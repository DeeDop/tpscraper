import argparse
from contextlib import nullcontext
import json
import time
from pathlib import Path
import httpx
from .protocol import Decoder, frame
from .auth import Auth, AuthError
from .quote_schema import quote_request, candidate_price, candidate_details

BASE = "https://backend.takeprofit.com/"
SERVICES = {
    "quote": "takeprofit.marketdata.external.quote.v1.QuoteApi/ListQuotes",
    "candles": "takeprofit.marketdata.external.candle.v1.CandleStreamApi/CandleStream",
    "history": "takeprofit.marketdata.external.candle.v1.ExtrapolationApi/ListBars",
}

def probe(service, seconds, auth=None, symbol="XAU/USD", provider="FXPPST", client=None):
    result = {"service": service, "messages": 0, "bytes": 0,
              "chunks": 0, "prices_verified": False, "grpc_status": None}
    start = time.monotonic()
    decoder = Decoder()
    candidates=[]
    details=[]
    if service=="quote":
        result.update(symbol=symbol, provider=provider)
    try:
        headers={"content-type":"application/grpc-web+proto","x-grpc-web":"1"}
        if auth:
            headers.update(auth.headers())
        result["authorization_elapsed_s"]=round(time.monotonic()-start,3)
        # Human approval / Chrome login is not network observation time.
        start=time.monotonic()
        payload=quote_request(symbol,provider) if service=="quote" else b""
        with (nullcontext(client) if client is not None else httpx.Client(http2=True, timeout=min(seconds,10), follow_redirects=False, trust_env=False)) as connection:
            with connection.stream("POST",BASE+SERVICES[service],content=frame(payload),headers=headers) as response:
                result.update(http_status=response.status_code,http_version=response.http_version)
                if response.status_code != 200:
                    result["outcome"]="access_denied" if response.status_code in (401,403) else "rate_limited" if response.status_code==429 else "http_error"
                elif "application/grpc-web" not in response.headers.get("content-type",""):
                    result["outcome"]="unexpected_content_type"
                else:
                    result["outcome"]="response_unvalidated"
                    status=response.headers.get("grpc-status")
                    if status and status.isdigit():
                        result["grpc_status"]=int(status)
                    trailer_received=False
                    for chunk in response.iter_bytes():
                        result["chunks"]+=1
                        for flags,body in decoder.feed(chunk):
                            if flags==128:
                                trailer_received=True
                                for line in body.splitlines():
                                    if line.lower().startswith(b"grpc-status:"):
                                        value=line.split(b":",1)[1].strip()
                                        if value.isdigit():
                                            result["grpc_status"]=int(value)
                            elif not flags&128:
                                result["messages"]+=1
                                result["bytes"]+=len(body)
                                if flags==0 and service=="quote":
                                    try:
                                        candidates.append(candidate_price(body))
                                        details.append(candidate_details(body))
                                    except ValueError:
                                        result["schema_mismatch"]=True
                        # A completed gRPC trailer takes precedence over the time limit.
                        if trailer_received:
                            decoder.finish()
                            break
                        if time.monotonic()-start>=seconds:
                            result["outcome"]="observation_limit"
                            break
                    else:
                        decoder.finish()
                    if result["grpc_status"] not in (None,0):
                        result["outcome"]="grpc_error"
                    elif result["grpc_status"]==0 and candidates:
                        result["outcome"]="candidate_price_unverified"
                        result["candidate_prices"]=candidates[:20]
                        if len(details)==1 and details[0]:
                            result["candidate_details"]=details[0]
    except AuthError as exc:
        result.update(outcome="authorization_required", detail=str(exc))
    except (httpx.HTTPError,ValueError) as exc:
        result.update(outcome="probe_error",error_type=type(exc).__name__)
    result["elapsed_s"]=round(time.monotonic()-start,3)
    if auth:
        result["renewals"]=auth.renewals
    return result

def main():
    import sys
    if len(sys.argv)>1 and sys.argv[1] in ("dashboard","serve"):
        from .dashboard import main as dashboard_main
        args=sys.argv[2:]
        if sys.argv[1]=="serve" and "--no-browser" not in args:
            args=args+["--no-browser"]
        return dashboard_main(args)
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("probe")
    p.add_argument("--service",choices=SERVICES,default="quote")
    p.add_argument("--seconds",type=float,default=15)
    p.add_argument("--symbol",default="XAU/USD")
    p.add_argument("--provider",default="FXPPST")
    p.add_argument("--repeat",type=int,default=1)
    p.add_argument("--interval",type=float,default=15)
    group=p.add_mutually_exclusive_group()
    group.add_argument("--prompt",action="store_true",help="Use an explicitly supplied access token in memory")
    group.add_argument("--session",action="store_true",help="Experimental first-party session renewal; use only if permitted")
    args=parser.parse_args()
    if not 1<=args.seconds<=120 or not 1<=args.repeat<=100 or not 15<=args.interval<=3600:
        parser.error("Invalid duration, repeat count or interval")
    if args.service!="quote" and (args.prompt or args.session):
        parser.error("Authenticated candle/history schema not verified; use quote first")
    auth=None
    results=[]
    try:
        if args.prompt or args.session:
            auth=Auth.prompt(session=args.session)
        for i in range(args.repeat):
            result=probe(args.service,args.seconds,auth,args.symbol,args.provider)
            results.append(result)
            print(json.dumps(result,indent=2),flush=True)
            if result["outcome"]!="candidate_price_unverified":
                break
            if i+1<args.repeat:
                time.sleep(args.interval)
    except AuthError as exc:
        print("Authorization input rejected:",str(exc))
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        if auth:
            auth.close()
        if results:
            Path("probe_result.json").write_text(json.dumps(results[0] if len(results)==1 else results,indent=2),encoding="utf-8")
            print("Saved credential-free probe_result.json")

if __name__=="__main__":
    main()
