"""One experimental multi-instrument ListQuotes request; no positional mapping assumed."""
import argparse
import json
import httpx
from .auth import AuthError
from .credential_store import CredentialStore, StoreError
from .local_chrome import LocalChromeAuth
from .quote_schema import quote_request, fields, candidate_price, message
from .protocol import frame, Decoder
from .__main__ import BASE, SERVICES

def inspect_batch(body):
    root=fields(body)
    items=[]
    for wire,value in root.get(2,[]):
        if wire!=2:
            continue
        row=fields(value)
        item={"fields":{str(k):[w for w,_ in vals] for k,vals in row.items()}}
        indexes=[v for w,v in row.get(1,[]) if w==0]
        if indexes:
            item["index_candidates"]=indexes[:8]
        try:
            item["candidate_price"]=candidate_price(message(2,value))
        except ValueError:
            pass
        items.append(item)
    return {"root_fields":{str(k):[w for w,_ in vals] for k,vals in root.items()},"items":items}

def main():
    p=argparse.ArgumentParser(description="One experimental two-symbol quote batch")
    p.add_argument("--remember",action="store_true")
    a=p.parse_args()
    store=None
    if a.remember:
        try: store=CredentialStore()
        except StoreError: pass
    auth=LocalChromeAuth(store=store)
    result={"requested":["FXPPST:XAU/USD","FXPPST:USDX.F"],"response_layout":[],"grpc_status":None}
    try:
        payload=quote_request("XAU/USD","FXPPST")+quote_request("USDX.F","FXPPST")
        headers={"content-type":"application/grpc-web+proto","x-grpc-web":"1",**auth.headers()}
        with httpx.Client(http2=True,timeout=10,follow_redirects=False,trust_env=False) as client:
            with client.stream("POST",BASE+SERVICES["quote"],headers=headers,content=frame(payload)) as response:
                result["http_status"]=response.status_code
                if response.status_code==200 and "application/grpc-web" in response.headers.get("content-type",""):
                    decoder=Decoder()
                    for chunk in response.iter_bytes():
                        for flags,body in decoder.feed(chunk):
                            if flags==0:
                                result["response_layout"].append(inspect_batch(body))
                            elif flags==128:
                                for line in body.splitlines():
                                    k,_,v=line.partition(b":")
                                    if k.lower()==b"grpc-status" and v.strip().isdigit():
                                        result["grpc_status"]=int(v.strip())
                    decoder.finish()
    except (AuthError,httpx.HTTPError,ValueError) as exc:
        result["error_type"]=type(exc).__name__
    finally:
        auth.close()
    print(json.dumps(result,indent=2))
    print("Diagnostic only: no quote assigned to a ticker until response mapping is verified.")

if __name__=="__main__":
    main()
