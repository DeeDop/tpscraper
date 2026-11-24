"""Small terminal monitor for experimental TakeProfit quote snapshots."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import time

import httpx

from .__main__ import probe
from .auth import Auth, AuthError


def format_sample(result, previous=None, now=None):
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%H:%M:%S")
    prefix = f"{stamp} UTC | {result['provider']}:{result['symbol']}"
    if result["outcome"] != "candidate_price_unverified":
        status = result.get("http_status")
        suffix = f" HTTP {status}" if status is not None else ""
        return f"{prefix} | {result['outcome'].upper()}{suffix}", previous
    try:
        values = result["candidate_prices"]
        if len(values) != 1:
            raise ValueError("ambiguous price")
        price = Decimal(values[0])
        if not price.is_finite():
            raise ValueError("nonfinite price")
    except (KeyError, ValueError, InvalidOperation, TypeError):
        return f"{prefix} | AMBIGUOUS PRICE", previous
    if previous is None:
        change = "FIRST"
    else:
        delta = price - previous
        change = ("UP" if delta > 0 else "DOWN" if delta < 0 else "SAME") + f" {delta:+f}"
    latency = round(result.get("elapsed_s", 0) * 1000)
    return f"{prefix} | {price:f} | {change} | {latency} ms | UNVERIFIED SNAPSHOT", price


def monitor(auth, symbol, provider, interval=15, count=0, client=None, emit=print, sleep=time.sleep):
    previous = None
    attempts = 0
    failures = 0
    while not count or attempts < count:
        result = probe("quote", 10, auth, symbol, provider, client=client)
        line, price = format_sample(result, previous)
        emit(line)
        attempts += 1
        if result["outcome"] == "candidate_price_unverified":
            previous = price
            failures = 0
        elif result["outcome"] == "probe_error":
            failures += 1
            if failures >= 3:
                emit("Stopped after three transport/protocol failures.")
                break
        else:
            emit("Stopped: inspect authorization, entitlement, or response status.")
            break
        if count and attempts >= count:
            break
        sleep(interval * (2 ** failures))
    return attempts


def main():
    parser = argparse.ArgumentParser(description="Experimental TakeProfit quote console")
    parser.add_argument("--symbol", default="XAU/USD")
    parser.add_argument("--provider", default="FXPPST")
    parser.add_argument("--interval", type=float, default=15, help="Seconds between requests (minimum 15)")
    parser.add_argument("--count", type=int, default=0, help="Number of observations; zero runs until stopped")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--session", action="store_true", help="Use existing experimental session renewal, if permitted")
    mode.add_argument("--browser", action="store_true", help="Opt-in isolated Chrome authorization, if permitted")
    mode.add_argument("--local-chrome", action="store_true", help="Use regular installed Chrome with explicit local authorization handoff")
    args = parser.parse_args()
    if not 15 <= args.interval <= 3600 or not 0 <= args.count <= 100000:
        parser.error("interval must be 15–3600 seconds and count must be nonnegative")
    auth = None
    try:
        print("TPSCRAPER | QUOTE MONITOR", flush=True)
        print("Snapshot polling; not push streaming. Prices are unverified.", flush=True)
        if args.local_chrome:
            from .local_chrome import LocalChromeAuth
            auth = LocalChromeAuth()
        elif args.browser:
            from .browser_auth import BrowserAuth
            auth = BrowserAuth()
        else:
            auth = Auth.prompt(session=args.session)
        with httpx.Client(http2=True, timeout=10, follow_redirects=False, trust_env=False) as client:
            monitor(auth, args.symbol, args.provider, args.interval, args.count, client, emit=lambda line: print(line, flush=True))
    except AuthError as exc:
        print("Authorization:", str(exc))
    except KeyboardInterrupt:
        print("\nMonitor stopped.")
    finally:
        if auth is not None:
            auth.close()


if __name__ == "__main__":
    main()
