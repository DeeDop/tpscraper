"""Offline tests for saved watchlists."""
import tempfile
import unittest
from pathlib import Path
from tpscraper.workspace import validate_pairs,instruments_for,preset_pairs,load_workspace,save_workspace

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
