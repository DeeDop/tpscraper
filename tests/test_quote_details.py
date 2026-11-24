import unittest
from tpscraper.quote_schema import candidate_details, candidate_price

# Gold market-data response only; no headers or credentials.
BODY=bytes.fromhex("12e60112e1010a6e0a06089e8c1610641a0d08fdf3ffffffffffffff011064220d08d6ffffffffffffffff0110643206089e9c1610643a0608e3b91610644206088b871610644a080a0608a198161064520608904e10904e5a06089e8c161064620908f0f1f9d10810904e6a0908b8ecc5b3ba021064126b0a06089e8c1610641a0d08fdf3ffffffffffffff011064220d08d6ffffffffffffffff0110643206089e9c1610643a0608e3b91610644206088b871610644a080a0608a198161064520608904e10904e5a06089e8c16106462060894bd5910016a0908a4ef9e9bb30f10641a0208012001")

class DetailsTests(unittest.TestCase):
    def test_captured_fields(self):
        self.assertEqual(candidate_price(BODY),"3620.14")
        self.assertEqual(candidate_details(BODY),dict(open="3640.62",high="3678.43",low="3613.55",prev_close="3635.53",change="-15.39",change_pct="-0.42",candidate_volume="231935",candidate_turnover="843968323.12"))

    def test_incomplete(self):
        self.assertEqual(candidate_details(b""),{})
