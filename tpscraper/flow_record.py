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
        self.db.commit()
        self.next_prune=0

    def write(self,flows):
        now=time.time()
        # Record features, not 60k raw depth levels per frame.
        try:
            with self.db:
                for key,f in flows.items():
                    b=dict(f["book"])
                    b.pop("bids",None); b.pop("asks",None)
                    row=dict(f,book=b)
                    self.db.execute("INSERT INTO features VALUES (?,?,?)",(now,key,json.dumps(row,allow_nan=False,separators=(",",":"))))
                if now>=self.next_prune:
                    self.db.execute("DELETE FROM features WHERE epoch<?",(now-7*86400,))
                    self.next_prune=now+3600
        except sqlite3.Error as exc:
            raise RuntimeError("local research journal write failed") from exc

    def close(self):
        self.db.close()
