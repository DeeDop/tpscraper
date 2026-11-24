import os
import tempfile
import unittest
from pathlib import Path
from tpscraper.credential_store import CredentialStore, protect, unprotect
from tpscraper.local_chrome import LocalChromeAuth
import base64
import json
import time

def token(exp):
    return "synthetic."+base64.urlsafe_b64encode(json.dumps({"exp":exp}).encode()).decode().rstrip("=")+".signature"

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = CredentialStore(Path(self.tmp.name)/"auth"/"access.dpapi",encrypt=lambda b:b[::-1],decrypt=lambda b:b[::-1])

    def test_store_roundtrip(self):
        self.assertIsNone(self.store.load())
        self.store.save("synthetic")
        self.assertNotEqual(self.store.path.read_bytes(),b"synthetic")
        self.assertEqual(self.store.load(),"synthetic")
        self.store.clear()
        self.assertIsNone(self.store.load())

    def test_reuse_without_browser(self):
        value=token(time.time()+900)
        self.store.save(value)
        auth=LocalChromeAuth(store=self.store,ask=lambda _:self.fail("prompted"),emit=lambda _:None)
        self.assertEqual(auth.headers(),{"accesstoken":value})
        auth.close()

    def test_expired_replaced(self):
        self.store.save(token(time.time()-1))
        value=token(time.time()+900)
        answers=iter(["y","c"])
        auth=LocalChromeAuth(store=self.store,ask=lambda _:next(answers),emit=lambda _:None,opener=lambda:None,clipboard=lambda:value)
        self.assertEqual(auth.headers(),{"accesstoken":value})
        self.assertEqual(self.store.load(),value)
        auth.close()

    @unittest.skipUnless(os.name=="nt","Windows DPAPI only")
    def test_native_encryption(self):
        data=b"synthetic credential for test"
        ciphertext=protect(data)
        self.assertNotEqual(ciphertext,data)
        self.assertEqual(unprotect(ciphertext),data)
