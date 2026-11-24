import unittest
from tpscraper.quote_schema import candidate_details, candidate_price

# Public quote fields only, extracted from captured XAU/SGD response.
BODY=bytes.fromhex("12830212fe010a7c0a0808d1ce9d0210e8071a0e08d587ffffffffffffff0110e807220d08e0ffffffffffffffff011064320808eff89e0210e8073a0808ede2a10210e807420808f4989d0210e8074a0a0a0808fcc69e0210e807520608904e10904e5a0808d1ce9d0210e807620908f0bad8f30710904e6a0a08adddf6ee841d10e807127a0a0808d1ce9d0210e8071a0e08d587ffffffffffffff0110e807220d08e0ffffffffffffffff011064320808eff89e0210e8073a0808ede2a10210e807420808f4989d0210e8074a0a0a0808fcc69e0210e807520608904e10904e5a0808d1ce9d0210e807620608de8b6210016a0b08e6b6a890f3d90110e8071a0208012001")

class DetailsTests(unittest.TestCase):
    def test_captured_fields(self):
        self.assertEqual(candidate_price(BODY),"4679.505")
        self.assertEqual(candidate_details(BODY),dict(open="4701.295",high="4747.629",low="4672.628",prev_close="4694.908",change="-15.403",change_pct="-0.32"))

    def test_incomplete(self):
        self.assertEqual(candidate_details(b""),{})
