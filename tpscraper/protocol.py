import struct

def frame(payload: bytes) -> bytes:
    return struct.pack(">BI", 0, len(payload)) + payload

class Decoder:
    def __init__(self, max_size=16*1024*1024):
        self.buffer = bytearray()
        self.max_size = max_size

    def feed(self, chunk):
        self.buffer.extend(chunk)
        while len(self.buffer) >= 5:
            flags, size = struct.unpack_from(">BI", self.buffer)
            if flags not in (0, 1, 128, 129) or size > self.max_size:
                raise ValueError("Invalid frame")
            if len(self.buffer) < 5 + size:
                break
            payload = bytes(self.buffer[5:5+size])
            del self.buffer[:5+size]
            yield flags, payload

    def finish(self):
        if self.buffer:
            raise ValueError("Incomplete frame")
