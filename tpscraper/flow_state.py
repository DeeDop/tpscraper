"""Stateful market-flow features, separate from settlement/reference quotes."""
from collections import deque, OrderedDict
import math
import threading
import time

class BookGap(RuntimeError):
    pass

class OrderBook:
    def __init__(self):
        self.reset()

    def reset(self):
        self.bids={}; self.asks={}; self.version=None; self.timestamp=None
        self.received=None; self.synced=False; self.cached=None; self.computed=0.0

    def apply(self,row,now):
        v=row.get("version")
        if not isinstance(v,int) or v<=0:
            self.reset()
            raise BookGap("missing version")
        if row["kind"]=="snapshot":
            self.reset()
        elif not self.synced or v!=self.version+1:
            self.reset()
            raise BookGap("version gap")
        for dest,key in ((self.bids,"bid_levels"),(self.asks,"ask_levels")):
            for level in row[key]:
                p,q=level["price"],level["size"]
                if q is None:
                    self.reset()
                    raise BookGap("unknown level quantity")
                if q==0:
                    dest.pop(p,None)
                else:
                    dest[p]=q
        self.version=v
        self.timestamp=row.get("time")
        self.received=now
        self.synced=True

    def summary(self,now,depth=20):
        age=None if self.timestamp is None else now-self.timestamp
        fresh=self.synced and age is not None and -2<=age<=5 and self.received is not None and now-self.received<=5
        out=dict(synchronized=self.synced,fresh=bool(fresh),version=self.version,
                 exchange_timestamp=self.timestamp,age_s=age,bid=None,ask=None,spread=None,
                 bids=[],asks=[],imbalance={},bid_levels=len(self.bids),ask_levels=len(self.asks))
        if not fresh or not self.bids or not self.asks:
            out["fresh"]=False
            return out
        # Full depth is maintained, but only bounded levels/features leave the API.
        if self.cached is None or now-self.computed>=0.5:
            bids=sorted(self.bids.items(),reverse=True)
            asks=sorted(self.asks.items())
            bid,ask=bids[0][0],asks[0][0]
            if bid>=ask:
                self.cached=None
                out["fresh"]=False
                out["crossed"]=True
                return out
            mid=(bid+ask)/2
            im={}
            for bps in (1,5,10,25):
                radius=mid*bps/10000
                b=sum(q for p,q in bids if p>=mid-radius)
                a=sum(q for p,q in asks if p<=mid+radius)
                im[str(bps)]=dict(bid_volume=b,ask_volume=a,imbalance=(b-a)/(b+a) if b+a else None)
            self.cached=dict(bid=bid,ask=ask,spread=ask-bid,mid=mid,
                             bids=bids[:depth],asks=asks[:depth],imbalance=im,
                             feature_version=self.version,feature_timestamp=self.timestamp)
            self.computed=now
        out.update(self.cached)
        return out

