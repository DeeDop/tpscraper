import tempfile
import time
import unittest
from pathlib import Path
from tpscraper.capabilities import CapabilityCache,SERVICES
from tpscraper.flow_state import FlowState,OrderBook,BookGap
from tpscraper.native_state import NativeDashboardState
from tpscraper.instruments import Instrument

class CapabilityTests(unittest.TestCase):
    def test_unknown_symbol_eligible_and_cache_expires(self):
        with tempfile.TemporaryDirectory() as d:
            now=[10000]
            c=CapabilityCache(Path(d)/"cap.json",clock=lambda:now[0])
            f=FlowState("CUSTOM:NEW")
            self.assertEqual(set(c.queue({"x":f})),{("x",k) for k in SERVICES})
            c.remember(f.symbol,"orderbook","no_data")
            self.assertNotIn(("x","orderbook"),c.queue({"x":f}))
            self.assertIn(("x","orderbook"),c.queue({"x":f},force=True))
            now[0]+=901
            self.assertIn(("x","orderbook"),c.queue({"x":f}))
    def test_live_trade_separate_from_quote(self):
        s=NativeDashboardState([Instrument("x","CUSTOM:NEW","New","Test",1)],orderflow=True)
        now=time.time()
        s.ingest_quote("x",{"main_session":{"last":100}},now)
        s.flows["x"].ingest("trades",[dict(time=now,price=101,quantity=2,side="buy",trade_id="a")],now)
        q=s.snapshot(False)["quotes"]["x"]
        self.assertEqual(q["last"],100)
        self.assertFalse(q["usable_short_term"])
        self.assertEqual(q["live_price"],101)
        self.assertTrue(q["live_price_usable"])
        self.assertEqual(q["live_price_source"],"timestamped_trade_event")
        s.flows["x"].status("trades","paused")
        self.assertFalse(s.snapshot(False)["quotes"]["x"]["live_price_usable"])
    def test_stale_event_not_fresh_even_on_recent_receipt(self):
        f=FlowState("CUSTOM:NEW")
        now=time.time()
        f.ingest("trades",[dict(time=now-10,price=101,quantity=2,side="buy")],now)
        self.assertFalse(f.snapshot(now)["latest_trade"]["fresh"])
    def test_book_gap_discards_quotes(self):
        b=OrderBook()
        now=time.time()
        row=dict(kind="snapshot",version=2,time=now,bid_levels=[dict(price=99,size=1)],ask_levels=[dict(price=100,size=2)])
        b.apply(row,now)
        self.assertTrue(b.summary(now)["fresh"])
        with self.assertRaises(BookGap):
            b.apply(dict(row,kind="update",version=4),now)
        self.assertIsNone(b.summary(now)["bid"])
    def test_empty_side_not_fresh(self):
        b=OrderBook()
        now=time.time()
        b.apply(dict(kind="snapshot",version=1,time=now,bid_levels=[],ask_levels=[dict(price=100,size=1)]),now)
        self.assertFalse(b.summary(now)["fresh"])

if __name__=="__main__":
    unittest.main()
