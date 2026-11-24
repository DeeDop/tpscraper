import unittest
from tpscraper.symbols import choose, matches

ROWS = [
    {"provider":"FXPPST","symbol":"XAU/USD"},
    {"provider":"FXEXTS","symbol":"XAU/USD"},
    {"provider":"CXBNCE","symbol":"BTC/USDT"},
    {"provider":"CXBNF8","symbol":"BTC/USDT.P"},
]

class SymbolsTests(unittest.TestCase):
    def test_unique_match_and_slash(self):
        self.assertEqual(choose("btcusdt", rows=ROWS, emit=lambda _:None),("BTC/USDT","CXBNCE"))

    def test_ambiguity_requires_selection(self):
        self.assertEqual(choose("XAU/USD", rows=ROWS, ask=lambda _:"2", emit=lambda _:None),("XAU/USD","FXEXTS"))

    def test_unknown_ticker_with_provider(self):
        self.assertEqual(choose("FXPPST:NEW.123", rows=[]),("NEW.123","FXPPST"))

    def test_unknown_ticker_interactive(self):
        answers=iter(["NEW.123","FXPPST"])
        self.assertEqual(choose(rows=[], ask=lambda _:next(answers), emit=lambda _:None),("NEW.123","FXPPST"))

    def test_exact_contract(self):
        self.assertEqual(len(matches("BTC/USDT.P",ROWS)),1)

    def test_cancel(self):
        self.assertIsNone(choose(rows=[],ask=lambda _:""))

    def test_conflicting_provider(self):
        with self.assertRaises(ValueError):
            choose("FXPPST:XAU/USD","FXEXTS",rows=ROWS)
