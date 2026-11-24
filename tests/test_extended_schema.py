import unittest
from tpscraper.extended_schema import plans, trade_rows, book_summary, footprint_rows, tpo_rows, renko_rows
from tpscraper.native_schema import integer, message, fields

def dec(n,scale=100):
    return integer(1,n)+integer(2,scale)

class ExtendedSchemaTests(unittest.TestCase):
    def test_trade(self):
        raw=message(1,message(4,dec(362000))+message(5,dec(150))+integer(6,2))
        self.assertEqual(trade_rows(raw)[0]["side"],"sell")
        self.assertEqual(trade_rows(raw)[0]["quantity"],1.5)

    def test_book_snapshot_vs_delta(self):
        raw=message(2,message(1,dec(362100))+message(2,dec(100)))+message(3,message(1,dec(362000))+message(2,dec(200)))
        self.assertEqual(book_summary(message(1,raw))[0]["spread"],1)
        self.assertNotIn("spread",book_summary(message(2,raw))[0])

    def test_footprint(self):
        raw=message(1,message(6,dec(150))+message(7,dec(250)))
        self.assertEqual(footprint_rows(raw)[0]["delta"],1)
        self.assertEqual(footprint_rows(message(3,dec(100))),[])

    def test_tpo_and_renko(self):
        self.assertEqual(tpo_rows(message(1,message(7,dec(362000))))[0]["poc"],3620)
        raw=message(2,message(2,message(3,dec(362000))+message(4,dec(362100))))
        self.assertEqual(renko_rows(raw)[0]["close"],3621)

    def test_request_structure(self):
        p=plans("BTC/USDT","CXBNCE",now=1795500000)
        self.assertEqual(len(p),9)
        self.assertEqual(list(fields(p["trades"][1])),[1])
        self.assertEqual(fields(p["heatmap"][1])[7][0][1],20)
        self.assertEqual(fields(p["footprint"][1])[4][0][1],1000)
