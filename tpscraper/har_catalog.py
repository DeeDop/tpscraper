"""Offline extraction of public instrument metadata from TakeProfit screener HAR responses.

Never reads or exports request headers, cookies, authentication, or raw payloads.
Only the observed 27-column screener layout is accepted.
"""
import argparse
import base64
import csv
import json
from pathlib import Path
from urllib.parse import urlsplit
from .protocol import Decoder
from .quote_schema import fields

ENDPOINT = "/takeprofit.screener.external.v1.SearcherApi/SearchWithGroups"
COLUMNS = ("provider","symbol","exchange_name","market_type","category","group",
           "base","asset_type","quote_currency","description")


def children(data, field):
    return [value for wire,value in fields(data).get(field,[]) if wire==2]


def one(data, field):
    values=children(data,field)
    if len(values)!=1:
        raise ValueError("Unexpected field count")
    return values[0]


def extract_message(body):
    for group in children(body,1):
        for container in children(group,4):
            for item in children(container,2):
                try:
                    identity=one(one(item,1),2)
                    symbol=one(identity,1).decode()
                    provider=one(identity,2).decode()
                    cols=children(item,2)
                    if len(cols)!=27:
                        continue
                    def cell(index):
                        return one(cols[index],10).decode()
                    if cell(3)!=symbol or cell(6)!=provider:
                        continue
                    row=dict(provider=provider,symbol=symbol,exchange_name=cell(7),
                             market_type=cell(8),category=cell(9),group=cell(10),
                             base=cell(11),asset_type=cell(12),quote_currency=cell(19),
                             description=cell(20))
                    if not all(len(v)<=500 and not any(ord(c)<32 for c in v) for v in row.values()):
                        continue
                    yield row
                except (ValueError,IndexError,UnicodeError):
                    continue


def extract_har(har):
    rows={}
    responses=0
    for entry in har.get("log",{}).get("entries",[]):
        request=entry.get("request",{})
        url=urlsplit(request.get("url",""))
        response=entry.get("response",{})
        if (url.scheme!="https" or url.hostname!="backend.takeprofit.com"
                or url.path!=ENDPOINT or request.get("method")!="POST"
                or response.get("status")!=200):
            continue
        content=response.get("content",{})
        if content.get("encoding")!="base64" or not content.get("text"):
            continue
        try:
            decoder=Decoder()
            frames=list(decoder.feed(base64.b64decode(content["text"],validate=True)))
            decoder.finish()
            trailers=[v for flag,v in frames if flag==128]
            if not any(any(line.partition(b":")[0].strip().lower()==b"grpc-status" and line.partition(b":")[2].strip()==b"0" for line in t.splitlines()) for t in trailers):
                continue
            batch=[]
            for flag,body in frames:
                if flag==0:
                    batch.extend(extract_message(body))
            responses+=1
            for row in batch:
                rows[row["provider"],row["symbol"]]=row
        except (ValueError,TypeError,IndexError):
            continue
    return [rows[key] for key in sorted(rows)],responses


def write_catalog(rows, output):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    with (output/"takeprofit_tickers.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=("input",)+COLUMNS)
        writer.writeheader()
        # Guard spreadsheet formula interpretation; exact input is still provider:symbol.
        def safe(v):
            return "'"+v if v.startswith(("=","+","-","@")) else v
        for row in rows:
            writer.writerow({k:safe(v) for k,v in dict(row,input=row["provider"]+":"+row["symbol"]).items()})
    with (output/"takeprofit_exchanges.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.writer(f)
        writer.writerow(("provider","exchange_names","instrument_count"))
        for provider in sorted({row["provider"] for row in rows}):
            group=[row for row in rows if row["provider"]==provider]
            writer.writerow((provider,"; ".join(sorted({r["exchange_name"] for r in group})),len(group)))


def main():
    parser=argparse.ArgumentParser(description="Extract instrument metadata from local HAR; no network requests")
    parser.add_argument("har",type=Path)
    parser.add_argument("--output",type=Path,default=Path("."))
    args=parser.parse_args()
    try:
        with args.har.open(encoding="utf-8-sig") as f:
            rows,responses=extract_har(json.load(f))
        if not rows:
            parser.exit(1,"No compatible screener results found; nothing exported.\n")
        write_catalog(rows,args.output)
    except (OSError,ValueError,TypeError):
        parser.exit(1,"Unable to read or export the HAR catalog.\n")
    print(f"Extracted {len(rows)} unique provider/symbol pairs from {responses} screener responses.")
    print("Catalog membership is not proof of live market-data access.")

if __name__=="__main__":
    main()
