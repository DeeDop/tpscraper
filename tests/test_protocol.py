import unittest
from tpscraper.protocol import Decoder, frame

class ProtocolTests(unittest.TestCase):
    def test_split(self):
        d = Decoder()
        raw = frame(b"abc")
        self.assertEqual(list(d.feed(raw[:3])), [])
        self.assertEqual(list(d.feed(raw[3:])), [(0,b"abc")])
        d.finish()

    def test_multiple(self):
        self.assertEqual(list(Decoder().feed(frame(b"a")+frame(b"b"))), [(0,b"a"),(0,b"b")])

    def test_truncated(self):
        d=Decoder()
        list(d.feed(frame(b"abc")[:-1]))
        with self.assertRaises(ValueError):
            d.finish()

    def test_limit(self):
        with self.assertRaises(ValueError):
            list(Decoder(2).feed(frame(b"abc")))

if __name__ == "__main__":
    unittest.main()
