import unittest
from tpscraper.feed import MarketDataFeed, Quote
from tpscraper.catalog import Catalog

class FeedTests(unittest.TestCase):
    def test_unverified(self):
        feed=MarketDataFeed()
        feed.publish("gold",Quote("XAU/USD",2000))
        self.assertFalse(feed.snapshot()["quotes"]["gold"]["usable_short_term"])

    def test_empty(self):
        self.assertEqual(MarketDataFeed().snapshot(),{"quotes":{}})

    def test_catalog(self):
        from tpscraper.catalog import Instrument
        c=Catalog(":memory:")
        c.add(Instrument("example","XAU/USD","Gold"))
        self.assertEqual(c.search("gold")[0]["entitlement"],"unverified")
        c.db.close()
