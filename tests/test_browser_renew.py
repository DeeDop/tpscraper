"""Offline tests: no real TakeProfit account or token used."""
import base64
import json
import threading
from unittest.mock import Mock
import time
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from tpscraper.browser_renew import RenewalBridge, load_pairing
from tpscraper.auth import AuthError

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.b=RenewalBridge(0)
        self.url=f"http://127.0.0.1:{self.b.server.server_port}"
        self.out=[]
    def tearDown(self):
        self.b.close()

    def req(self,path,body=None,paired=True):
        headers={"Authorization":"Bearer "+(self.b.code if paired else "wrong")}
        if body is not None:
            headers["Content-Type"]="application/json"
        with urlopen(Request(self.url+path,data=None if body is None else json.dumps(body).encode(),headers=headers),timeout=3) as r:
            return json.load(r)

    def start(self):
        def wait():
            try:
                self.out.append(self.b.request(timeout=3))
            except AuthError:
                self.out.append("denied")
        t=threading.Thread(target=wait)
        t.start()
        deadline=time.monotonic()+2
        while not self.req("/status")["renew"]:
            self.assertLess(time.monotonic(),deadline)
            time.sleep(.01)
        return t

    def test_unauthorized(self):
        with self.assertRaises(HTTPError) as cm:
            self.req("/status",paired=False)
        with cm.exception as response:
            self.assertEqual(response.code,403)

    def test_success_once(self):
        t=self.start()
        claim=base64.urlsafe_b64encode(json.dumps({"exp":time.time()+600}).encode()).decode().rstrip("=")
        token="eyJhbGciOiJub25lIn0."+claim+".test"
        request_id=self.req("/status")["request_id"]
        body={"accessToken":token,"request_id":request_id}
        with self.assertRaises(HTTPError) as cm:
            self.req("/token",dict(body,request_id="wrong"))
        with cm.exception as response:
            self.assertEqual(response.code,409)
        self.assertTrue(self.req("/token",body)["accepted"])
        t.join(4)
        self.assertEqual(self.out,[token])
        self.assertFalse(self.req("/status")["renew"])
        with self.assertRaises(HTTPError) as cm:
            self.req("/token",body)
        with cm.exception as response:
            self.assertEqual(response.code,409)

    def test_denied(self):
        t=self.start()
        self.req("/failure",{"request_id":self.req("/status")["request_id"]})
        t.join(4)
        self.assertEqual(self.out,["denied"])

class PairingTests(unittest.TestCase):
    def test_persistent_pairing(self):
        store=Mock()
        store.load.return_value=None
        first,created=load_pairing(store)
        self.assertTrue(created)
        store.save.assert_called_once_with(first)
        store.load.return_value=first
        self.assertEqual(load_pairing(store),(first,False))
        second,created=load_pairing(store,reset=True)
        self.assertTrue(created)
        self.assertNotEqual(first,second)

if __name__=="__main__":
    unittest.main()