class FlowState:
    def __init__(self,symbol):
        self.symbol=symbol
        self.units="tick_activity" if symbol.startswith(("FXPPST:","FXEXTS:")) else "provider_trade_quantity"
        self.lock=threading.RLock()
        self.book=OrderBook()
        self.trades=deque(maxlen=100000)
        self.ids=OrderedDict()
        self.profiles={}
        self.tpo={}
        self.heat={}
        self.states={}
        self.received={}
        self.trade_started=None
        self.duplicate_count=0
        self.unidentified_count=0
        self.version_gaps=0
        self.trade_evicted_at=None

    def status(self,kind,reason):
        with self.lock:
            self.states[kind]=reason
            if kind=="orderbook":
                self.book.reset()
            if kind=="trades":
                self.trades.clear()
                self.trade_started=None
                self.trade_evicted_at=None
            if kind=="footprint":
                self.profiles.clear()
            if kind=="tpo":
                self.tpo={}
            if kind=="heatmap":
                self.heat={}

    def ingest(self,kind,rows,now=None):
        now=time.time() if now is None else now
        if not rows:
            return
        with self.lock:
            for r in rows:
                if kind=="trades":
                    t=r.get("time")
                    if t is None or not now-300<=t<=now+2:
                        continue
                    ident=r.get("trade_id")
                    if ident is not None:
                        if ident in self.ids:
                            self.duplicate_count+=1
                            continue
                        self.ids[ident]=now
                        while len(self.ids)>200000:
                            self.ids.popitem(last=False)
                    else:
                        self.unidentified_count+=1
                    if self.trade_started is None:
                        self.trade_started=now
                    if len(self.trades)==self.trades.maxlen:
                        self.trade_evicted_at=now
                    self.trades.append(dict(r))
                elif kind=="orderbook":
                    try:
                        self.book.apply(r,now)
                    except BookGap:
                        self.version_gaps+=1
                        self.states[kind]="resynchronizing"
                        raise
                elif kind=="footprint":
                    t=r.get("start")
                    if t is not None and r.get("end") is not None:
                        self.profiles[t]=dict(r)
                        for key in sorted(self.profiles)[:-120]:
                            del self.profiles[key]
                elif kind=="heatmap":
                    t=r.get("time")
                    if t is not None:
                        self.heat[t]=dict(r)
                        for key in sorted(self.heat)[:-120]:
                            del self.heat[key]
                elif kind=="tpo":
                    if r["kind"]=="profile":
                        self.tpo=dict(r)
                    elif self.tpo and r.get("start")==self.tpo.get("start"):
                        self.tpo.update({k:v for k,v in r.items() if k!="kind"})
            self.states[kind]="receiving"
            self.received[kind]=now

    def snapshot(self,now=None,details=False):
        now=time.time() if now is None else now
        with self.lock:
            streams={}
            for k,v in self.states.items():
                age=None if k not in self.received else now-self.received[k]
                freshness="stale" if v=="receiving" and (age is None or age>5) else "live" if v=="receiving" else v
                streams[k]=dict(status=freshness,connection_status=v,receipt_age_s=age)
            recent=[r for r in self.trades if now-60<=r["time"]<=now+2]
            latest=max((r["time"] for r in recent),default=None)
            windows={}
            for seconds in (5,15,30,60):
                rows=[r for r in recent if r["time"]>=now-seconds]
                buy=sum(r["quantity"] for r in rows if r["side"]=="buy")
                sell=sum(r["quantity"] for r in rows if r["side"]=="sell")
                unknown=sum(r["quantity"] for r in rows if r["side"]=="unknown")
                complete=self.trade_started is not None and now-self.trade_started>=seconds and (self.trade_evicted_at is None or now-self.trade_evicted_at>=seconds)
                fresh=latest is not None and -2<=now-latest<=5 and self.states.get("trades")=="receiving"
                windows[str(seconds)]=dict(count=len(rows),buy_volume=buy,sell_volume=sell,unknown_volume=unknown,
                    delta=buy-sell,imbalance=(buy-sell)/(buy+sell) if buy+sell else None,
                    largest_quantity=max((r["quantity"] for r in rows),default=None),
                    complete=bool(complete and fresh),fresh=bool(fresh))
            fp=[self.profiles[t] for t in sorted(self.profiles)]
            closed=[r for r in fp if r["end"]<=now and r.get("delta") is not None]
            # Only the observed profile history, not a session-wide CVD.
            cvd=sum(r["delta"] for r in closed) if closed else None
            profile=fp[-1] if fp else None
            profile_fresh=bool(profile and profile["start"]<=now<profile["end"] and
                self.states.get("footprint")=="receiving" and now-self.received.get("footprint",0)<=5)
            book=self.book.summary(now)
            out=dict(symbol=self.symbol,quantity_semantics=self.units,streams=streams,trade_windows=windows,
                     latest_trade_timestamp=latest,duplicates=self.duplicate_count,
                     unidentified=self.unidentified_count,book_gaps=self.version_gaps,book=book,
                     footprint=dict(latest={k:v for k,v in profile.items() if k!="levels"} if profile else None,
                         fresh=profile_fresh,closed_window_cvd=cvd,closed_profiles=len(closed)),
                     tpo=dict(self.tpo),heatmap=dict(buckets=len(self.heat)),
                     generated_epoch=now)
            if details:
                out["recent_trades"]=list(recent[-100:])
                out["footprint"]["profiles"]=fp[-30:]
                out["heatmap"]["profiles"]=[self.heat[t] for t in sorted(self.heat)[-30:]]
            return out
