import tempfile
import time
import unittest
from pathlib import Path
from tpscraper.history_cache import HistoryCache
from tpscraper.dashboard_state import DashboardState
from tpscraper.instruments import GOLD

class CacheTests(unittest.TestCase):
    def test_restore_without_live_quote(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"sample.sqlite3"
            cache=HistoryCache(path)
            s=DashboardState(GOLD,cache=cache)
            t=int(time.time()//60)*60-120
            for sec,price in [(0,10),(15,12),(45,9),(60,11)]:
                s.ingest("gold",{"outcome":"candidate_price_unverified","candidate_prices":[str(price)]},now=t+sec)
            cache.close()
            cache=HistoryCache(path)
            try:
                s=DashboardState(GOLD,cache=cache)
                p=s.snapshot()
                self.assertEqual(s.cached_bars,2)
                self.assertFalse(p["connected"])
                self.assertIsNone(p["quotes"]["gold"]["last"])
                gold=next(i for i in p["instruments"] if i["key"]=="gold")
                self.assertEqual(gold["bars"][0],dict(t=t,o=10,h=12,l=9,c=9,v=None,closed=True))
            finally:
                cache.close()

    def test_no_fabricated_gap(self):
        with tempfile.TemporaryDirectory() as root:
            cache=HistoryCache(Path(root)/"sample.sqlite3")
            try:
                for t in (60,240):
                    cache.save("FXPPST:XAU/USD",60,dict(t=t,o=10,h=10,l=10,c=10))
                self.assertEqual([b["t"] for b in cache.load("FXPPST:XAU/USD",60,10,now=300)],[60,240])
                self.assertEqual(cache.load("FXEXTS:XAU/USD",60,10,now=300),[])
            finally:
                cache.close()
