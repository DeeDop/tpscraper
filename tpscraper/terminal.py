"""Single-row terminal display with a local countdown (no extra network calls)."""
import math
import shutil
import sys
import time


class TerminalRow:
    def __init__(self, stream=None, clock=time.monotonic, sleep=time.sleep, width=None):
        self.stream = stream if stream is not None else sys.stdout
        self.clock = clock
        self.sleep = sleep
        self.width = width or (lambda: shutil.get_terminal_size((120, 24)).columns)
        self.enabled = self.stream.isatty()
        self.latest = ""
        self.drawn = 0

    def _write(self, text):
        self.stream.write(text)
        self.stream.flush()

    def _draw(self, text):
        if not self.enabled:
            return
        # Stay one column short of the terminal edge to avoid automatic wrapping.
        limit = max(1, self.width() - 1)
        text = text[:limit]
        padding = " " * max(0, min(self.drawn, limit) - len(text))
        self._write("\r" + text + padding + "\r" + text)
        self.drawn = len(text)

    def sample(self, line):
        self.latest = line
        if self.enabled:
            self._draw(line)
        else:
            self._write(line + "\n")

    def clear(self):
        if self.enabled and self.drawn:
            self._write("\r" + " " * min(self.drawn, max(1, self.width()-1)) + "\r")
        self.drawn = 0

    def message(self, line):
        self.clear()
        self._write(str(line) + "\n")

    def ask(self, prompt):
        self.clear()
        return input(prompt)

    def wait(self, seconds):
        if not self.enabled:
            self.sleep(seconds)
            return
        deadline = self.clock() + seconds
        while True:
            remaining = deadline - self.clock()
            if remaining <= 0:
                break
            # Countdown comes first so it remains visible on narrow terminals.
            self._draw(f"NEXT {math.ceil(remaining):02d}s | " + self.latest)
            self.sleep(min(1.0, remaining))
        self._draw("REQUESTING | " + self.latest)

    def finish(self):
        if self.enabled and self.drawn:
            self.clear()
            if self.latest:
                self._write(self.latest + "\n")
