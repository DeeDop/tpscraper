"""Loopback HTTP contract tests; no upstream connection or credentials."""
from functools import partial
from http.client import HTTPConnection
import json
import threading
import unittest
from tpscraper.dashboard import DashboardHandler, LocalServer
from tpscraper.instruments import BTC

class State:
    instruments=BTC
    def snapshot(self,with_series=True):
        return {"connected":True,"mode":"native_push","reason":"test","generated_utc":"2026-01-01T00:00:00+00:00",
                "history_ready":1,"uptime_seconds":5,
                "quotes":{"btc":{"symbol":BTC[0].symbol,"last":100,"status":"UNVERIFIED",
                                  "usable_short_term":False,"live_price_usable":True,"live_price":101}},
                "instruments":[{"key":"btc","symbol":BTC[0].symbol,"history_ready":True,
                                "bars":[{"t":60,"o":100,"h":101,"l":99,"c":101,"closed":True},
                                        {"t":120,"o":101,"h":102,"l":100,"c":102,"closed":False}]}]}

class LocalApiTests(unittest.TestCase):
    def setUp(self):
        self.stop=threading.Event()
        self.server=LocalServer(("127.0.0.1",0),partial(DashboardHandler,State(),self.stop))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
    def tearDown(self):
        self.stop.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
    def get(self,path,headers=None):
        c=HTTPConnection("127.0.0.1",self.server.server_port,timeout=3)
        try:
            c.request("GET",path,headers=headers or {})
            r=c.getresponse()
            return r.status,json.loads(r.read())
        finally:
            c.close()
    def test_version(self):
        code,data=self.get("/api/version")
        self.assertEqual(code,200)
        self.assertEqual(data["api_version"],1)
    def test_single_quote_and_unknown(self):
        code,data=self.get("/api/quotes?key=btc")
        self.assertEqual(code,200)
        self.assertEqual(data["quotes"]["btc"]["live_price"],101)
        self.assertEqual(self.get("/api/quotes?key=missing")[0],404)
    def test_instruments(self):
        self.assertEqual(self.get("/api/instruments")[1]["instruments"][0]["key"],"btc")
    def test_bars(self):
        code,data=self.get("/api/bars?key=btc&closed=1&limit=1")
        self.assertEqual(code,200)
        self.assertEqual([b["t"] for b in data["bars"]],[60])
        self.assertEqual(self.get("/api/bars?key=btc&resolution=99")[0],400)
        self.assertEqual(self.get("/api/bars?key=missing")[0],404)
    def test_host_rejected(self):
        self.assertEqual(self.get("/api/quotes",{"Host":"external.example"})[0],403)
    def test_health(self):
        code,data=self.get("/api/health")
        self.assertEqual(code,200)
        self.assertEqual(data["timestamped_live_count"],1)
        self.assertEqual(data["usable_count"],0)
    def test_quotes_only_sse(self):
        c=HTTPConnection("127.0.0.1",self.server.server_port,timeout=3)
        try:
            c.request("GET","/api/stream/quotes")
            response=c.getresponse()
            self.assertEqual(response.status,200)
            self.assertEqual(response.readline().strip(),b"event: quotes")
            payload=response.readline().strip()
            self.assertTrue(payload.startswith(b"data: "))
            self.assertEqual(json.loads(payload[6:])["quotes"]["btc"]["live_price"],101)
            response.close()
        finally:
            c.close()

if __name__=="__main__":
    unittest.main()
