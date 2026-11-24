import argparse
import json
import time
from pathlib import Path
import httpx
from .protocol import Decoder, frame

BASE = "https://backend.takeprofit.com/"
SERVICES = {
    "quote": "takeprofit.marketdata.external.quote.v1.QuoteApi/ListQuotes",
    "candles": "takeprofit.marketdata.external.candle.v1.CandleStreamApi/CandleStream",
    "history": "takeprofit.marketdata.external.candle.v1.ExtrapolationApi/ListBars",
}

def probe(service, seconds):
    result = {"service": service, "messages": 0, "bytes": 0,
              "chunks": 0, "prices_verified": False, "grpc_status": None}
    start = time.monotonic()
    decoder = Decoder()
    try:
        with httpx.Client(http2=True, timeout=min(seconds, 10), follow_redirects=False) as client:
            with client.stream("POST", BASE + SERVICES[service], content=frame(b""),
                               headers={"content-type":"application/grpc-web+proto",
                                        "x-grpc-web":"1"}) as response:
                result.update(http_status=response.status_code, http_version=response.http_version)
                if response.status_code != 200:
                    result["outcome"] = "access_denied" if response.status_code in (401,403) else "http_error"
                elif "application/grpc-web" not in response.headers.get("content-type",""):
                    result["outcome"] = "unexpected_content_type"
                else:
                    result["outcome"] = "response_unvalidated"
                    result["grpc_status"] = response.headers.get("grpc-status")
                    for chunk in response.iter_bytes():
                        result["chunks"] += 1
                        for flags, payload in decoder.feed(chunk):
                            if flags == 128:
                                for line in payload.splitlines():
                                    if line.lower().startswith(b"grpc-status:"):
                                        value = line.split(b":",1)[1].strip()
                                        if value.isdigit():
                                            result["grpc_status"] = int(value)
                            elif not flags & 128:
                                result["messages"] += 1
                                result["bytes"] += len(payload)
                        if time.monotonic()-start >= seconds:
                            result["outcome"] = "observation_limit"
                            break
                    else:
                        decoder.finish()
    except (httpx.HTTPError, ValueError) as exc:
        result.update(outcome="probe_error", error_type=type(exc).__name__)
    result["elapsed_s"] = round(time.monotonic()-start,3)
    return result

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--service", choices=SERVICES, default="quote")
    p.add_argument("--seconds", type=float, default=15)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 120:
        parser.error("seconds must be between 1 and 120")
    result = probe(args.service, args.seconds)
    data = json.dumps(result, indent=2)
    Path("probe_result.json").write_text(data, encoding="utf-8")
    print(data)

if __name__ == "__main__":
    main()
