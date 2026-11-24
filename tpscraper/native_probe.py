"""One bounded read-only native request using the existing local authorization."""
import argparse
import json
import time
import httpx
from .native_schema import (CANDLE_HISTORY,CANDLE_STREAM,QUOTE_STREAM,
    history_request,candle_request,quote_stream_request,history_items,candle_item,quote_item)
from .protocol import frame,Decoder
from .local_chrome import LocalChromeAuth
from .credential_store import CredentialStore,StoreError
from .auth import AuthError

BASE="https://backend.takeprofit.com/"

def messages(client,service,payload,headers):
    with client.stream("POST",BASE+service,content=frame(payload),
            headers={"content-type":"application/grpc-web+proto","x-grpc-web":"1",**headers}) as res:
        if res.status_code!=200:
            yield {"http_status":res.status_code}
            return
        if "application/grpc-web" not in res.headers.get("content-type",""):
            yield {"error":"unexpected_content_type"}
            return
        d=Decoder()
        for chunk in res.iter_bytes():
            for flag,body in d.feed(chunk):
                if flag==0:
                    yield body
                elif flag==128:
                    code=None
                    for line in body.splitlines():
                        k,_,v=line.partition(b":")
                        if k.lower()==b"grpc-status" and v.strip().isdigit():
                            code=int(v.strip())
                    yield {"grpc_status":code}
                    d.finish()
                    return
                else:
                    raise ValueError("Unsupported compressed frame")
        d.finish()

def main():
    p=argparse.ArgumentParser(description="Test native TakeProfit market data on one bounded connection")
    p.add_argument("mode",choices=("history","candles","quotes"))
    p.add_argument("--symbol",default="XAU/USD")
    p.add_argument("--provider",default="FXPPST")
    p.add_argument("--period",type=int,choices=(30,60,300,900),default=60)
    p.add_argument("--count",type=int,default=360)
    p.add_argument("--seconds",type=int,default=15)
    p.add_argument("--remember",action="store_true")
    a=p.parse_args()
    if not 1<=a.count<=1000 or not 1<=a.seconds<=60:
        p.error("Invalid count/duration")
    pairs=[(a.symbol,a.provider)]
    if a.mode=="history":
        service,payload,parse=CANDLE_HISTORY,history_request(*pairs[0],a.period,a.count),history_items
    elif a.mode=="candles":
        service,payload,parse=CANDLE_STREAM,candle_request(*pairs[0],a.period,a.count),candle_item
    else:
        pairs.append(("BTC/USDT","CXBNCE") if pairs[0]!=("BTC/USDT","CXBNCE") else ("XAU/USD","FXPPST"))
        service,payload=QUOTE_STREAM,quote_stream_request(pairs)
        parse=lambda body:quote_item(body,pairs)
    store=None
    if a.remember:
        try: store=CredentialStore()
        except StoreError: pass
    auth=LocalChromeAuth(store=store)
    bars={}; quotes={}; events=0; updates=0; final_marker=False
    result={"mode":a.mode,"instruments":pairs,"period":a.period}
    try:
        headers=auth.headers()
        started=time.monotonic()
        with httpx.Client(http2=True,timeout=httpx.Timeout(5.0),trust_env=False,follow_redirects=False) as client:
            gen=messages(client,service,payload,headers)
            try:
                for raw in gen:
                    if isinstance(raw,dict):
                        result.update(raw)
                        break
                    item=parse(raw)
                    events+=1
                    if item:
                        if item.get("status"):
                            result["item_status"]=item["status"]
                            break
                        if a.mode=="quotes":
                            key=item["provider"]+":"+item["symbol"]
                            # Sparse quote updates merge only explicitly present fields.
                            row=quotes.setdefault(key,{})
                            for session in ("main_session","daily_session"):
                                if session in item:
                                    row.setdefault(session,{}).update(item[session])
                        else:
                            batch=item.get("bars",[]) if a.mode=="history" else [item["bar"]] if item.get("bar") else []
                            for bar in batch:
                                if bar["t"] in bars:
                                    updates+=1
                                bars[bar["t"]]=bar
                            final_marker=final_marker or item.get("is_last",False)
                    if a.mode!="history" and (time.monotonic()-started>=a.seconds or events>=5000):
                        result["observation_limit"]=True
                        break
            finally:
                gen.close()
    except (AuthError,httpx.HTTPError,ValueError) as exc:
        result["error_type"]=type(exc).__name__
    except KeyboardInterrupt:
        result["interrupted"]=True
    finally:
        auth.close()
    ordered=[bars[t] for t in sorted(bars)]
    result.update(events=events,unique_bars=len(ordered),repeated_bar_updates=updates,
                  initial_history_marker=final_marker,volume_bars=sum(b["v"] is not None for b in ordered),
                  first_bar=ordered[0] if ordered else None,last_bar=ordered[-1] if ordered else None,quotes=quotes)
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__=="__main__":
    main()
