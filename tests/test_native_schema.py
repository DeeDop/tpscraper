import unittest
from tpscraper.native_schema import (
    candle_request, history_request, quote_stream_request,
    candle_item, history_items, quote_item, integer, security)
from tpscraper.quote_schema import fields,message

def dec(n,scale=100):
    return integer(1,n)+integer(2,scale)

def fixture():
    return (message(1,integer(1,1795507200))+
            b"".join(message(i,dec(n)) for i,n in [(2,362000),(3,362150),(4,361900),(5,362100),(7,1234)]))

class NativeSchemaTests(unittest.TestCase):
    def test_history_and_candle_stream(self):
        bar=candle_item(message(2,fixture())+integer(6,1))
        self.assertTrue(bar["is_last"])
        self.assertEqual(bar["bar"]["c"],3621)
        self.assertEqual(bar["bar"]["v"],12.34)
        self.assertIsNone(bar["bar"]["buying_volume"])
        self.assertEqual(history_items(message(2,fixture()))["bars"],[bar["bar"]])
        self.assertEqual(candle_item(message(1,integer(1,7))),{"status":7})

    def test_request_fields(self):
        req=fields(candle_request("XAU/USD","FXPPST"))
        entry=fields(req[1][0][1])
        self.assertEqual(fields(entry[3][0][1])[2][0][1],360)
        hist=fields(history_request("XAU/USD","FXPPST",end=1795507200))
        self.assertEqual(fields(hist[3][0][1])[4][0][1],(1<<64)-360)

    def test_tagged_quote(self):
        pairs=[("XAU/USD","FXPPST"),("BTC/USDT","CXBNCE")]
        req=fields(quote_stream_request(pairs))
        self.assertEqual(len(req[1]),2)
        q=message(1,message(1,dec(362100))+message(5,integer(1,1795507200)))
        out=quote_item(message(1,message(2,q)+integer(4,1)),pairs)
        self.assertEqual(out["symbol"],"XAU/USD")
        self.assertEqual(out["main_session"]["last"],3621)
        self.assertEqual(out["main_session"]["exchange_timestamp"],1795507200)
        out=quote_item(message(1,message(2,q)+message(3,security(*pairs[1]))),pairs)
        self.assertEqual(out["symbol"],"BTC/USDT")
        with self.assertRaises(ValueError):
            quote_item(message(1,message(2,q)+integer(4,99)),pairs)
