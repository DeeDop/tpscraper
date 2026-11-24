import unittest
import httpx
from tpscraper.auth import Auth, AuthError
from tpscraper.protocol import frame
from tpscraper.quote_schema import quote_request, candidate_price, message, varint

class QuoteAuthTests(unittest.TestCase):
    def test_request_matches_observed_shape(self):
        expected=bytes.fromhex("00000000190a170a1312110a075841552f55534412064658505053541001")
        self.assertEqual(frame(quote_request("XAU/USD","FXPPST")),expected)

    def test_candidate(self):
        value=b"\x08"+varint(4200123)+b"\x10"+varint(1000)
        for field in (1,1,2,2):
            value=message(field,value)
        self.assertEqual(candidate_price(value),"4200.123")

    def test_renewal(self):
        def handler(req):
            self.assertEqual(str(req.url),"https://takeprofit.com/api/auth/token")
            self.assertEqual(req.headers["cookie"],"token=synthetic-session")
            return httpx.Response(200,json={"success":True,"data":{"accessToken":"synthetic-access"}},headers={"Set-Cookie":"token=rotated-synthetic; Path=/; Secure; HttpOnly"})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            auth=Auth(session="synthetic-session",client=client)
            self.assertEqual(auth.headers(),{"accesstoken":"synthetic-access"})
            self.assertEqual(auth.renewals,1)
            self.assertEqual(auth.headers(),{"accesstoken":"synthetic-access"})
            auth.close()

    def test_denial(self):
        with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(403))) as client:
            auth=Auth(session="synthetic-session",client=client)
            with self.assertRaises(AuthError):
                auth.headers()
