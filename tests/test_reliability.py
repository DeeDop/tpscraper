"""Regression tests for stale data, reconnects and ambiguous provider data.
No real credentials or upstream network access.
"""
import time
import unittest
from tpscraper.flow_state import FlowState, OrderBook, BookGap
from tpscraper.native_state import NativeDashboardState
from tpscraper.instruments import BTC

def level(p,q):
    return dict(price=p,size=q)

def book(now,version=1,bids=None,asks=None,kind="snapshot"):
    return dict(time=now,version=version,kind=kind,
                bid_levels=[level(99,2)] if bids is None else bids,
                ask_levels=[level(101,3)] if asks is None else asks)

class ReliabilityTests(unittest.TestCase):
    def test_crossed_book_immediately_invalidates_cached_prices(self):
        b=OrderBook()
        b.apply(book(1000),1000)
        self.assertTrue(b.summary(1000)["fresh"])
        b.apply(book(1000.1,2,[level(102,1)],[],kind="update"),1000.1)
        self.assertFalse(b.summary(1000.1)["fresh"])
        self.assertIsNone(b.summary(1000.1)["bid"])

    def test_best_price_recomputed_before_cache_expiry(self):
        b=OrderBook()
        b.apply(book(1000),1000)
        self.assertEqual(b.summary(1000)["bid"],99)
        b.apply(book(1000.1,2,[level(100,1)],[],kind="update"),1000.1)
        self.assertEqual(b.summary(1000.1)["bid"],100)

    def test_omitted_size_removes_level_as_in_worker(self):
        b=OrderBook()
        b.apply(book(1000,bids=[level(99,2),level(98,3)]),1000)
        b.apply(book(1000.1,2,[level(99,None)],[],kind="update"),1000.1)
        self.assertEqual(b.summary(1000.1)["bid"],98)

    def test_explicit_zero_removes_level(self):
        b=OrderBook()
        b.apply(book(1000,bids=[level(99,2),level(98,3)]),1000)
        b.apply(book(1000.1,2,[level(99,0)],[],kind="update"),1000.1)
        self.assertEqual(b.summary(1000.1)["bid"],98)

    def test_duplicate_does_not_refresh_receipt(self):
        f=FlowState("TEST:BTC")
        r=dict(time=1000,price=99,quantity=1,side="buy",trade_id="1")
        self.assertTrue(f.ingest("trades",[r],1000))
        self.assertFalse(f.ingest("trades",[r],1004))
        self.assertEqual(f.received["trades"],1000)
        self.assertFalse(f.snapshot(1006)["latest_trade"]["fresh"])

    def test_out_of_order_trade_price_change(self):
        f=FlowState("TEST:BTC")
        f.ingest("trades",[dict(time=1000,price=101,quantity=1,side="buy"),
                           dict(time=999,price=99,quantity=1,side="buy")],1000)
        self.assertEqual(f.snapshot(1000)["trade_windows"]["5"]["price_change"],2)

    def test_history_ready_reset_on_reconnect(self):
        s=NativeDashboardState(BTC)
        now=int(time.time()//60)*60-60
        s.ingest_bar("btc",60,dict(bar=dict(t=now,o=99,h=101,l=98,c=100,v=1,value=100),is_last=True))
        self.assertEqual(s.snapshot(False)["history_ready"],1)
        s.bar_state("btc",60,"reconnecting")
        p=s.snapshot()
        self.assertEqual(p["history_ready"],0)
        self.assertEqual(len(p["instruments"][0]["bars"]),1)

    def test_old_quote_cannot_replace_session_fields(self):
        s=NativeDashboardState(BTC)
        now=time.time()
        s.ingest_quote("btc",{"main_session":{"last":100,"exchange_timestamp":now}},now)
        s.ingest_quote("btc",{"main_session":{"last":90,"exchange_timestamp":now-1}},now)
        q=s.snapshot(False)["quotes"]["btc"]
        self.assertEqual(q["last"],100)
        self.assertEqual(q["main_session"]["last"],100)

    def test_tpo_merges_block_indices_without_guessing_volume(self):
        f=FlowState("TEST:BTC")
        f.ingest("tpo",[dict(kind="profile",start=900,levels=[dict(price=99,block_indexes=[0])],block_infos=[0])],1000)
        f.ingest("tpo",[dict(kind="diff",start=900,poc=100,row_diffs=[dict(price=99,block_indexes=[0,1])],block_appends=[dict(index=1,offsets=[1800])])],1001)
        t=f.snapshot(1001,details=True)["tpo"]
        self.assertEqual(t["poc"],100)
        self.assertEqual(t["levels"][0]["block_indexes"],[0,1])
        self.assertEqual(t["block_infos"],[0,1800])
        self.assertFalse(t["volume_updates_verified"])
        self.assertIsNone(t["levels"][0]["buy_volume"])

    def test_disconnect_clears_eligible_book_and_trade(self):
        s=NativeDashboardState(BTC,orderflow=True)
        now=time.time()
        f=s.flows["btc"]
        f.ingest("orderbook",[book(now)],now)
        f.ingest("trades",[dict(time=now,price=100,quantity=1,side="buy")],now)
        self.assertTrue(s.snapshot(False)["quotes"]["btc"]["live_price_usable"])
        s.stop("test")
        q=s.snapshot(False)["quotes"]["btc"]
        self.assertFalse(q["live_price_usable"])
        self.assertIsNone(q["bid"])
        self.assertFalse(q["orderflow"]["book"]["fresh"])

if __name__=="__main__":
    unittest.main()
