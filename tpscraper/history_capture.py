"""Offline, credential-free diagnostics for captured historical market-data messages.

Only ListBars POST request/response bodies are examined. No headers, cookies,
URLs with queries, raw binary data, arbitrary text or identifiers are emitted.
"""
import argparse
import base64
import json
import struct
from pathlib import Path
from urllib.parse import urlsplit
from .protocol import Decoder
from .quote_schema import fields

ENDPOINT="/takeprofit.marketdata.external.candle.v1.ExtrapolationApi/ListBars"

def tree(body,allowed,depth=0):
    result={}
    for key,values in fields(body).items():
        items=[]
        for wire,value in values[:3]:
            if wire==0:
                items.append({"wire":wire,"integer":value})
            elif wire==2:
                try:
                    decoded=value.decode("utf-8")
                except UnicodeError:
                    decoded=None
                if decoded in allowed:
                    items.append({"wire":wire,"instrument":decoded})
                elif depth<7 and value:
                    try:
                        items.append({"wire":wire,"length":len(value),"fields":tree(value,allowed,depth+1)})
                    except ValueError:
                        items.append({"wire":wire,"length":len(value)})
                else:
                    items.append({"wire":wire,"length":len(value)})
            else:
                # Fixed-width protobuf values could be floating-point OHLC.
                fmt="<d" if wire==1 else "<f"
                import math
                n=struct.unpack(fmt,value)[0]
                items.append({"wire":wire,"number":n if math.isfinite(n) else None})
        result[str(key)]={"count":len(values),"samples":items}
    return result

def body_bytes(obj):
    text=obj.get("text")
    if not isinstance(text,str) or not text:
        return []
    if obj.get("encoding")=="base64":
        try:
            return [base64.b64decode(text,validate=True)]
        except ValueError:
            return []
    out=[]
    for encoding in ("latin1","utf-8"):
        try:
            data=text.encode(encoding)
            if data not in out:
                out.append(data)
        except UnicodeError:
            pass
    return out

def describe(obj,allowed):
    for data in body_bytes(obj):
        if len(data)>16*1024*1024:
            continue
        try:
            decoder=Decoder()
            frames=list(decoder.feed(data))
            decoder.finish()
            if not frames:
                continue
            out=[]
            for flag,body in frames[:4]:
                item={"flag":flag,"length":len(body)}
                if flag==0:
                    item["fields"]=tree(body,allowed)
                elif flag==128:
                    for line in body.splitlines():
                        k,_,v=line.partition(b":")
                        if k.lower()==b"grpc-status" and v.strip().isdigit():
                            item["grpc_status"]=int(v.strip())
                out.append(item)
            return {"frame_count":len(frames),"frames":out}
        except (ValueError,OverflowError,RecursionError):
            continue
    return {"available":False,"reason":"Missing or undecodable binary body"}

def inspect(har,allowed):
    output=[]
    for entry in har.get("log",{}).get("entries",[]):
        req=entry.get("request",{})
        url=urlsplit(req.get("url",""))
        if url.scheme!="https" or url.hostname!="backend.takeprofit.com" or url.path!=ENDPOINT or req.get("method")!="POST":
            continue
        res=entry.get("response",{})
        if res.get("status")!=200:
            continue
        output.append({"request":describe(req.get("postData",{}),allowed),
                       "response":describe(res.get("content",{}),allowed)})
        if len(output)>=3:
            break
    return {"service":"ListBars","samples":output}

def main():
    p=argparse.ArgumentParser(description="Extract credential-free ListBars structure from a local HAR")
    p.add_argument("har",type=Path)
    p.add_argument("--symbol",default="XAU/USD")
    p.add_argument("--provider",default="FXPPST")
    a=p.parse_args()
    try:
        with a.har.open(encoding="utf-8-sig") as f:
            result=inspect(json.load(f),{a.symbol,a.provider})
    except (OSError,ValueError,TypeError):
        p.exit(1,"Could not read HAR. No credentials were exported.\n")
    print(json.dumps(result,indent=2,allow_nan=False))
    print("Only share this diagnostic, not the raw HAR. Review before sharing.")

if __name__=="__main__":
    main()
