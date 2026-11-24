"""Provider-neutral instrument catalog. Never invent entitlements."""
import sqlite3
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class Instrument:
    provider: str
    symbol: str
    description: str = ""
    asset_class: str = "unknown"
    entitlement: str = "unverified"

class Catalog:
    def __init__(self, path="catalog.sqlite3"):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS instruments (provider TEXT, symbol TEXT, description TEXT, asset_class TEXT, entitlement TEXT, PRIMARY KEY(provider,symbol))")

    def add(self, item):
        self.db.execute("INSERT OR REPLACE INTO instruments VALUES (?,?,?,?,?)", tuple(asdict(item).values()))
        self.db.commit()

    def search(self, query=""):
        q = "%" + query + "%"
        rows = self.db.execute("SELECT * FROM instruments WHERE symbol LIKE ? OR description LIKE ? OR provider LIKE ? ORDER BY provider,symbol LIMIT 500", (q,q,q))
        return [asdict(Instrument(*row)) for row in rows]
