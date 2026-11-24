"""Regression: human authorization time is not the network deadline."""
import unittest
from unittest.mock import patch
import httpx
from tpscraper.__main__ import probe
from tpscraper.protocol import frame
from tpscraper.quote_schema import message, varint


class TwoChunks(httpx.SyncByteStream):
    def __init__(self, payload):
        self.payload = payload

    def __iter__(self):
        yield self.payload[:3]
        yield self.payload[3:-21]
        yield self.payload[-21:]


class ProbeTimingTests(unittest.TestCase):
    def test_slow_human_authorization(self):
        clock = [100.0]

        class SlowAuth:
            renewals = 1

            def headers(self):
                clock[0] += 60
                return {"accesstoken": "synthetic"}

        value = b"\x08" + varint(362251) + b"\x10" + varint(100)
        for field in (1, 1, 2, 2):
            value = message(field, value)
        trailer = b"grpc-status: 0\r\n"
        payload = frame(value) + b"\x80" + len(trailer).to_bytes(4, "big") + trailer

        def handler(request):
            self.assertEqual(request.headers["accesstoken"], "synthetic")
            clock[0] += 0.25
            return httpx.Response(200, headers={"content-type": "application/grpc-web+proto"},
                                  stream=TwoChunks(payload))

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with patch("tpscraper.__main__.time.monotonic", side_effect=lambda: clock[0]):
                result = probe("quote", 10, SlowAuth(), client=client)

        self.assertEqual(result["outcome"], "candidate_price_unverified")
        self.assertEqual(result["grpc_status"], 0)
        self.assertEqual(result["candidate_prices"], ["3622.51"])
        self.assertEqual(result["authorization_elapsed_s"], 60)
        self.assertEqual(result["elapsed_s"], 0.25)
        self.assertFalse(result["prices_verified"])
