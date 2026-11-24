import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from decimal import Decimal
from tpscraper.console import format_sample, monitor

def result(price="3622.51"):
    return {"outcome":"candidate_price_unverified","symbol":"XAU/USD","provider":"FXPPST","candidate_prices":[price],"elapsed_s":0.546}

class ConsoleTests(unittest.TestCase):
    def test_delta(self):
        line, price = format_sample(result(),Decimal("3622.50"),datetime(2026,11,24,7,4,52,tzinfo=timezone.utc))
        self.assertIn("UP +0.01",line)
        self.assertIn("546 ms",line)
        self.assertIn("UNVERIFIED",line)
        self.assertEqual(price,Decimal("3622.51"))

    def test_ambiguous(self):
        sample=result()
        sample["candidate_prices"].append("1")
        line, price=format_sample(sample)
        self.assertIn("AMBIGUOUS",line)
        self.assertIsNone(price)

    @patch("tpscraper.console.probe")
    def test_stop_on_denial(self, probe):
        probe.return_value=dict(result(),outcome="access_denied",http_status=403)
        lines=[]
        self.assertEqual(monitor(None,"XAU/USD","FXPPST",emit=lines.append,sleep=lambda _:None),1)
        self.assertIn("403",lines[0])

    @patch("tpscraper.console.probe")
    def test_repeated(self, probe):
        probe.side_effect=[result(),result("3622.49")]
        lines=[]
        sleeps=[]
        self.assertEqual(monitor(None,"XAU/USD","FXPPST",count=2,emit=lines.append,sleep=sleeps.append),2)
        self.assertEqual(sleeps,[15])
        self.assertIn("DOWN -0.02",lines[1])

    @patch("tpscraper.console.probe")
    def test_backoff(self, probe):
        probe.return_value=dict(result(),outcome="probe_error")
        sleeps=[]
        self.assertEqual(monitor(None,"XAU/USD","FXPPST",emit=lambda _:None,sleep=sleeps.append),3)
        self.assertEqual(sleeps,[30,60])
