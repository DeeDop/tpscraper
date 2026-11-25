"""Local HTTP and SSE interface for market data."""
import argparse
import json
import os
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
from . import __version__
from .workspace import load_workspace,save_workspace,preset_pairs,instruments_for


class LocalServer(ThreadingHTTPServer):
    daemon_threads=True

    def __init__(self,*args,**kwargs):
        self.slots=threading.BoundedSemaphore(16)
        super().__init__(*args,**kwargs)

    def process_request(self,request,client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.settimeout(1)
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request,client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self,request,client_address):
        try:
            super().process_request_thread(request,client_address)
        finally:
            self.slots.release()


class DashboardHandler(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"

    def __init__(self,state,stop,*args,**kwargs):
        self.state=state
        self.stop=stop
        super().__init__(*args,**kwargs)

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self,*args):
        pass

    def send_error(self,code,message=None,explain=None):
        self.close_connection=True
        body=json.dumps({"api_version":1,"error":{"status":code,"message":message or self.responses.get(code,("Request failed",))[0]}}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Cache-Control","no-store")
        self.send_header("Connection","close")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        if getattr(self,"command",None)!="HEAD":
            self.wfile.write(body)

    def send_body(self,body,kind):
        self.send_response(200)
        self.send_header("Content-Type",kind)
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("X-TPScraper-API-Version","1")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path!="/api/workspace":
            self.send_error(404)
            return
        expected=f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host")!=expected or self.headers.get("Origin")!="http://"+expected or self.headers.get("Content-Type")!="application/json":
            self.send_error(403)
            return
        try:
            length=int(self.headers.get("Content-Length","0"))
            if not 0<length<=8192:
                raise ValueError("Invalid workspace request size")
            self.connection.settimeout(5)
            pairs=save_workspace(json.loads(self.rfile.read(length))["pairs"])
        except (ValueError,TypeError,KeyError,OSError):
            self.send_error(400,"Invalid workspace or unable to save")
            return
        self.send_body(json.dumps({"saved":pairs,"restart_required":True}).encode(),"application/json")

    def do_GET(self):
        if self.headers.get("Host")!=f"127.0.0.1:{self.server.server_port}":
            self.send_error(403)
            return
        url=urlsplit(self.path)
        route=url.path
        query=parse_qs(url.query)
        if route in ("/","/index.html"):
            self.send_body((Path(__file__).parent/"static"/"dashboard.html").read_bytes(),"text/html; charset=utf-8")
            return
        if route=="/api/version":
            self.send_body(json.dumps({"api_version":1,"version":__version__}).encode(),"application/json")
            return
        if route=="/api/stream" or route=="/api/stream/quotes":
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
                    quotes_only=route=="/api/stream/quotes"
                    full=not quotes_only and now-last_full>=2
                    payload=self.state.snapshot(full)
                    if full:
                        last_full=now
                    event="full" if full else "tick"
                    if not quotes_only:
                        self.wfile.write(f"event: {event}\ndata: {json.dumps(payload,allow_nan=False)}\n\n".encode())
                    # Compatible quotes event for headless consumers.
                    self.wfile.write(("event: quotes\ndata: "+json.dumps(self.quote_payload(payload),allow_nan=False)+"\n\n").encode())
                    self.wfile.flush()
                    self.stop.wait(0.25)
            except (OSError,ValueError,TypeError):
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
            payload={"streams":self.state.diagnostic_snapshot() if hasattr(self.state,"diagnostic_snapshot") else {},
                     "process_id":os.getpid(),"python_threads":threading.active_count()}
        elif route=="/api/workspace":
            try:
                saved=load_workspace()
            except (ValueError,TypeError,KeyError,OSError):
                saved=None
            payload={"saved":saved,"active":[i.symbol for i in self.state.instruments],"presets":preset_pairs(),"max_instruments":12}
        elif route=="/api/catalog":
            payload=catalog_payload(self.path)
        elif route=="/api/quotes":
            payload=self.quote_payload(self.state.snapshot(False))
            key=query.get("key",[None])[0]
            if key is not None:
                if key not in payload["quotes"]:
                    self.send_error(404,"Unknown instrument key")
                    return
                payload["quotes"]={key:payload["quotes"][key]}
        elif route=="/api/instruments":
            payload={"instruments":[{"key":i.key,"symbol":i.symbol,"name":i.name,"group":i.group,"decimals":i.decimals} for i in self.state.instruments]}
        elif route=="/api/bars":
            key=query.get("key",[None])[0]
            period=query.get("resolution",["60"])[0]
            try:
                limit=int(query.get("limit",["360"])[0])
                if period not in ("30","60") or not 1<=limit<=1000 or not key:
                    raise ValueError()
            except ValueError:
                self.send_error(400,"Require key, resolution 30 or 60, limit 1-1000")
                return
            data=self.state.snapshot(True,with_analysis=False) if isinstance(self.state,NativeDashboardState) else self.state.snapshot(True)
            inst=next((i for i in data["instruments"] if i["key"]==key),None)
            if inst is None:
                self.send_error(404,"Unknown instrument key")
                return
            rows=inst.get("micro_bars" if period=="30" else "bars",[])
            if query.get("closed",["0"])[0]=="1":
                rows=[b for b in rows if b.get("closed") is True]
            payload={"key":key,"symbol":inst["symbol"],"resolution_seconds":int(period),"history_ready":inst.get("history_ready",False) if period=="60" else None,"bars":rows[-limit:],"generated_utc":data["generated_utc"]}
        elif route=="/api/health":
            data=self.state.snapshot(False)
            payload=dict(connected=data["connected"],mode=data["mode"],reason=data["reason"],
                         instruments=len(data["quotes"]),usable_count=sum(q["usable_short_term"] for q in data["quotes"].values()),
                         receiving=sum(q["status"] in ("LIVE","UNVERIFIED") for q in data["quotes"].values()),
                         history_ready=data.get("history_ready",0),
                         timestamped_live_count=sum(q.get("live_price_usable",False) for q in data["quotes"].values()),
                         fresh_book_count=sum(bool((q.get("orderflow") or {}).get("book",{}).get("fresh")) for q in data["quotes"].values()),
                         uptime_seconds=data.get("uptime_seconds"),process_id=os.getpid(),python_threads=threading.active_count())
        else:
            self.send_error(404)
            return
        try:
            body=json.dumps(payload,allow_nan=False).encode()
        except (ValueError,TypeError):
            self.send_error(503,"Market data snapshot unavailable")
            return
        self.send_body(body,"application/json")

    @staticmethod
    def quote_payload(payload):
        return dict(api_version=1,**{k:payload[k] for k in ("quotes","connected","mode","reason","generated_utc")})


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
    p.add_argument("--flow-budget",type=int,default=None,help="Maximum concurrent advanced subscriptions (default up to 12; choose 1-60 within provider limits)")
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
    renewal=p.add_mutually_exclusive_group()
    renewal.add_argument("--auto-renew","--browser-renew",dest="auto_renew",action="store_true",help="Authorize via the Chrome extension (persistent pairing on Windows)")
    p.add_argument("--reset-pairing",action="store_true",help="Replace local Chrome pairing; requires --auto-renew")
    p.add_argument("--chrome-profile")
    p.add_argument("--ticker",action="append",default=[],help="Override preset with repeatable PROVIDER:TICKER values")
    p.add_argument("--workspace",action="store_true",help="Use watchlist saved from the dashboard; fallback to selected preset if none exists")
    args=p.parse_args(argv)
    if not 1<=args.requests_per_second<=3 or not 1<=args.interval<=3600 or not 1<=args.history<=1440 or not 1024<=args.port<=65535:
        p.error("Invalid interval, port or history")
    if args.flow_budget is not None and not 1<=args.flow_budget<=60:
        p.error("--flow-budget must be 1-60")
    if args.refresh_capabilities and not args.orderflow:
        p.error("--refresh-capabilities requires --orderflow")
    if args.auto_renew and (args.snapshot or not args.authorized):
        p.error("Browser renewal requires native mode and --authorized")
    if args.reset_pairing and not args.auto_renew:
        p.error("--reset-pairing requires --auto-renew")
    if args.orderflow and (args.snapshot or not args.authorized):
        p.error("--orderflow requires native mode and --authorized")
    if args.record_flow and not args.orderflow:
        p.error("--record-flow requires --orderflow")
    instruments=WATCHLISTS[args.watchlist]
    if args.orderflow and args.watchlist=="gold" and not args.ticker:
        instruments=instruments+(Instrument("gold_perp","CXBNF8:XAU/USDT.P","Gold perpetual (Binance)","Gold flow",5,2),)
    if args.workspace and args.ticker:
        p.error("Choose --workspace or --ticker, not both")
    if args.workspace:
        try:
            saved=load_workspace()
            if saved is not None:
                instruments=instruments_for(saved)
        except (ValueError,TypeError,KeyError,OSError):
            p.error("Saved workspace is invalid or unreadable; repair it in the dashboard")
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
        state=NativeDashboardState(instruments,args.history,args.native_30s,args.orderflow,recorder,args.flow_budget or min(12,5*len(instruments)),args.refresh_capabilities)
    stop=threading.Event()
    server=None
    thread=None
    try:
        # Authorize on main thread, before starting server.
        if args.auto_renew:
            from .browser_renew import BrowserRenewAuth
            auth=BrowserRenewAuth(store=store,reset_pairing=args.reset_pairing)
        else:
            auth=LocalChromeAuth(store=store,opener=lambda:open_chrome(args.chrome_profile))
        auth.headers()
        handler=partial(DashboardHandler,state,stop)
        server=LocalServer((args.host,args.port),handler)
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
