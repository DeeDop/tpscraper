"""Loopback-only API; empty feed until an upstream adapter is validated."""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .feed import MarketDataFeed

def serve(port=8789, feed=None):
    feed = feed or MarketDataFeed()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?",1)[0]
            if path == "/api/stream":
                self.send_response(200)
                self.send_header("Content-Type","text/event-stream")
                self.send_header("Cache-Control","no-cache")
                self.end_headers()
                try:
                    while True:
                        self.wfile.write(("data: "+json.dumps(feed.snapshot())+"\n\n").encode())
                        self.wfile.flush()
                        time.sleep(1)
                except OSError:
                    pass
                return
            if path in ("/api/quotes","/api/snapshot"):
                payload = feed.snapshot()
            elif path == "/api/health":
                payload = {"service":"tpscraper","upstream_verified":False,"status":"UNVERIFIED"}
            else:
                self.send_error(404)
                return
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(("127.0.0.1",port),Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()

if __name__ == "__main__":
    serve()
