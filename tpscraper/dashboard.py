"""Loopback dashboard and predictor API, backed by TakeProfit snapshot polling."""
import argparse
import json
import sqlite3
import threading
import time
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import httpx

from .__main__ import probe
from .dashboard_state import DashboardState
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
        route=self.path.split("?",1)[0]
        if route in ("/","/index.html"):
            self.send_body((Path(__file__).parent/"static"/"dashboard.html").read_bytes(),"text/html; charset=utf-8")
            return
        if route=="/api/stream":
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream")
            self.send_header("Cache-Control","no-cache")
            self.send_header("Connection","close")
            self.end_headers()
            self.close_connection=True
            last_full=-float("inf")
            try:
                while not self.stop.is_set():
                    now=time.monotonic()
                    full=now-last_full>=5
                    payload=self.state.snapshot(full)
                    if full:
                        last_full=now
                    event="full" if full else "tick"
                    self.wfile.write(f"event: {event}\ndata: {json.dumps(payload,allow_nan=False)}\n\n".encode())
                    # Compatible quotes event for headless consumers.
                    self.wfile.write(("event: quotes\ndata: "+json.dumps(self.quote_payload(payload),allow_nan=False)+"\n\n").encode())
                    self.wfile.flush()
                    self.stop.wait(1)
            except OSError:
                pass
            return
        if route=="/api/snapshot":
            payload=self.state.snapshot(True)
        elif route=="/api/quotes":
            payload=self.quote_payload(self.state.snapshot(False))
        elif route=="/api/health":
            data=self.state.snapshot(False)
            payload=dict(connected=data["connected"],mode=data["mode"],reason=data["reason"],
                         instruments=len(data["quotes"]),usable_count=0,
                         receiving=sum(q["status"]=="UNVERIFIED" for q in data["quotes"].values()))
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
    p.add_argument("--no-cache",action="store_true",help="Do not persist or restore local sampled bars")
    p.add_argument("--history",type=int,default=360,help="Local 1-minute bar retention")
    p.add_argument("--resolution",choices=("1",),default="1",help="Local base bars are one minute")
    p.add_argument("--no-browser",action="store_true")
    p.add_argument("--local-chrome",action="store_true",help="Regular Chrome authorization (default)")
    p.add_argument("--remember",action="store_true")
    p.add_argument("--chrome-profile")
    p.add_argument("--ticker",action="append",default=[],help="Override preset with repeatable PROVIDER:TICKER values")
    args=p.parse_args(argv)
    if not 1<=args.requests_per_second<=3 or not 1<=args.interval<=3600 or not 1<=args.history<=1440 or not 1024<=args.port<=65535:
        p.error("Invalid interval, port or history")
    instruments=WATCHLISTS[args.watchlist]
    if args.ticker:
        if len(args.ticker)>12:
            p.error("Maximum 12 instruments per process")
        items=[]
        for n,value in enumerate(args.ticker):
            if ":" not in value:
                p.error("Use PROVIDER:TICKER with --ticker")
            try:
                symbol,provider=choose(value)
            except ValueError as exc:
                p.error(str(exc))
            items.append(Instrument(f"custom{n+1}",f"{provider}:{symbol}",symbol,"Custom",n%9+1,5))
        instruments=tuple(items)
    store=None
    if args.remember:
        try:
            store=CredentialStore()
        except StoreError as exc:
            print(str(exc)+" Continuing in memory only.")
    auth=LocalChromeAuth(store=store,opener=lambda:open_chrome(args.chrome_profile))
    cache=None
    if not args.no_cache:
        try:
            cache=HistoryCache()
            cache.prune()
        except (OSError,sqlite3.Error):
            if cache is not None:
                cache.close()
            cache=None
            print("Local sample cache unavailable; continuing in memory.")
    try:
        state=DashboardState(instruments,args.history,max(args.interval,len(instruments)/args.requests_per_second),cache=cache)
    except (OSError,sqlite3.Error):
        if cache is not None:
            cache.close()
        cache=None
        state=DashboardState(instruments,args.history,max(args.interval,len(instruments)/args.requests_per_second))
    print(f"Restored {state.cached_bars} local one-minute bars; no exchange backfill yet.",flush=True)
    stop=threading.Event()
    server=None
    thread=None
    try:
        # Authorize on main thread, before starting server.
        auth.headers()
        handler=partial(DashboardHandler,state,stop)
        server=ThreadingHTTPServer((args.host,args.port),handler)
        server.daemon_threads=True
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        url=f"http://{args.host}:{args.port}/"
        print("TakeProfit dashboard:",url,flush=True)
        print(f"Snapshot polling; target sweep {max(args.interval,len(instruments)/args.requests_per_second):g}s; global cap {args.requests_per_second:g} requests/s. Unverified prices. Ctrl+C to stop.",flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        with httpx.Client(http2=True,timeout=10,follow_redirects=False,trust_env=False) as client:
            collect(state,auth,stop,args.interval,client,requests_per_second=args.requests_per_second)
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
        auth.close()
        if cache is not None:
            cache.close()

if __name__=="__main__":
    main()
