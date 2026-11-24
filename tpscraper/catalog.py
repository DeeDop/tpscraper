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


# Browser directory: merge the existing instrument catalog and optional book list.
import csv
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from functools import lru_cache

ROOT=Path(__file__).resolve().parent.parent / "docs"

@lru_cache(maxsize=4)
def load_catalog():
    out={}
    for filename,kind in (("takeprofit_tickers.csv","catalog"),("orderbook_catalog.csv","orderbook")):
        path=ROOT/filename
        if not path.is_file():
            continue
        with path.open(encoding="utf-8-sig",newline="") as f:
            for raw in csv.DictReader(f):
                provider=raw.get("provider") or ""
                symbol=raw.get("symbol") or raw.get("ticker") or ""
                if not provider or not symbol:
                    continue
                key=provider+":"+symbol
                row=out.setdefault(key,{"input":key,"symbol":symbol,"provider":provider,"orderbook_listed":False})
                if kind=="orderbook":
                    row["orderbook_listed"]=True
                else:
                    row.update({k:v for k,v in raw.items() if v and k not in ("input","orderbook_listed")})
    return tuple(sorted(out.values(),key=lambda r:r["input"]))

def catalog_payload(path):
    q=parse_qs(urlsplit(path).query)
    query=q.get("q",[""])[0].casefold().strip()[:100]
    provider=q.get("provider",[""])[0].upper()[:40]
    try:
        limit=max(1,min(500,int(q.get("limit",["100"])[0])))
    except ValueError:
        limit=100
    rows=load_catalog()
    filtered=[r for r in rows if (not provider or r["provider"]==provider) and (not query or query in " ".join(str(v) for v in r.values()).casefold())]
    return {"total":len(rows),"matched":len(filtered),"instruments":filtered[:limit],
            "providers":sorted({r["provider"] for r in rows}),
            "source":"offline_catalog","live_availability_verified":False}
