"""Run one sequential, bounded diagnostic per market-data feature.

Only use with account and provider permission for programmatic access.
No access-denial retries. Report contains market data and numeric status only.
"""
import argparse
import json
import time
from collections import Counter
from pathlib import Path
import httpx
from .auth import AuthError, expires_at
from .local_chrome import LocalChromeAuth
from .credential_store import CredentialStore, StoreError
from .native_probe import messages
from .extended_schema import plans

def run_one(client,headers,plan,seconds):
    service,payload,decode=plan
    result=dict(service=service,messages=0,records=0,kind_counts={},first=None,last=None)
    counts=Counter()
    started=time.monotonic()
    gen=messages(client,service,payload,headers)
    try:
        for raw in gen:
            if isinstance(raw,dict):
                result.update(raw)
                break
            result["messages"]+=1
            rows,code=decode(raw)
            if code:
                result["item_status"]=code
                break
            if rows:
                result["records"]+=len(rows)
                if result["first"] is None:
                    result["first"]=rows[0]
                result["last"]=rows[-1]
                counts.update(r.get("kind",r.get("side","data")) for r in rows)
            if time.monotonic()-started>=seconds or result["messages"]>=1000:
                result["observation_limit"]=True
                break
    except httpx.TimeoutException:
        result["read_timeout"]=True
    except (httpx.HTTPError,ValueError,RuntimeError,KeyError,TypeError,OverflowError) as exc:
        result["error_type"]=type(exc).__name__
    finally:
        gen.close()
    result["elapsed_s"]=round(time.monotonic()-started,3)
    result["kind_counts"]=dict(counts)
    http=result.get("http_status")
    grpc=result.get("grpc_status")
    item=result.get("item_status")
    if http in (401,403,429) or grpc in (7,8,16) or item in (7,8,16):
        result["verdict"]="restricted"
    elif result.get("error_type") or result.get("error") or http or grpc not in (None,0) or item:
        result["verdict"]="error"
    elif result["records"]:
        result["verdict"]="data_observed"
    else:
        result["verdict"]="no_data_observed"
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker",default="CXBNCE:BTC/USDT",help="PROVIDER:TICKER")
    p.add_argument("--only",nargs="+",choices=("history","candles","quotes","trades","orderbook","footprint","heatmap","tpo","renko"))
    p.add_argument("--seconds",type=int,default=6)
    p.add_argument("--remember",action="store_true")
    p.add_argument("--output",type=Path,default=Path("tp_data_report.json"))
    p.add_argument("--authorized",action="store_true",help="Confirm programmatic access is permitted by your provider/account")
    args=p.parse_args()
    if not args.authorized:
        p.error("Use --authorized only if your account/provider permits this programmatic market-data access.")
    if ":" not in args.ticker or not 1<=args.seconds<=15:
        p.error("Use PROVIDER:TICKER and 1-15 seconds.")
    provider,symbol=args.ticker.split(":",1)
    tests=plans(symbol,provider)
    report={"ticker":args.ticker,"generated_epoch":time.time(),"tests":{},
            "indie":"not requested; test your own indicator in the normal workspace"}
    store=None
    if args.remember:
        try:
            store=CredentialStore()
        except StoreError:
            pass
    auth=LocalChromeAuth(store=store)
    try:
        headers=auth.headers()
        expiry=expires_at(headers.get("accesstoken",""))
        with httpx.Client(http2=True,timeout=httpx.Timeout(8.0,connect=5.0),
                          trust_env=False,follow_redirects=False) as client:
            for name in args.only or tests:
                if expiry is not None and expiry-time.time()<30:
                    report["stopped"]="token nearing expiry"
                    break
                print("Testing",name,flush=True)
                row=run_one(client,headers,tests[name],args.seconds)
                report["tests"][name]=row
                print(" ",row["verdict"],"messages:",row["messages"],"records:",row["records"],flush=True)
                if row["verdict"]=="restricted":
                    report["stopped"]="Access or rate restriction. Resolve authorization before another request."
                    break
                time.sleep(1)
    except AuthError:
        report["stopped"]="authorization unavailable"
    except KeyboardInterrupt:
        report["stopped"]="interrupted"
    finally:
        auth.close()
        args.output.write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
        print("Saved report:",args.output.resolve())

if __name__=="__main__":
    main()
