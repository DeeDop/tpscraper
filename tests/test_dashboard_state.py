import unittest
from tpscraper.dashboard_state import DashboardState
from tpscraper.instruments import GOLD, REALTIME, MARKETS15

class DashboardStateTests(unittest.TestCase):
    def test_presets(self):
        self.assertEqual(len(REALTIME),8)
        self.assertEqual(len(GOLD),9)
        self.assertEqual(len(MARKETS15),12)
        self.assertEqual(len({i.key for i in MARKETS15}),12)

    def test_empty_and_unverified(self):
        s=DashboardState(GOLD)
        self.assertEqual(len(s.snapshot()["quotes"]),9)
        self.assertFalse(s.snapshot()["connected"])
        self.assertTrue(s.ingest("gold",{"outcome":"candidate_price_unverified","candidate_prices":["3621.43"]}))
        p=s.snapshot()
        self.assertTrue(p["connected"])
        self.assertEqual(p["quotes"]["gold"]["last"],3621.43)
        self.assertIsNone(p["quotes"]["gold"]["exchange_utc"])
        self.assertFalse(p["quotes"]["gold"]["usable_short_term"])
        s.stop("rate_limited")
        self.assertFalse(s.snapshot()["connected"])

    def test_sample_bars(self):
        s=DashboardState(GOLD)
        for t,p in [(60,10),(75,12),(90,9),(120,11)]:
            s.ingest("gold",{"outcome":"candidate_price_unverified","candidate_prices":[str(p)]},now=t)
        gold=next(i for i in s.snapshot()["instruments"] if i["key"]=="gold")
        self.assertEqual(gold["bars"][0],dict(t=60,o=10,h=12,l=9,c=9,v=None,closed=True))
        self.assertEqual(len(gold["micro_bars"]),3)
        self.assertEqual(gold["change"],1)

    def test_bad_price(self):
        s=DashboardState(GOLD)
        self.assertFalse(s.ingest("gold",{"outcome":"candidate_price_unverified","candidate_prices":["NaN"]}))
        self.assertIsNone(s.snapshot()["quotes"]["gold"]["last"])

    def test_invalid_symbol_visible(self):
        s=DashboardState(GOLD)
        s.ingest("silver",{"outcome":"grpc_error","grpc_status":5})
        self.assertEqual(s.snapshot()["quotes"]["silver"]["status"],"UNAVAILABLE")
