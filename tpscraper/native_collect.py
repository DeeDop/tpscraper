"""Persistent read-only collection using the native endpoints tested on Gold/BTC.

One tagged quote subscription plus one candle subscription per instrument.
An optional second candle resolution is explicitly requested. No polling loop,
no access-denial retries, no automatic fallback to other data providers.
"""
import threading
import time
import httpx
from .auth import expires_at
from .native_schema import CANDLE_STREAM, QUOTE_STREAM, candle_request, candle_item, quote_stream_request, quote_item
from .native_probe import messages


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
        headers=auth.headers()   # User-authorized renewal happens on main thread only.
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
                          limits=httpx.Limits(max_connections=32,max_keepalive_connections=16),
                          trust_env=False,follow_redirects=False) as client:
            def run(service,payload,decode,apply,report,label):
                for attempt in range(3):
                    if cycle.is_set() or stop.is_set():
                        return
                    report("connecting" if attempt==0 else "reconnecting")
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
                                    if http or grpc not in (0,None) or raw.get("error"):
                                        report(f"service unavailable ({http or grpc or raw.get('error')})")
                                        return
                                    break
                                item=decode(raw)
                                if item is not None and apply(item) is False:
                                    return
                        finally:
                            stream.close()
                        report("stream ended")
                    except (httpx.HTTPError,ValueError,RuntimeError) as exc:
                        if cycle.is_set() or stop.is_set():
                            return
                        report(type(exc).__name__)
                        if isinstance(exc,ValueError):
                            return  # Never retry an unknown schema in a loop.
                    if attempt<2 and cycle.wait(2**(attempt+1)):
                        return
                report("stream stopped; retry limit reached")

            def launch(*args):
                t=threading.Thread(target=run,args=args,daemon=True)
                workers.append(t)
                t.start()

            def on_quote(item):
                code=item.get("status",0)
                keys=by_pair[(item["symbol"],item["provider"])]
                for key in keys:
                    state.ingest_quote(key,item)
                if code==8:
                    deny("quote stream rate restriction")
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
                            if code in (8,16):
                                deny("candle rate restriction or authorization required")
                            return not bool(code)
                        def report(reason,key=inst.key,p=period):
                            state.bar_state(key,p,reason)
                        count=min(1000,state.history*(2 if period==30 else 1))
                        launch(CANDLE_STREAM,candle_request(symbol,provider,period,count),
                               candle_item,on_bar,report,f"{inst.symbol} {period}s")
                        if cycle.wait(0.20):
                            break
                renew=False
                while not stop.is_set() and not cycle.is_set():
                    if expiry is not None and time.time()>=expiry-45:
                        renew=True
                        break
                    if not any(t.is_alive() for t in workers):
                        break
                    stop.wait(0.25)
            finally:
                cycle.set()
                # Close sockets to wake blocked readers before joining threads.
                client.close()
                for t in workers:
                    t.join(timeout=1)
                state.all_quotes("native streams paused")
        if halt:
            state.stop(halt[0])
            print(halt[0]+". Resolve provider access before restarting.",flush=True)
            return
        if stop.is_set():
            return
        if not renew:
            state.stop("native streams stopped")
            return
        print("Access token nearing expiry; fresh local authorization required.",flush=True)
