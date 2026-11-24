import io
import unittest
from tpscraper.terminal import TerminalRow

class TTY(io.StringIO):
    def isatty(self):
        return True

class TerminalTests(unittest.TestCase):
    def test_same_line_and_countdown(self):
        out = TTY()
        clock = [0.0]
        def sleep(seconds):
            clock[0] += seconds
        row = TerminalRow(out, clock=lambda:clock[0], sleep=sleep, width=lambda:120)
        row.sample("3622.51 | UNVERIFIED")
        row.wait(15)
        row.sample("3622.52 | UNVERIFIED")
        self.assertNotIn("\n", out.getvalue())
        self.assertIn("NEXT 15s", out.getvalue())
        self.assertIn("NEXT 01s", out.getvalue())
        self.assertEqual(clock[0], 15)
        row.finish()
        self.assertTrue(out.getvalue().endswith("3622.52 | UNVERIFIED\n"))

    def test_redirected_output(self):
        out = io.StringIO()
        row = TerminalRow(out)
        row.sample("first")
        row.sample("second")
        row.finish()
        self.assertEqual(out.getvalue(),"first\nsecond\n")

    def test_message_clears_row(self):
        out = TTY()
        row = TerminalRow(out,width=lambda:80)
        row.sample("waiting")
        row.message("Authorization needed")
        self.assertTrue(out.getvalue().endswith("Authorization needed\n"))
        self.assertEqual(row.drawn,0)
