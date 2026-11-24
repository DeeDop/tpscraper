"""Optional compact local research journal; retains seven days of feature snapshots."""
import json
import sqlite3
import time
from pathlib import Path

class FlowRecorder:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.path,timeout=3)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS features (epoch REAL NOT NULL, instrument TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(epoch,instrument))")
        self.db.execute("CREATE TABLE IF NOT EXISTS quote_samples (epoch REAL NOT NULL, symbol TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(epoch,symbol))")
        self.db.execute("CREATE TABLE IF NOT EXISTS completed_bars (symbol TEXT NOT NULL, epoch REAL NOT NULL, observed_epoch REAL NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(symbol,epoch))")
        self.db.commit()
        self.latest_bar={}
        self.next_prune=0

    def write(self,flows,quotes=None,instruments=()):
        now=time.time()
        # Record features, not 60k raw depth levels per frame.
        try:
            with self.db:
                for key,f in flows.items():
                    b=dict(f["book"])
                    b.pop("bids",None); b.pop("asks",None)
                    row=dict(f,book=b)
                    self.db.execute("INSERT INTO features VALUES (?,?,?)",(now,key,json.dumps(row,allow_nan=False,separators=(",",":"))))
                for q in (quotes or {}).values():
                    row={k:v for k,v in q.items() if k!="orderflow"}
                    self.db.execute("INSERT OR REPLACE INTO quote_samples VALUES (?,?,?)",
                        (now,q["symbol"],json.dumps(row,allow_nan=False,separators=(",",":"))))
                for i in instruments:
                    symbol=i["symbol"]
                    latest=self.latest_bar.get(symbol,-1)
                    for bar in i.get("bars",()):
                        if not bar.get("closed") or bar["t"]<latest:
                            continue
                        self.db.execute("INSERT OR REPLACE INTO completed_bars VALUES (?,?,?,?)",
                            (symbol,bar["t"],now,json.dumps(bar,allow_nan=False,separators=(",",":"))))
                        self.latest_bar[symbol]=max(self.latest_bar.get(symbol,-1),bar["t"])
                if now>=self.next_prune:
                    self.db.execute("DELETE FROM features WHERE epoch<?",(now-7*86400,))
                    self.db.execute("DELETE FROM quote_samples WHERE epoch<?",(now-7*86400,))
                    self.db.execute("DELETE FROM completed_bars WHERE epoch<?",(now-7*86400,))
                    self.next_prune=now+3600
        except sqlite3.Error as exc:
            raise RuntimeError("local research journal write failed") from exc

    def write_snapshot(self,snapshot):
        self.write(snapshot.get("orderflow",{}),snapshot.get("quotes",{}),snapshot.get("instruments",()))

    def close(self):
        self.db.close()
