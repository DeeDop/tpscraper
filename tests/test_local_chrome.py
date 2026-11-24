import base64
import json
import time
import unittest
from tpscraper.auth import AuthError
from tpscraper.local_chrome import LocalChromeAuth, parse_access

def token(exp):
    body = base64.urlsafe_b64encode(json.dumps({"exp":exp}).encode()).decode().rstrip("=")
    return "synthetic." + body + ".signature"

class LocalChromeTests(unittest.TestCase):
    def test_json(self):
        value=token(time.time()+900)
        self.assertEqual(parse_access(json.dumps({"success":True,"data":{"accessToken":value}})),value)

    def test_expired(self):
        with self.assertRaises(AuthError):
            parse_access(token(time.time()-1))

    def test_reject_headers(self):
        with self.assertRaises(AuthError):
            parse_access("Cookie: token="+token(time.time()+900))

    def test_consent(self):
        value=token(time.time()+900)
        answers=iter(["y","c"])
        calls=[]
        auth=LocalChromeAuth(ask=lambda _:next(answers),emit=lambda _:None,opener=lambda:calls.append("open"),clipboard=lambda:value)
        self.assertEqual(auth.headers(),{"accesstoken":value})
        self.assertEqual(auth.headers(),{"accesstoken":value})
        self.assertEqual(calls,["open"])
        auth.close()

    def test_decline(self):
        auth=LocalChromeAuth(ask=lambda _:"n",opener=lambda:self.fail("opened"),clipboard=lambda:self.fail("read"))
        with self.assertRaises(AuthError):
            auth.headers()
