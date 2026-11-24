"""Small terminal monitor for experimental TakeProfit quote snapshots."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import time

import httpx

from .__main__ import probe
from .auth import Auth, AuthError
from .terminal import TerminalRow


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


def monitor(auth, symbol, provider, interval=15, count=0, client=None, emit=print, sleep=time.sleep, notify=None, clock=time.monotonic):
    notify = notify or emit
    previous = None
    attempts = 0
    failures = 0
    while not count or attempts < count:
        started = clock()
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
                notify("Stopped after three transport/protocol failures.")
                break
        else:
            notify("Stopped: inspect authorization, entitlement, or response status.")
            break
        if count and attempts >= count:
            break
        if failures:
            sleep(interval * (2 ** failures))
        else:
            # Use start-to-start cadence, but never burst to catch up after a slow request.
            delay = interval - (clock() - started)
            sleep(delay if delay > 0 else interval)
    return attempts


def main():
    parser = argparse.ArgumentParser(description="Experimental TakeProfit quote console")
    parser.add_argument("ticker", nargs="?", help="Ticker or PROVIDER:TICKER; omit for interactive input")
    parser.add_argument("--symbol", help="Exact ticker (alternative to positional ticker)")
    parser.add_argument("--provider", help="Provider code; omit for catalog suggestions")
    parser.add_argument("--interval", type=float, default=15, help="Seconds between requests (minimum 1; use faster polling only if permitted)")
    parser.add_argument("--count", type=int, default=0, help="Number of observations; zero runs until stopped")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--session", action="store_true", help="Use existing experimental session renewal, if permitted")
    mode.add_argument("--browser", action="store_true", help="Opt-in isolated Chrome authorization, if permitted")
    mode.add_argument("--local-chrome", action="store_true", help="Use regular installed Chrome with explicit local authorization handoff")
    parser.add_argument("--remember", action="store_true", help="Save access token using Windows DPAPI (local Chrome mode)")
    parser.add_argument("--chrome-profile", help="Existing Chrome profile directory: Default or Profile N")
    parser.add_argument("--history", action="store_true", help="Print one line per observation instead of updating in place")
    args = parser.parse_args()
    if args.ticker and args.symbol:
        parser.error("Use a positional ticker or --symbol, not both")
    if (args.remember or args.chrome_profile) and not args.local_chrome:
        parser.error("--remember and --chrome-profile require --local-chrome")
    if not 1 <= args.interval <= 3600 or not 0 <= args.count <= 100000:
        parser.error("interval must be 1–3600 seconds and count must be nonnegative")
    auth = None
    row = TerminalRow()
    if args.history:
        row.enabled = False
    try:
        print("TPSCRAPER | QUOTE MONITOR", flush=True)
        print(f"Quote snapshot every {args.interval:g} seconds; not push streaming. Prices are unverified.", flush=True)
        from .symbols import choose
        try:
            selected = choose(args.ticker or args.symbol, args.provider, ask=row.ask, emit=row.message)
        except ValueError as exc:
            parser.error(str(exc))
        if selected is None:
            row.message("No ticker selected.")
            return
        symbol, provider = selected
        row.message(f"Testing {provider}:{symbol} against TakeProfit...")
        if args.local_chrome:
            from .local_chrome import LocalChromeAuth, open_chrome
            from .credential_store import CredentialStore, StoreError
            store = None
            if args.remember:
                try:
                    store = CredentialStore()
                except StoreError as exc:
                    print(str(exc) + " Continuing in memory only.")
            auth = LocalChromeAuth(store=store, opener=lambda: open_chrome(args.chrome_profile), ask=row.ask, emit=row.message)
        elif args.browser:
            from .browser_auth import BrowserAuth
            auth = BrowserAuth(ask=row.ask, emit=row.message)
        else:
            auth = Auth.prompt(session=args.session)
        with httpx.Client(http2=True, timeout=10, follow_redirects=False, trust_env=False) as client:
            monitor(auth, symbol, provider, args.interval, args.count, client, emit=row.sample, sleep=row.wait, notify=row.message)
    except AuthError as exc:
        row.message("Authorization: " + str(exc))
    except KeyboardInterrupt:
        row.finish()
        row.message("Monitor stopped.")
    finally:
        row.finish()
        if auth is not None:
            auth.close()


if __name__ == "__main__":
    main()
