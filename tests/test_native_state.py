import unittest
import time
from tpscraper.native_state import NativeDashboardState
from tpscraper.instruments import GOLD

def bar(t,close=3620,volume=254,value=920056.58):
    return dict(t=t,o=3624.15,h=3624.15,l=3619.01,c=close,v=volume,value=value)

class NativeStateTests(unittest.TestCase):
    def test_history_does_not_create_live_quote(self):
        s=NativeDashboardState(GOLD)
        t=int(time.time()//60)*60-60
        s.ingest_bar("gold",60,{"bar":bar(t),"is_last":True})
        p=s.snapshot()
        self.assertEqual(p["history_ready"],1)
        self.assertIsNone(p["quotes"]["gold"]["last"])
        self.assertFalse(p["connected"])
        gold=next(i for i in p["instruments"] if i["key"]=="gold")
        self.assertEqual(gold["bars"][0]["v"],254)
        self.assertTrue(gold["bars"][0]["closed"])

    def test_cumulative_candle_is_replaced_not_added(self):
        s=NativeDashboardState(GOLD)
        t=int(time.time()//60)*60
        s.ingest_bar("gold",60,{"bar":bar(t,volume=200)})
        s.ingest_bar("gold",60,{"bar":bar(t,volume=237),"is_last":True})
        gold=next(i for i in s.snapshot()["instruments"] if i["key"]=="gold")
        self.assertEqual(len(gold["bars"]),1)
        self.assertEqual(gold["bars"][0]["v"],237)
        self.assertEqual(gold["bar_updates"],1)

    def test_quote_merges_session_but_not_timestamp(self):
        s=NativeDashboardState(GOLD)
        now=time.time()
        s.ingest_quote("gold",{"main_session":{"last":3620.29,"volume":243088,"exchange_timestamp":now}},now)
        s.ingest_quote("gold",{"main_session":{"last":3619.74}},now+0.1)
        q=s.snapshot()["quotes"]["gold"]
        self.assertEqual(q["last"],3619.74)
        self.assertEqual(q["main_session"]["volume"],243088)
        self.assertIsNone(q["exchange_utc"])
        self.assertFalse(q["usable_short_term"])
        s.ingest_quote("gold",{"main_session":{"volume":243089}},now+1)
        self.assertEqual(s.data["gold"]["received"],now+0.1)
        self.assertEqual(s.snapshot()["quotes"]["gold"]["samples"],2)

    def test_unavailable_isolated(self):
        s=NativeDashboardState(GOLD)
        s.ingest_quote("gold",{"main_session":{"last":3620.29}})
        s.ingest_quote("silver",{"status":5})
        p=s.snapshot()
        self.assertEqual(p["quotes"]["silver"]["status"],"UNAVAILABLE")
        self.assertTrue(p["connected"])
        s.stop("rate limit")
        self.assertFalse(s.snapshot()["connected"])

    def test_native_micro_separate(self):
        s=NativeDashboardState(GOLD,micro=True)
        t=int(time.time()//60)*60
        s.ingest_bar("gold",30,{"bar":bar(t),"is_last":True})
        p=s.snapshot()
        gold=next(i for i in p["instruments"] if i["key"]=="gold")
        self.assertEqual(len(gold["micro_bars"]),1)
        self.assertEqual(gold["bars"],[])
        self.assertTrue(p["micro_enabled"])
