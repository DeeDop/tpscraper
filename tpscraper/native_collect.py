"""Persistent read-only collection using the native endpoints tested on Gold/BTC.

One tagged quote subscription plus one candle subscription per instrument.
An optional second candle resolution is explicitly requested. No polling loop,
no access-denial retries, no automatic fallback to other data providers.
"""
import threading
import time
import httpx
from .auth import expires_at, AuthError
from .native_schema import CANDLE_STREAM, QUOTE_STREAM, candle_request, candle_item, quote_stream_request, quote_item
from .native_probe import messages
from .extended_schema import plans, trade_rows, book_summary, footprint_rows, tpo_rows
from .flow_state import BookGap


def collect_native(state,auth,stop):
    pairs=[]
    by_pair={}
    for inst in state.instruments:
        provider,symbol=inst.symbol.split(":",1)
        pair=(symbol,provider)
        if pair not in by_pair:
            pairs.append(pair)
            by_pair[pair]=[]
        by_pair[pair].append(inst.key)
    while not stop.is_set():
        try:
            headers=auth.headers()   # User-authorized renewal happens on main thread only.
        except AuthError as exc:
            state.stop('authorization unavailable')
            print(str(exc),flush=True)
            return
        expiry=expires_at(headers.get("accesstoken",""))
        cycle=threading.Event()
        halt=[]
        halt_lock=threading.Lock()
        workers=[]

        def deny(reason):
            with halt_lock:
                if not halt:
                    halt.append(reason)
                cycle.set()

        with httpx.Client(http2=True,timeout=httpx.Timeout(20.0,connect=10.0),
                          limits=httpx.Limits(max_connections=1+len(state.instruments)*(2 if state.micro else 1)+state.flow_budget,max_keepalive_connections=16),
                          trust_env=False,follow_redirects=False) as client:
            def run(service,payload,decode,apply,report,label,capability=None):
                observed=False
                def remember(status):
                    if capability is not None:
                        symbol,kind=capability
                        state.capabilities.remember(symbol,kind,status)
                attempt=0
                while not cycle.is_set() and not stop.is_set():
                    observed_this_attempt=False
                    attempt+=1
                    if cycle.is_set() or stop.is_set():
                        return
                    report("connecting" if attempt==1 else "reconnecting")
                    state.stream_event(label,"attempt")
                    try:
                        stream=messages(client,service,payload,headers)
                        try:
                            for raw in stream:
                                if cycle.is_set() or stop.is_set():
                                    return
                                if isinstance(raw,dict):
                                    http=raw.get("http_status")
                                    grpc=raw.get("grpc_status")
                                    if http in (401,403,429) or grpc in (7,8,16):
                                        reason=f"{label}: access or rate restriction ({http or grpc})"
                                        report(reason)
                                        deny(reason)
                                        return
                                    if capability is not None and grpc in (3,5,12):
                                        result="unsupported" if grpc==12 else "unavailable"
                                        remember(result)
                                        report(result)
                                        return
                                    if http in (500,502,503,504) or grpc in (4,13,14):
                                        raise RuntimeError('transient upstream error')
                                    if http or grpc not in (0,None) or raw.get("error"):
                                        report(f"service unavailable ({http or grpc or raw.get('error')})")
                                        return
                                    break
                                item=decode(raw)
                                if item:
                                    state.stream_event(label,"message")
                                if item is not None and apply(item) is False:
                                    return
                                if capability is not None and item:
                                    observed_this_attempt=True
                                    if not observed:
                                        observed=True
                                        remember("observed")
                        finally:
                            stream.close()
                        if capability is not None and not observed_this_attempt:
                            remember("no_data")
                            report("no_data")
                            return
                        report("stream ended")
                    except (httpx.HTTPError,ValueError,RuntimeError) as exc:
                        if cycle.is_set() or stop.is_set():
                            return
                        if capability is not None and not observed_this_attempt and isinstance(exc,httpx.ReadTimeout):
                            remember("no_data")
                            report("no_data")
                            return
                        state.stream_event(label,"error",type(exc).__name__)
                        report(type(exc).__name__)
                        if isinstance(exc,ValueError):
                            return  # Never retry an unknown schema in a loop.
                    # Slow recovery after repeated transport failures. No access-denial
                    # retries or schema guessing. Keep healthy streams running.
                    delay=min(120,2**min(attempt,7))
                    state.stream_event(label,"retry",str(delay))
                    if cycle.wait(delay):
                        return

            def launch(*args):
                t=threading.Thread(target=run,args=args,daemon=True)
                workers.append(t)
                t.start()
                return t

            def on_quote(item):
                code=item.get("status",0)
                keys=by_pair[(item["symbol"],item["provider"])]
                for key in keys:
                    state.ingest_quote(key,item)
                if code in (7,8):
                    deny("quote stream access or rate restriction")
                    return False
                if code==16:
                    deny("quote stream authorization required")
                    return False
                # An unavailable instrument does not erase valid other subscriptions.
                return True

            launch(QUOTE_STREAM,quote_stream_request(pairs),lambda raw:quote_item(raw,pairs),
                   on_quote,state.all_quotes,"quotes")
            ordered=sorted(state.instruments,key=lambda i:i.key!="gold")
            try:
                for period in ((60,30) if state.micro else (60,)):
                    for inst in ordered:
                        if cycle.is_set() or stop.is_set():
                            break
                        provider,symbol=inst.symbol.split(":",1)
                        def on_bar(item,key=inst.key,p=period):
                            state.ingest_bar(key,p,item)
                            code=item.get("status",0)
                            if code in (7,8,16):
                                deny("candle rate restriction or authorization required")
                            return not bool(code)
                        def report(reason,key=inst.key,p=period):
                            state.bar_state(key,p,reason)
                        count=min(1000,state.history*(2 if period==30 else 1))
                        launch(CANDLE_STREAM,candle_request(symbol,provider,period,count),
                               candle_item,on_bar,report,f"{inst.symbol} {period}s")
                        if cycle.wait(0.20):
                            break
                # Queue every entered ticker. Catalog information only prioritizes;
                # a missing record never prevents discovery.
                pending=state.capabilities.queue(state.flows,state.refresh_capabilities) if state.flows else []
                active={}
                decoders={"trades":trade_rows,"footprint":lambda raw:footprint_rows(raw,full=True),
                          "orderbook":lambda raw:book_summary(raw,full=True),
                          "heatmap":lambda raw:book_summary(raw,heat=True,full=True),"tpo":tpo_rows}

                def launch_next():
                    key,kind=pending.pop(0)
                    flow=state.flows[key]
                    provider,symbol=flow.symbol.split(":",1)
                    service,payload,_=plans(symbol,provider)[kind]
                    def apply(rows):
                        flow.ingest(kind,rows)
                        return True
                    def report(reason):
                        flow.status(kind,reason)
                    active[(key,kind)]=launch(service,payload,decoders[kind],apply,report,
                                             f"{flow.symbol} {kind}",(flow.symbol,kind))

                state.refresh_capabilities=False  # force once, not on every renewal
                next_launch=time.monotonic()
                renew=False
                next_record=time.monotonic()
                while not stop.is_set() and not cycle.is_set():
                    for job,thread in list(active.items()):
                        if not thread.is_alive():
                            del active[job]
                    if pending and len(active)<state.flow_budget and time.monotonic()>=next_launch:
                        launch_next()
                        next_launch=time.monotonic()+0.5
                    if state.recorder is not None and time.monotonic()>=next_record:
                        state.record_flow()
                        next_record=time.monotonic()+1
                    if expiry is not None and time.time()>=expiry-45:
                        renew=True
                        break
                    if not pending and not any(t.is_alive() for t in workers):
                        break
                    stop.wait(0.25)
            finally:
                cycle.set()
                # Close sockets to wake blocked readers before joining threads.
                # Bound total shutdown time rather than waiting once per socket.
                client.close()
                deadline=time.monotonic()+5
                for t in workers:
                    t.join(timeout=max(0,deadline-time.monotonic()))
                if any(t.is_alive() for t in workers):
                    halt.append("stream shutdown incomplete; restart required")
                state.all_quotes("native streams paused")
                for flow in state.flows.values():
                    for kind in list(flow.states):
                        if "restriction" not in flow.states[kind] and flow.states[kind] not in ("no_data","unsupported","unavailable","cached_no_data","cached_unsupported","cached_unavailable"):
                            flow.status(kind,"paused")
        if halt:
            state.stop(halt[0])
            print(halt[0]+". Resolve provider access before restarting.",flush=True)
            return
        if stop.is_set():
            return
        if not renew:
            state.stop("native streams stopped")
            return
        state.stream_event("authorization","renewal")
        print("Access token nearing expiry; renewing local authorization.",flush=True)
