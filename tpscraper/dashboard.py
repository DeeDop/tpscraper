"""Loopback dashboard and predictor API with native TakeProfit streams by default."""
import argparse
import json
import sqlite3
import threading
import time
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import httpx

from .__main__ import probe
from .dashboard_state import DashboardState
from .native_state import NativeDashboardState
from .native_collect import collect_native
from .flow_record import FlowRecorder
from .catalog import catalog_payload
from .history_cache import HistoryCache
from .instruments import WATCHLISTS, Instrument
from .local_chrome import LocalChromeAuth, open_chrome
from .credential_store import CredentialStore, StoreError
from .auth import AuthError
from .symbols import choose


class DashboardHandler(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"

    def __init__(self,state,stop,*args,**kwargs):
        self.state=state
        self.stop=stop
        super().__init__(*args,**kwargs)

    def log_message(self,*args):
        pass

    def send_body(self,body,kind):
        self.send_response(200)
        self.send_header("Content-Type",kind)
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url=urlsplit(self.path)
        route=url.path
        query=parse_qs(url.query)
        if route in ("/","/index.html"):
            self.send_body((Path(__file__).parent/"static"/"dashboard.html").read_bytes(),"text/html; charset=utf-8")
            return
        if route=="/api/stream":
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream")
            self.send_header("Cache-Control","no-cache")
            self.send_header("Connection","close")
            self.connection.settimeout(10)
            self.end_headers()
            self.close_connection=True
            last_full=-float("inf")
            try:
                while not self.stop.is_set():
                    now=time.monotonic()
                    full=now-last_full>=2
                    payload=self.state.snapshot(full)
                    if full:
                        last_full=now
                    event="full" if full else "tick"
                    self.wfile.write(f"event: {event}\ndata: {json.dumps(payload,allow_nan=False)}\n\n".encode())
                    # Compatible quotes event for headless consumers.
                    self.wfile.write(("event: quotes\ndata: "+json.dumps(self.quote_payload(payload),allow_nan=False)+"\n\n").encode())
                    self.wfile.flush()
                    self.stop.wait(0.25)
            except OSError:
                pass
            return
        if route=="/api/snapshot":
            payload=self.state.snapshot(True)
        elif route=="/api/orderflow":
            key=query.get("key",[None])[0]
            if key is not None and hasattr(self.state,"flows"):
                flow=self.state.flows.get(key)
                payload={"orderflow":{key:flow.snapshot(details=True)} if flow is not None else {}}
            else:
                payload={"orderflow":self.state.flow_snapshot(True)} if hasattr(self.state,"flow_snapshot") else {"orderflow":{}}
        elif route=="/api/diagnostics":
            payload={"streams":self.state.diagnostic_snapshot()} if hasattr(self.state,"diagnostic_snapshot") else {"streams":{}}
        elif route=="/api/catalog":
            payload=catalog_payload(self.path)
        elif route=="/api/quotes":
            payload=self.quote_payload(self.state.snapshot(False))
        elif route=="/api/health":
            data=self.state.snapshot(False)
            payload=dict(connected=data["connected"],mode=data["mode"],reason=data["reason"],
                         instruments=len(data["quotes"]),usable_count=sum(q["usable_short_term"] for q in data["quotes"].values()),
                         receiving=sum(q["status"] in ("LIVE","UNVERIFIED") for q in data["quotes"].values()),
                         history_ready=data.get("history_ready",0),
                         timestamped_live_count=sum(q.get("live_price_usable",False) for q in data["quotes"].values()),
                         fresh_book_count=sum(bool(q.get("orderflow",{}).get("book",{}).get("fresh")) for q in data["quotes"].values()),
                         uptime_seconds=data.get("uptime_seconds"))
        else:
            self.send_error(404)
            return
        self.send_body(json.dumps(payload,allow_nan=False).encode(),"application/json")

    @staticmethod
    def quote_payload(payload):
        return {k:payload[k] for k in ("quotes","connected","mode","reason","generated_utc")}


def collect(state,auth,stop,interval,client,request=probe,requests_per_second=1):
    failures=0
    retry_at={}
    ordered=sorted(state.instruments,key=lambda i: i.key!="gold")
    while not stop.is_set():
        started=time.monotonic()
        for inst in ordered:
            if stop.is_set():
                return
            if time.monotonic()<retry_at.get(inst.key,0):
                continue
            provider,symbol=inst.symbol.split(":",1)
            begin=time.monotonic()
            result=request("quote",10,auth,symbol,provider,client=client)
            state.ingest(inst.key,result)
            outcome=result["outcome"]
            if outcome in ("authorization_required","access_denied","rate_limited") or result.get("grpc_status") in (7,8,16):
                state.stop(outcome)
                print("Collection stopped:",outcome,"; restart after resolving authorization or provider limits.",flush=True)
                return
            if result.get("grpc_status") in (3,5,12) or outcome in ("response_unvalidated","unexpected_content_type"):
                # Do not repeatedly request unknown or unsupported instruments.
                retry_at[inst.key]=time.monotonic()+60
                print(inst.symbol,":",outcome,"(retry in 60s)",flush=True)
            if outcome=="probe_error":
                failures+=1
                if failures>=3:
                    state.stop("transport failures")
                    return
            else:
                failures=0
            # Explicit global rate cap; no bursts or concurrent requests.
            if stop.wait(max(0,1/requests_per_second-(time.monotonic()-begin))):
                return
        if stop.wait(max(0,interval-(time.monotonic()-started))):
            return


def main(argv=None):
    p=argparse.ArgumentParser(description="TakeProfit dashboard and read-only local API")
    p.add_argument("--watchlist",choices=WATCHLISTS,default="realtime")
    p.add_argument("--port",type=int,default=8789)
    p.add_argument("--host",choices=("127.0.0.1",),default="127.0.0.1")
    p.add_argument("--interval",type=float,default=15,help="Minimum seconds per full watchlist sweep")
    p.add_argument("--requests-per-second",type=float,default=1,help="Global sequential request cap (1–3; increase only if provider permits)")
    p.add_argument("--snapshot",action="store_true",help="Legacy polling mode instead of native streams")
    p.add_argument("--orderflow",action="store_true",help="Discover advanced market data for every requested instrument")
    p.add_argument("--flow-budget",type=int,default=None,help="Maximum concurrent advanced subscriptions (default all five services per entered ticker; set a lower limit if needed, 1-60)")
    p.add_argument("--refresh-capabilities",action="store_true",help="Retest cached unavailable capabilities once at startup")
    p.add_argument("--authorized",action="store_true",help="Confirm account/provider permission for additional programmatic subscriptions")
    p.add_argument("--record-flow",type=Path,help="Optional local SQLite feature journal")
    p.add_argument("--native-30s",action="store_true",help="Optional extra 30-second candle subscription per instrument")
    p.add_argument("--no-cache",action="store_true",help="Do not persist or restore local sampled bars")
    p.add_argument("--history",type=int,default=360,help="Requested native one-minute history count (default 360); legacy cache retention in minutes")
    p.add_argument("--resolution",choices=("1",),default="1",help="Local base bars are one minute")
    p.add_argument("--no-browser",action="store_true")
    p.add_argument("--local-chrome",action="store_true",help="Regular Chrome authorization (default)")
    p.add_argument("--remember",action="store_true")
    p.add_argument("--auto-renew",action="store_true",help="Optional paired Chrome renewal; only with provider permission")
    p.add_argument("--chrome-profile")
    p.add_argument("--ticker",action="append",default=[],help="Override preset with repeatable PROVIDER:TICKER values")
    args=p.parse_args(argv)
    if not 1<=args.requests_per_second<=3 or not 1<=args.interval<=3600 or not 1<=args.history<=1440 or not 1024<=args.port<=65535:
        p.error("Invalid interval, port or history")
    if args.flow_budget is not None and not 1<=args.flow_budget<=60:
        p.error("--flow-budget must be 1-60")
    if args.refresh_capabilities and not args.orderflow:
        p.error("--refresh-capabilities requires --orderflow")
    if args.auto_renew and (args.snapshot or not args.authorized):
        p.error("--auto-renew requires native mode and --authorized")
    if args.orderflow and (args.snapshot or not args.authorized):
        p.error("--orderflow requires native mode and --authorized")
    if args.record_flow and not args.orderflow:
        p.error("--record-flow requires --orderflow")
    instruments=WATCHLISTS[args.watchlist]
    if args.orderflow and args.watchlist=="gold" and not args.ticker:
        instruments=instruments+(Instrument("gold_perp","CXBNF8:XAU/USDT.P","Gold perpetual (Binance)","Gold flow",5,2),)
    if args.ticker:
        if len(args.ticker)>12:
            p.error("Maximum 12 instruments per process")
        items=[]
        seen=set()
        for n,value in enumerate(args.ticker):
            if ":" not in value:
                p.error("Use PROVIDER:TICKER with --ticker")
            try:
                symbol,provider=choose(value)
            except ValueError as exc:
                p.error(str(exc))
            pair=f"{provider}:{symbol}"
            if pair in seen:
                continue
            seen.add(pair)
            items.append(Instrument(f"custom{len(items)+1}",pair,symbol,"Custom",len(items)%9+1,5))
        instruments=tuple(items)
    store=None
    if args.remember:
        try:
            store=CredentialStore()
        except StoreError as exc:
            print(str(exc)+" Continuing in memory only.")
    auth=None
    cache=None
    recorder=None
    if args.snapshot and not args.no_cache:
        try:
            cache=HistoryCache()
            cache.prune()
        except (OSError,sqlite3.Error):
            if cache is not None:
                cache.close()
            cache=None
            print("Local sample cache unavailable; continuing in memory.")
    if args.snapshot:
        try:
            state=DashboardState(instruments,args.history,max(args.interval,len(instruments)/args.requests_per_second),cache=cache)
        except (OSError,sqlite3.Error):
            if cache is not None:
                cache.close()
            cache=None
            state=DashboardState(instruments,args.history,max(args.interval,len(instruments)/args.requests_per_second))
        print(f"Restored {state.cached_bars} local one-minute bars.",flush=True)
    else:
        if args.history>1000 or (args.native_30s and args.history>500):
            p.error("Native history max 1000 minutes, or 500 with 30-second streams")
        if args.record_flow:
            try:
                recorder=FlowRecorder(args.record_flow)
            except (OSError,sqlite3.Error):
                p.error("Could not open local feature journal")
        state=NativeDashboardState(instruments,args.history,args.native_30s,args.orderflow,recorder,args.flow_budget or min(60,5*len(instruments)),args.refresh_capabilities)
    stop=threading.Event()
    server=None
    thread=None
    try:
        # Authorize on main thread, before starting server.
        if args.auto_renew:
            from .browser_renew import BrowserRenewAuth
            auth=BrowserRenewAuth(store=store)
        else:
            auth=LocalChromeAuth(store=store,opener=lambda:open_chrome(args.chrome_profile))
        auth.headers()
        handler=partial(DashboardHandler,state,stop)
        server=ThreadingHTTPServer((args.host,args.port),handler)
        server.daemon_threads=True
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        url=f"http://{args.host}:{args.port}/"
        print("TakeProfit dashboard:",url,flush=True)
        if args.snapshot:
            print(f"Legacy snapshot polling; target sweep {max(args.interval,len(instruments)/args.requests_per_second):g}s. Ctrl+C to stop.",flush=True)
        else:
            print(f"Native push: {len(instruments)} instruments, {args.history} initial 1m bars per instrument, 30s={args.native_30s}. Ctrl+C to stop.",flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        if args.snapshot:
            with httpx.Client(http2=True,timeout=10,follow_redirects=False,trust_env=False) as client:
                collect(state,auth,stop,args.interval,client,requests_per_second=args.requests_per_second)
        else:
            collect_native(state,auth,stop)
        if not stop.is_set():
            print("Dashboard remains available for inspection; Ctrl+C to exit.",flush=True)
            while not stop.wait(1):
                pass
    except KeyboardInterrupt:
        print("\nStopped.")
    except (AuthError,OSError) as exc:
        print("Unable to start:",str(exc))
    finally:
        state.stop("stopped")
        stop.set()
        if server is not None:
            if thread is not None:
                server.shutdown()
            server.server_close()
        if auth is not None:
            auth.close()
        if cache is not None:
            cache.close()
        if recorder is not None and getattr(state,"recorder",None) is not None:
            recorder.close()

if __name__=="__main__":
    main()
