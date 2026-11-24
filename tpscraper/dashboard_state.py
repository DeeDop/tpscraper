"""TV-compatible dashboard state derived solely from received TP snapshots."""
import math
import threading
import time
from datetime import datetime, timezone
from collections import OrderedDict
from statistics import correlation


def utc(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def add_bar(bars, timestamp, price, period, limit):
    t = int(timestamp // period) * period
    if bars and t < next(reversed(bars)):
        return
    if t not in bars:
        if bars:
            bars[next(reversed(bars))]["closed"] = True
        bars[t] = dict(t=t, o=price, h=price, l=price, c=price, v=None, closed=False)
    else:
        b = bars[t]
        b.update(h=max(b["h"],price), l=min(b["l"],price), c=price)
    while len(bars)>limit:
        bars.popitem(last=False)


def returns(bars):
    out = {}
    prev = None
    for b in bars:
        if b["closed"]:
            if prev and b["t"]-prev["t"]==60 and min(b["c"],prev["c"])>0:
                out[b["t"]] = math.log(b["c"]/prev["c"])
            prev=b
    return out


class DashboardState:
    def __init__(self, instruments, history=360, interval=15):
        self.instruments=tuple(instruments)
        self.history=history
        self.interval=interval
        self.lock=threading.RLock()
        self.started=time.monotonic()
        self.running=True
        self.reason="starting"
        self.data={i.key:dict(last=None, first=None, received=None, ticks=0, changes=0,
                              outcome="awaiting_quote", details={}, latency_ms=None, bars=OrderedDict(), micro=OrderedDict()) for i in instruments}

    def ingest(self,key,result,now=None):
        now=time.time() if now is None else now
        with self.lock:
            row=self.data[key]
            row["outcome"]=result["outcome"]
            if row["outcome"]!="candidate_price_unverified":
                return False
            try:
                values=result["candidate_prices"]
                if len(values)!=1:
                    raise ValueError()
                p=float(values[0])
                if not math.isfinite(p):
                    raise ValueError()
            except (ValueError,TypeError,KeyError,OverflowError):
                row["outcome"]="ambiguous_price"
                return False
            if row["first"] is None:
                row["first"]=p
            if row["last"] is not None and row["last"]!=p:
                row["changes"]+=1
            detail = {}
            try:
                for k in ("open","high","low","prev_close","change","change_pct"):
                    v=float(result.get("candidate_details",{})[k])
                    if not math.isfinite(v):
                        raise ValueError()
                    detail[k]=v
            except (KeyError,ValueError,TypeError,OverflowError):
                detail={}
            row.update(last=p,received=now,ticks=row["ticks"]+1,details=detail,
                       latency_ms=round(result.get("elapsed_s",0)*1000))
            add_bar(row["bars"],now,p,60,self.history)
            add_bar(row["micro"],now,p,30,self.history*2)
            self.reason="receiving snapshots"
            return True

    def stop(self, reason):
        with self.lock:
            self.running=False
            self.reason=reason

    def snapshot(self,with_series=True):
        with self.lock:
            now=time.time()
            instruments=[]
            quotes={}
            for i in self.instruments:
                r=self.data[i.key]
                age=max(0,now-r["received"]) if r["received"] is not None else None
                fresh=age is not None and age<=max(5,self.interval*2)
                success=r["outcome"]=="candidate_price_unverified"
                status="warning" if success and fresh and self.running else "serious" if r["last"] is not None else "unknown"
                d=r["details"]
                checks=[
                    dict(id="feed",status=status,detail="Unverified snapshot" if success else r["outcome"]),
                    dict(id="fresh",status="warning" if fresh else "unknown",detail=f"Receipt {age:.1f}s ago; exchange time unknown" if age is not None else "No quote"),
                    dict(id="cross",status="unknown",detail="Independent candle feed not decoded"),
                    dict(id="range",status="warning" if d else "unknown",detail="Candidate session range consistent" if d else "Session range unavailable"),
                    dict(id="spread",status="unknown",detail="Bid/ask unavailable"),
                    dict(id="bars",status="warning" if r["bars"] else "unknown",detail="Local sampled bars only"),
                ]
                last,first=r["last"],r["first"]
                item=dict(key=i.key,symbol=i.symbol,name=i.name,group=i.group,slot=i.slot,decimals=i.decimals,
                          last=last,change=d.get("change",last-first if first is not None else None),
                          change_pct=d.get("change_pct",(last/first-1)*100 if first else None),
                          change_basis="candidate_session" if d else "since_start",
                          ticks=r["ticks"],status=status,checks=checks,delay_seconds=None,
                          update_mode="snapshot_unverified",bid=None,ask=None,open=d.get("open"),high=d.get("high"),low=d.get("low"),
                          prev_close=d.get("prev_close"),volume=None,range_position=(last-d["low"])/(d["high"]-d["low"]) if d and d["high"]>d["low"] else None,realized_vol_pct=None,bar_count=len(r["bars"]))
                if with_series:
                    item.update(bars=[dict(b) for b in r["bars"].values()],micro_bars=[dict(b) for b in r["micro"].values()])
                instruments.append(item)
                quotes[i.key]=dict(symbol=i.symbol,last=last,exchange_utc=None,
                    received_utc=utc(r["received"]) if r["received"] is not None else None,
                    price_age_s=None,receipt_age_s=age,update_mode="snapshot_unverified",
                    status="DISCONNECTED" if not self.running else "UNAVAILABLE" if not success else "UNVERIFIED" if fresh else "STALE",
                    usable_short_term=False, outcome=r["outcome"], latency_ms=r["latency_ms"], samples=r["ticks"], price_changes=r["changes"], candidate_details=dict(d))
            connected=self.running and any(q["status"]=="UNVERIFIED" for q in quotes.values())
            payload=dict(instruments=instruments,quotes=quotes,connected=connected,mode="snapshot_unverified",
                         reason=self.reason,generated_utc=utc(now),uptime_seconds=time.monotonic()-self.started)
            if with_series:
                keys=[i.key for i in self.instruments]
                rs=[returns(i["bars"]) for i in instruments]
                matrix=[]; counts=[]
                for a in rs:
                    mr=[]; cr=[]
                    for b in rs:
                        common=sorted(a.keys() & b.keys())
                        cr.append(len(common))
                        try:
                            mr.append(correlation([a[t] for t in common],[b[t] for t in common]) if len(common)>=10 else None)
                        except (ValueError,ZeroDivisionError):
                            mr.append(None)
                    matrix.append(mr); counts.append(cr)
                payload["correlation"]=dict(keys=keys,matrix=matrix,counts=counts)
            return payload
