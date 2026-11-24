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
        self.started=None

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
                # The captured OrderBook worker maps missing Decimal to zero,
                # and its storage explicitly deletes zero-size delta levels.
                if q is None:
                    q=0.0
                if not math.isfinite(p) or p<=0 or not math.isfinite(q) or q<0:
                    self.reset()
                    raise BookGap("invalid level")
                if row["kind"]=="update":
                    delta=q-dest.get(p,0.0)
                    changes[side+("_added" if delta>=0 else "_removed")]+=abs(delta)
                if q==0:
                    dest.pop(p,None)
                else:
                    dest[p]=q
        if row["kind"]=="update":
            self.changes.append((now,changes))
        if self.started is None:
            self.started=now
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
        # Best prices must follow the current book, not the cached depth statistics.
        best_bid=max(self.bids)
        best_ask=min(self.asks)
        if best_bid>=best_ask:
            self.cached=None
            out["fresh"]=False
            out["crossed"]=True
            return out
        if self.cached is None or now-self.computed>=0.5 or self.cached["bid"]!=best_bid or self.cached["ask"]!=best_ask:
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
                             depth_changes_complete=bool(self.started is not None and now-self.started>=15 and (len(self.changes)<self.changes.maxlen or self.changes[0][0]<=now-15)),
                             bids=bids[:depth],asks=asks[:depth],imbalance=im,
                             feature_version=self.version,feature_timestamp=self.timestamp)
            self.computed=now
        out.update(self.cached)
        out["feature_age_s"]=None if self.cached["feature_timestamp"] is None else now-self.cached["feature_timestamp"]
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
            self.received.pop(kind,None)
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

    def pause(self):
        with self.lock:
            terminal={"restricted","disabled_until_restart","no_data","unavailable","unsupported",
                      "cached_no_data","cached_unavailable","cached_unsupported"}
            for kind,reason in tuple(self.states.items()):
                if reason not in terminal and "restriction" not in reason:
                    self.status(kind,"paused")

    def ingest(self,kind,rows,now=None):
        now=time.time() if now is None else now
        if not rows:
            return False
        with self.lock:
            accepted=False
            for r in rows:
                if kind=="trades":
                    t=r.get("time")
                    if t is None or not now-300<=t<=now+2 or not math.isfinite(r["price"]) or r["price"]<=0 or not math.isfinite(r["quantity"]) or r["quantity"]<0:
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
                    accepted=True
                elif kind=="orderbook":
                    try:
                        self.book.apply(r,now)
                        accepted=True
                    except BookGap:
                        self.version_gaps+=1
                        self.states[kind]="resynchronizing"
                        raise
                elif kind=="footprint":
                    t=r.get("start")
                    if t is not None and r.get("end") is not None:
                        self.profiles[t]=dict(r)
                        accepted=True
                        for key in sorted(self.profiles)[:-120]:
                            del self.profiles[key]
                elif kind=="heatmap":
                    t=r.get("time")
                    if t is not None:
                        self.heat[t]=dict(r)
                        accepted=True
                        for key in sorted(self.heat)[:-120]:
                            del self.heat[key]
                elif kind=="tpo":
                    if r["kind"]=="profile":
                        if r.get("start") is None or (self.tpo.get("start") is not None and r["start"]<self.tpo["start"]):
                            continue
                        self.tpo=dict(r)
                        self.tpo["rows_verified"]=bool(r.get("levels"))
                        accepted=True
                        self.tpo["levels"]=[dict(x) for x in r.get("levels",[])]
                        self.tpo["block_infos"]=list(r.get("block_infos",[]))
                    elif self.tpo and r.get("start")==self.tpo.get("start"):
                        self.tpo.update({k:v for k,v in r.items() if k not in ("kind","row_diffs","block_appends")})
                        accepted=True
                        # Matches the captured client storage: union newly visited
                        # block indexes and splice block metadata at its explicit index.
                        # Do not accumulate volume fields the client doesn't apply.
                        levels={x["price"]:dict(x) for x in self.tpo.get("levels",[]) if x["price"] is not None}
                        for diff in r.get("row_diffs",[]):
                            p=diff["price"]
                            if p is None:
                                continue
                            row=levels.setdefault(p,dict(price=p,block_indexes=[]))
                            row["block_indexes"]=sorted(set(row["block_indexes"])|set(diff["block_indexes"]))
                            # Snapshot volume may now be outdated.
                            row["buy_volume"]=row["sell_volume"]=None
                        self.tpo["levels"]=sorted(levels.values(),key=lambda x:x["price"])
                        infos=list(self.tpo.get("block_infos",[]))
                        for a in r.get("block_appends",[]):
                            index=a["index"]
                            end=index+len(a["offsets"])
                            if index>len(infos) or end>10000:
                                raise ValueError("TPO block metadata gap")
                            if len(infos)<end:
                                infos.extend([None]*(end-len(infos)))
                            infos[index:end]=a["offsets"]
                        self.tpo["block_infos"]=infos
                        self.tpo["price_rows"]=len(levels)
                        self.tpo["blocks"]=len(infos)
                        self.tpo["rows_verified"]=bool(levels)
                        self.tpo["volume_updates_verified"]=False
            if accepted:
                self.states[kind]="receiving"
                self.received[kind]=now
            return accepted

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
            recent=sorted((r for r in self.trades if now-60<=r["time"]<=now+2),key=lambda r:r["time"])
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
            large_threshold=qties[max(0,math.ceil(.95*len(qties))-1)] if len(qties)>=30 and self.units!="tick_activity" and qties[0]!=qties[-1] else None
            large=[r for r in recent if large_threshold is not None and r["quantity"]>=large_threshold]
            oi=next((r["open_interest"] for r in reversed(recent) if r.get("open_interest") is not None),None)
            windows={}
            for seconds in (5,15,30,60):
                rows=[r for r in recent if r["time"]>=now-seconds]
                buy=sum(r["quantity"] for r in rows if r["side"]=="buy")
                sell=sum(r["quantity"] for r in rows if r["side"]=="sell")
                unknown=sum(r["quantity"] for r in rows if r["side"]=="unknown")
                complete=self.trade_started is not None and now-self.trade_started>=seconds and (self.trade_evicted_at is None or now-self.trade_evicted_at>=seconds)
                fresh=bool(trade_price and trade_price["fresh"])
                windows[str(seconds)]=dict(count=len(rows),buy_volume=buy,sell_volume=sell,unknown_volume=unknown,
                    delta=buy-sell if rows else None,imbalance=(buy-sell)/(buy+sell) if buy+sell else None,
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
            if "orderbook" in streams and not book["fresh"] and streams["orderbook"]["status"]=="live":
                streams["orderbook"]["status"]="stale_or_unsynchronized"
            if "trades" in streams and not (trade_price and trade_price["fresh"]) and streams["trades"]["status"]=="live":
                streams["trades"]["status"]="stale_event_time"
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
                out["tpo"]["levels"]=[dict(x) for x in self.tpo.get("levels",[])]
                out["tpo"]["block_infos"]=list(self.tpo.get("block_infos",[]))
                out["footprint"]["profiles"]=fp[-30:]
                out["heatmap"]["profiles"]=[self.heat[t] for t in sorted(self.heat)[-30:]]
            return out
