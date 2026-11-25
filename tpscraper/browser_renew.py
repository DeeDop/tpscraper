"""Optional user-paired local browser renewal, for authorized first-party use.

This is not a public TakeProfit authentication API. The companion extension
requests a fresh access token through the normal signed-in browser session.
It does not inspect traffic, read cookies, or access Chrome's profile.
"""
import hmac
import json
import secrets
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .local_chrome import LocalChromeAuth, parse_access
from .auth import AuthError, expires_at
from .credential_store import StoreError, CredentialStore, default_path


class RenewalBridge:
    def __init__(self, port=8790, code=None):
        self.code=code or secrets.token_urlsafe(32)
        self.request_id=None
        self.closed=False
        self.lock=threading.Lock()
        self.ready=threading.Event()
        self.pending=False
        self.request_in_progress=False
        self.token=None
        self.failure=False
        self.status_checks=0
        self.last_status_at=None
        bridge=self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(5)

            def log_message(self,*args):
                pass

            def reply(self,status,data):
                body=json.dumps(data).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type","application/json")
                self.send_header("Cache-Control","no-store")
                self.send_header("Content-Length",str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def permitted(self):
                expected="Bearer "+bridge.code
                actual=self.headers.get("Authorization","")
                return (self.headers.get("Host")==f"127.0.0.1:{bridge.server.server_port}"
                        and hmac.compare_digest(actual.encode("utf-8"),expected.encode("utf-8")))

            def do_GET(self):
                if not self.permitted():
                    return self.reply(403,{"error":"not paired"})
                if self.path!="/status":
                    return self.reply(404,{"error":"unknown route"})
                with bridge.lock:
                    bridge.status_checks+=1
                    bridge.last_status_at=time.monotonic()
                    needed=bridge.pending
                    request_id=bridge.request_id if needed else None
                self.reply(200,{"renew":needed,"request_id":request_id})

            def do_POST(self):
                if not self.permitted():
                    return self.reply(403,{"error":"not paired"})
                if self.path not in ("/token","/failure"):
                    return self.reply(404,{"error":"unknown route"})
                try:
                    n=int(self.headers.get("Content-Length","0"))
                    if not 0<n<=40000 or self.headers.get("Content-Type")!="application/json":
                        raise ValueError()
                    self.connection.settimeout(5)
                    data=json.loads(self.rfile.read(n))
                    request_id=data["request_id"]
                    value=parse_access(data["accessToken"]) if self.path=="/token" else None
                except (ValueError,KeyError,TypeError,AuthError,OSError):
                    return self.reply(400,{"error":"invalid renewal response"})
                with bridge.lock:
                    if not bridge.pending or request_id!=bridge.request_id:
                        return self.reply(409,{"error":"no renewal pending"})
                    bridge.token=value
                    bridge.failure=value is None
                    bridge.pending=False
                    bridge.ready.set()
                self.reply(200,{"accepted":True})

        self.server=ThreadingHTTPServer(("127.0.0.1",port),Handler)
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def request(self,timeout=100):
        with self.lock:
            if self.closed or self.request_in_progress:
                raise AuthError("Renewal bridge closed or busy.")
            self.request_in_progress=True
            self.ready.clear()
            self.request_id=secrets.token_urlsafe(24)
            self.pending=True
            self.token=None
            self.failure=False
        try:
            self.ready.wait(timeout)
            with self.lock:
                value=self.token
                failed=self.failure
                contacted=self.last_status_at is not None and time.monotonic()-self.last_status_at<=timeout+1
            if not value:
                if failed:
                    raise AuthError("Browser authorization refused or sign-in expired. Check the signed-in account; explicitly pair again after resolving access.")
                if contacted:
                    raise AuthError("Chrome contacted the local service but did not return valid authorization. Open the extension popup and check its status.")
                raise AuthError("No paired Chrome connection. Reload extension v1.2.0 or newer, disable old copies, and use --reset-pairing if the saved pairing is missing.")
            return value
        finally:
            with self.lock:
                self.pending=False
                self.request_in_progress=False
                self.token=None
                self.request_id=None

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed=True
            self.pending=False
            self.token=None
            self.ready.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def pairing_store():
    return CredentialStore(path=default_path().with_name("pairing.dpapi"))


def load_pairing(store, reset=False):
    """The pairing secret is independent of the provider credential."""
    value=None if reset else store.load()
    if value and re.fullmatch(r"[A-Za-z0-9_-]{43}",value):
        return value,False
    value=secrets.token_urlsafe(32)
    store.save(value)
    return value,True


class BrowserRenewAuth(LocalChromeAuth):
    def __init__(self,store=None,port=8790,reset_pairing=False,pair_store=None,**kwargs):
        super().__init__(store=store,**kwargs)
        # Always authenticate through the extension on startup; a cached provider
        # credential must not silently substitute for current browser consent.
        self._restore_attempted=True
        try:
            code,created=load_pairing(pair_store if pair_store is not None else pairing_store(),reset_pairing)
            persistent=True
        except StoreError:
            code,created=secrets.token_urlsafe(32),True
            persistent=False
        self.bridge=RenewalBridge(port,code=code)
        self.emit("Chrome authorization is required. Keep your signed-in browser open.")
        if created:
            self.emit("Pair the tpscraper extension: "+self.bridge.code)
        else:
            self.emit("Saved local pairing loaded. No new code is required.")
            self.emit("Open the extension popup and select Check connection now if Chrome has not connected.")
        if not persistent:
            self.emit("Secure pairing storage unavailable; pair again next launch.")

    renewal_lead_seconds=75

    def refresh(self,timeout=100):
        self.emit("Requesting authorization from Chrome...")
        value=self.bridge.request(timeout=timeout)
        self._access=value
        self.renewals+=1
        if self.store is not None:
            try:
                self.store.save(value)
            except StoreError:
                self.emit("Encrypted access-token storage unavailable.")
        self.emit("Chrome authorization accepted.")
        return value

    def prepare_renewal(self):
        old=expires_at(self._access) if self._access else None
        timeout=min(65,max(1,old-time.time()-5)) if old is not None else 65
        value=self.refresh(timeout=timeout)
        if old is not None and expires_at(value)<=old:
            raise AuthError("Provider did not extend the token expiration.")

    def close(self):
        super().close()
        self.bridge.close()
