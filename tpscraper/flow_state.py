"""Stateful market-flow features, separate from settlement/reference quotes."""
from collections import deque, OrderedDict
import math
import heapq
from statistics import median
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
        self.changes=deque(maxlen=6000)

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
        changes={"bid_added":0.0,"bid_removed":0.0,"ask_added":0.0,"ask_removed":0.0}
        for dest,key,side in ((self.bids,"bid_levels","bid"),(self.asks,"ask_levels","ask")):
            for level in row[key]:
                p,q=level["price"],level["size"]
                # The captured client decimal conversion maps an omitted size to 0;
                # its order-book storage removes zero-size levels.
                if q is None:
                    q=0.0
                if row["kind"]=="update":
                    delta=q-dest.get(p,0.0)
                    changes[side+("_added" if delta>=0 else "_removed")]+=abs(delta)
                if q==0:
                    dest.pop(p,None)
                else:
                    dest[p]=q
        if row["kind"]=="update":
            self.changes.append((now,changes))
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
            bids=heapq.nlargest(depth,self.bids.items())
            asks=heapq.nsmallest(depth,self.asks.items())
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
                b=sum(q for p,q in self.bids.items() if p>=mid-radius)
                a=sum(q for p,q in self.asks.items() if p<=mid+radius)
                im[str(bps)]=dict(bid_volume=b,ask_volume=a,imbalance=(b-a)/(b+a) if b+a else None)
            walls={side:sorted(rows,key=lambda p:p[1],reverse=True)[:3] for side,rows in (("bids",bids),("asks",asks))}
            changes={k:sum(c[k] for t,c in self.changes if t>=now-15) for k in ("bid_added","bid_removed","ask_added","ask_removed")}
            self.cached=dict(bid=bid,ask=ask,spread=ask-bid,mid=mid,walls_top20=walls,depth_changes_15s=changes,
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
        self.latencies=deque(maxlen=4096)

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
                    self.trades.append(dict(r,received_epoch=now))
                    self.latencies.append(now-t)
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
            while self.trades and self.trades[0]["time"]<now-120:
                self.trades.popleft()
            recent=[r for r in self.trades if now-60<=r["time"]<=now+2]
            newest=max(recent,key=lambda r:(r["time"],r["received_epoch"]),default=None)
            latest=newest["time"] if newest else None
            trade_price=None
            if newest is not None:
                age=now-newest["time"]
                receipt_age=now-newest["received_epoch"]
                trade_price=dict(price=newest["price"],event_epoch=newest["time"],received_epoch=newest["received_epoch"],event_age_s=age,receipt_age_s=receipt_age,arrival_lag_s=newest["received_epoch"]-newest["time"],fresh=bool(self.states.get("trades")=="receiving" and -2<=age<=5 and 0<=receipt_age<=5))
            lag=sorted(self.latencies)
            latency=dict(count=len(lag),median_ms=median(lag)*1000 if lag else None,
                         p95_ms=lag[max(0,math.ceil(.95*len(lag))-1)]*1000 if lag else None,
                         max_ms=lag[-1]*1000 if lag else None)
            qties=sorted(r["quantity"] for r in recent if r["quantity"]>0)
            large_threshold=qties[max(0,math.ceil(.95*len(qties))-1)] if len(qties)>=30 else None
            large=[r for r in recent if large_threshold is not None and r["quantity"]>=large_threshold]
            oi=next((r["open_interest"] for r in reversed(recent) if r.get("open_interest") is not None),None)
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
                    price_change=rows[-1]["price"]-rows[0]["price"] if len(rows)>=2 else None,
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
                     latest_trade_timestamp=latest,latest_trade=trade_price,latency=latency,
                     open_interest=oi,large_trade_threshold=large_threshold,large_trade_count=len(large),
                     large_trade_buy_volume=sum(r["quantity"] for r in large if r["side"]=="buy") if large_threshold is not None else None,
                     large_trade_sell_volume=sum(r["quantity"] for r in large if r["side"]=="sell") if large_threshold is not None else None,
                     duplicates=self.duplicate_count,
                     unidentified=self.unidentified_count,book_gaps=self.version_gaps,book=book,
                     footprint=dict(latest={k:v for k,v in profile.items() if k!="levels"} if profile else None,
                         fresh=profile_fresh,closed_window_cvd=cvd,closed_profiles=len(closed)),
                     tpo={k:v for k,v in self.tpo.items() if k not in ("levels","block_infos")},heatmap=dict(buckets=len(self.heat)),
                     generated_epoch=now)
            if details:
                out["recent_trades"]=list(recent[-100:])
                out["tpo"]=dict(self.tpo)
                out["footprint"]["profiles"]=fp[-30:]
                out["heatmap"]["profiles"]=[self.heat[t] for t in sorted(self.heat)[-30:]]
            return out
