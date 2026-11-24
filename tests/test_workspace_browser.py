"""Offline tests for the optional dedicated browser and saved watchlists."""
import base64
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock
from tpscraper.auth import AuthError
from tpscraper.dedicated_chrome import DedicatedChromeAuth
from tpscraper.local_chrome import TOKEN_URL
from tpscraper.workspace import validate_pairs,instruments_for,preset_pairs,load_workspace,save_workspace

def token(exp):
    payload=base64.urlsafe_b64encode(json.dumps({"exp":exp}).encode()).decode().rstrip("=")
    return "eyJhbGciOiJub25lIn0."+payload+".test"

class DedicatedBrowserTests(unittest.TestCase):
    def test_decline(self):
        with self.assertRaises(AuthError):
            DedicatedChromeAuth(ask=lambda prompt:"n",emit=lambda msg:None)

    def make_auth(self,status=200):
        auth=DedicatedChromeAuth(ask=lambda prompt:"yes",emit=lambda msg:None)
        auth._context=Mock()
        response=auth._context.request.get.return_value
        response.status=status
        response.url=TOKEN_URL
        response.text.return_value=token(time.time()+600)
        return auth,response

    def test_exact_endpoint_no_redirects_and_disposal(self):
        auth,response=self.make_auth()
        try:
            self.assertEqual(auth.headers()["accesstoken"],response.text.return_value)
            auth._context.request.get.assert_called_once_with(TOKEN_URL,headers={"Accept":"application/json","Cache-Control":"no-cache"},max_redirects=0,timeout=15000)
            response.dispose.assert_called_once()
            self.assertEqual(auth.renewals,1)
        finally:
            auth.close()

    def test_denial_not_retried(self):
        auth,response=self.make_auth(403)
        try:
            with self.assertRaises(AuthError):
                auth.headers()
            auth._context.request.get.assert_called_once()
            response.dispose.assert_called_once()
        finally:
            auth.close()

    def test_renewal_requires_new_expiration(self):
        auth,response=self.make_auth()
        try:
            auth.headers()
            with self.assertRaises(AuthError):
                auth.prepare_renewal()
            response.text.return_value=token(time.time()+1200)
            auth.prepare_renewal()
        finally:
            auth.close()

class WorkspaceTests(unittest.TestCase):
    def test_preset_keys_preserved(self):
        rows=instruments_for(preset_pairs()["crypto15"])
        self.assertEqual([r.key for r in rows],["btc","eth","sol","xrp","doge","bnb","hype","near","zec"])

    def test_unknown_pair_stable_key(self):
        pair="CUSTOM:XYZ/USDT"
        self.assertEqual(instruments_for([pair])[0].key,instruments_for(["CXBNCE:BTC/USDT",pair])[1].key)

    def test_validation(self):
        for value in ([],["no-provider"],["TEST:ABC;invalid"],["TEST:A"]*13,{"pairs":[]},[1]):
            with self.assertRaises(ValueError):
                validate_pairs(value)
        self.assertEqual(validate_pairs(["TEST:A","TEST:A"]),["TEST:A"])

    def test_workspace_roundtrip(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/"workspace.json"
            self.assertIsNone(load_workspace(p))
            pairs=["CXBNCE:BTC/USDT","CUSTOM:X"]
            save_workspace(pairs,p)
            self.assertEqual(load_workspace(p),pairs)
            with self.assertRaises(ValueError):
                save_workspace([],p)
            self.assertEqual(load_workspace(p),pairs)

if __name__=="__main__":
    unittest.main()
