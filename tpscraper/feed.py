"""Thread-safe normalized snapshots, independent of the upstream provider."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import threading
import time
import math

@dataclass
class Quote:
    symbol: str
    last: float
    exchange_utc: str | None = None
    received_utc: str | None = None
    update_mode: str = "unverified"
    verified: bool = False

class MarketDataFeed:
    def __init__(self, stale_after=5.0):
        self.stale_after = stale_after
        self.lock = threading.RLock()
        self.quotes = {}

    def publish(self, key, quote):
        if not math.isfinite(quote.last):
            raise ValueError("Nonfinite price")
        with self.lock:
            row = asdict(quote)
            row["received_utc"] = datetime.now(timezone.utc).isoformat()
            self.quotes[key] = (row, time.monotonic())

    def snapshot(self):
        with self.lock:
            result = {}
            for key, (row, received) in self.quotes.items():
                age = time.monotonic()-received
                fresh = age <= self.stale_after
                exchange_age = None
                try:
                    stamp = datetime.fromisoformat(row["exchange_utc"].replace("Z","+00:00"))
                    exchange_age = (datetime.now(timezone.utc)-stamp).total_seconds()
                except (ValueError, TypeError, AttributeError):
                    pass
                usable = row["verified"] and fresh and exchange_age is not None and 0 <= exchange_age <= self.stale_after and row["update_mode"] == "live"
                result[key] = dict(row, price_age_s=exchange_age, receipt_age_s=age, status="LIVE" if usable else "STALE" if not fresh else "UNVERIFIED", usable_short_term=usable)
            return {"quotes":result}
