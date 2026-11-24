"""Optional user-paired local browser renewal, for authorized first-party use.

This is not a public TakeProfit authentication API. The companion extension
requests a fresh access token through the normal signed-in browser session.
It does not inspect traffic, read cookies, or access Chrome's profile.
"""
import hmac
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .local_chrome import LocalChromeAuth, parse_access
from .auth import AuthError
from .credential_store import StoreError


class RenewalBridge:
    def __init__(self, port=8790):
        self.code=secrets.token_urlsafe(32)
        self.lock=threading.Lock()
        self.ready=threading.Event()
        self.pending=False
        self.token=None
        self.failure=False
        bridge=self

        class Handler(BaseHTTPRequestHandler):
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
                return (self.headers.get("Host")==f"127.0.0.1:{port}"
                        and hmac.compare_digest(actual.encode("utf-8"),expected.encode("utf-8")))

            def do_GET(self):
                if not self.permitted():
                    return self.reply(403,{"error":"not paired"})
                if self.path!="/status":
                    return self.reply(404,{"error":"unknown route"})
                with bridge.lock:
                    needed=bridge.pending
                self.reply(200,{"renew":needed})

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
                    value=parse_access(data["accessToken"]) if self.path=="/token" else None
                except (ValueError,KeyError,TypeError,AuthError,OSError):
                    return self.reply(400,{"error":"invalid renewal response"})
                with bridge.lock:
                    if not bridge.pending:
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
            self.ready.clear()
            self.pending=True
            self.token=None
            self.failure=False
        self.ready.wait(timeout)
        with self.lock:
            self.pending=False
            value=self.token
            self.token=None
            failed=self.failure
        if not value:
            raise AuthError("Browser renewal denied or sign-in expired." if failed else
                            "Browser renewal timed out. Check the paired Chrome extension and signed-in account.")
        return value

    def close(self):
        with self.lock:
            self.pending=False
            self.token=None
            self.ready.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class BrowserRenewAuth(LocalChromeAuth):
    def __init__(self,store=None,port=8790,**kwargs):
        super().__init__(store=store,**kwargs)
        self.bridge=RenewalBridge(port)
        self.emit("Pair the TakeProfit Renewal extension once for this process.")
        self.emit("Local pairing code (not an access token): "+self.bridge.code)
        self.emit("Keep Chrome signed in. Renewal will stop if TakeProfit denies access.")

    def refresh(self):
        self._access=None
        self.emit("Requesting fresh authorization from paired Chrome...")
        self._access=self.bridge.request()
        self.renewals+=1
        if self.store is not None:
            try:
                self.store.save(self._access)
            except StoreError:
                self.emit("Encrypted storage unavailable; using memory only.")
        self.emit("Browser authorization renewed; reconnecting streams.")
        return self._access

    def close(self):
        super().close()
        self.bridge.close()
