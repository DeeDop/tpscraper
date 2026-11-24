"""Persist receipt-time sample bars outside the repository.

This is not exchange history. No gaps are filled and no token is stored.
"""
import os
from pathlib import Path
import sqlite3
import math
import time


def default_path():
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()/".local"/"share")))
    return root/"tpscraper"/"marketdata"/"sample_bars.sqlite3"


class HistoryCache:
    def __init__(self,path=None):
        self.path=Path(path) if path is not None else default_path()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.path,timeout=5)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS sample_bars (
            symbol TEXT NOT NULL, period INTEGER NOT NULL, t INTEGER NOT NULL,
            o REAL NOT NULL,h REAL NOT NULL,l REAL NOT NULL,c REAL NOT NULL,
            PRIMARY KEY(symbol,period,t))""")
        self.db.commit()

    def save(self,symbol,period,bar):
        if period not in (30,60):
            raise ValueError("Invalid bar period")
        values=[float(bar[k]) for k in ("o","h","l","c")]
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Nonfinite bar")
        self.db.execute("""INSERT INTO sample_bars VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(symbol,period,t) DO UPDATE SET
              h=max(sample_bars.h,excluded.h),l=min(sample_bars.l,excluded.l),c=excluded.c""",
            (symbol,period,int(bar["t"]),*values))
        self.db.commit()

    def load(self,symbol,period,minutes,now=None):
        now=time.time() if now is None else now
        bucket=int(now//period)*period
        cutoff=int((now-minutes*60)//period)*period
        rows=self.db.execute("""SELECT t,o,h,l,c FROM sample_bars
            WHERE symbol=? AND period=? AND t>=? AND t<=? ORDER BY t""",
            (symbol,period,cutoff,bucket))
        return [dict(t=t,o=o,h=h,l=l,c=c,v=None,closed=t<bucket)
                for t,o,h,l,c in rows]

    def prune(self,days=7):
        self.db.execute("DELETE FROM sample_bars WHERE t<?",(int(time.time()-days*86400),))
        self.db.commit()

    def close(self):
        self.db.close()
