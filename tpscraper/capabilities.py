"""Local capability hints, not entitlements. Unknown symbols remain eligible.
Cache only observations from authorized subscriptions; never cache credentials.
"""
import json
import os
import threading
import time
from pathlib import Path
from .catalog import load_catalog

SERVICES=("trades","orderbook","footprint","heatmap","tpo")
TTL={"observed":86400*7,"no_data":900,"unavailable":3600,"unsupported":86400}
class CapabilityCache:
    def __init__(self,path=None,clock=time.time):
        root=Path(os.environ.get("LOCALAPPDATA",str(Path.home()/".cache")))
        self.path=Path(path) if path is not None else root/"tpscraper"/"marketdata"/"capabilities.json"
        self.clock=clock
        self.lock=threading.RLock()
        self.rows={}
        self.directory={r["input"]:r for r in load_catalog()}
        try:
            raw=json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw,dict):
                self.rows={k:v for k,v in raw.items() if isinstance(v,dict)}
        except (OSError,ValueError):
            pass

    def lookup(self,symbol,kind):
        with self.lock:
            r=self.rows.get(symbol+"|"+kind,{})
            status=r.get("status")
            when=r.get("epoch")
            if status in TTL and isinstance(when,(float,int)) and 0<=self.clock()-when<TTL[status]:
                return status
            return "unknown"

    def remember(self,symbol,kind,status):
        if status not in TTL:
            return
        with self.lock:
            if self.lookup(symbol,kind)==status:
                return
            self.rows[symbol+"|"+kind]={"status":status,"epoch":self.clock()}
            try:
                self.path.parent.mkdir(parents=True,exist_ok=True)
                temp=self.path.with_name(self.path.name+".tmp")
                temp.write_text(json.dumps(self.rows,separators=(",",":")),encoding="utf-8")
                os.replace(temp,self.path)
            except OSError:
                pass

    def queue(self,flows,force=False):
        # Service-major order: every entered instrument has a chance at basic
        # trade/depth data before optional profile services occupy the budget.
        pending=[]
        for kind in SERVICES:
            for key,flow in flows.items():
                hint=self.lookup(flow.symbol,kind)
                if not force and hint in ("no_data","unsupported","unavailable"):
                    flow.status(kind,"cached_"+hint)
                    continue
                pending.append((key,kind))
                flow.status(kind,"queued")
        # Prefer previously successful streams and listed depth, but retain
        # round-robin service priority. Missing catalog entries never exclude.
        rank={k:n for n,k in enumerate(SERVICES)}
        pending.sort(key=lambda x:(rank[x[1]],
            self.lookup(flows[x[0]].symbol,x[1])!="observed",
            not (x[1] in ("orderbook","heatmap") and self.directory.get(flows[x[0]].symbol,{}).get("orderbook_listed"))))
        return pending
