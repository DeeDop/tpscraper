"""Native quote and candle dashboard state. History never masquerades as a quote."""
import math
import threading
import time
from statistics import correlation
from .dashboard_state import utc, returns


class NativeDashboardState:
    def __init__(self,instruments,history=360,micro=False):
        self.instruments=tuple(instruments)
        self.history=history
        self.micro=micro
        self.lock=threading.RLock()
        self.started=time.monotonic()
        self.running=True
        self.reason="connecting native streams"
        self.data={i.key:dict(sessions={},last=None,received=None,exchange=None,
                              ticks=0,changes=0,quote_state="connecting",
                              bars={},micro_bars={},bar_state={},ready=set(),bar_updates=0)
                   for i in self.instruments}

    def quote_state(self,key,reason):
        with self.lock:
            self.data[key]["quote_state"]=reason

    def all_quotes(self,reason):
        with self.lock:
            for row in self.data.values():
                row["quote_state"]=reason
            self.reason=reason

    def bar_state(self,key,period,reason):
        with self.lock:
            self.data[key]["bar_state"][period]=reason

    def ingest_quote(self,key,item,now=None):
        now=time.time() if now is None else now
        with self.lock:
            r=self.data[key]
            if item.get("status"):
                r["quote_state"]="provider status "+str(item["status"])
                return
            for name in ("main_session","daily_session"):
                if name in item:
                    r["sessions"].setdefault(name,{}).update(item[name])
            # Only a price in the current message refreshes receipt freshness.
            name="main_session" if "last" in r["sessions"].get("main_session",{}) else "daily_session"
            update=item.get(name,{})
            if "last" not in update:
                return
            p=update["last"]
            if not math.isfinite(p):
                return
            ts=update.get("exchange_timestamp")
            if ts is not None and (not math.isfinite(ts) or ts>now+2):
                ts=None
            if ts is not None and r["exchange"] is not None and ts<r["exchange"]:
                return
            r["changes"]+=int(r["last"] is not None and r["last"]!=p)
            r.update(last=p,received=now,exchange=ts,ticks=r["ticks"]+1,quote_state="receiving")
            self.reason="receiving native streams"

    def ingest_bar(self,key,period,item):
        with self.lock:
            r=self.data[key]
            if item.get("status"):
                r["bar_state"][period]="provider status "+str(item["status"])
                return
            b=item.get("bar")
            if b is not None:
                if not math.isfinite(b["t"]) or b["t"]>time.time()+2:
                    return
                target=r["bars" if period==60 else "micro_bars"]
                if b["t"] in target:
                    r["bar_updates"]+=1
                # Stream delivers complete replacement candle, not incremental volume.
                target[b["t"]]=dict(b)
                limit=self.history*(2 if period==30 else 1)
                if len(target)>limit:
                    for t in sorted(target)[:len(target)-limit]:
                        del target[t]
            if item.get("is_last"):
                r["ready"].add(period)
            r["bar_state"][period]="receiving" if period in r["ready"] else "loading history"

    def stop(self,reason):
        with self.lock:
            self.running=False
            self.reason=reason

    @staticmethod
    def series(target,period,now):
        return [dict(target[t],closed=t+period<=now) for t in sorted(target)]

    def snapshot(self,with_series=True):
        with self.lock:
            now=time.time()
            instruments=[]; quotes={}
            for i in self.instruments:
                r=self.data[i.key]
                age=None if r["received"] is None else max(0,now-r["received"])
                ex_age=None if r["exchange"] is None else max(0,now-r["exchange"])
                fresh=bool(self.running and r["quote_state"]=="receiving" and age is not None and age<=5)
                # The price timestamp was absent in the successful probes.
                # No receipt-only price is declared predictor-safe.
                eligible=bool(fresh and ex_age is not None and ex_age<=5)
                state="DISCONNECTED" if not self.running else "LIVE" if eligible else "UNVERIFIED" if fresh else "STALE" if r["last"] is not None else "UNAVAILABLE"
                severity="good" if eligible else "warning" if fresh else "serious" if r["last"] is not None else "unknown"
                d=r["sessions"].get("main_session",{})
                if "last" not in d:
                    d=r["sessions"].get("daily_session",{})
                last=r["last"]
                bars=r["bars"]
                latest=bars[max(bars)] if bars else None
                same_bar=latest is not None and r["received"] is not None and latest["t"]<=r["received"]<latest["t"]+60
                cross="Awaiting aligned quote and candle"
                cross_status="unknown"
                if same_bar and fresh:
                    inside=latest["l"]<=last<=latest["h"]
                    cross=f"Quote {'inside' if inside else 'outside'} current candle (asynchronous)"
                    cross_status="good" if inside else "warning"
                low,high=d.get("low"),d.get("high")
                has_range=last is not None and low is not None and high is not None and low<=last<=high
                bar_note=r["bar_state"].get(60,"connecting")
                checks=[
                    dict(id="feed",status=severity,detail=r["quote_state"]),
                    dict(id="fresh",status="good" if eligible else "warning" if fresh else "unknown",
                         detail="No quote" if age is None else f"Receipt {age:.1f}s; "+("exchange time unknown" if ex_age is None else f"exchange age {ex_age:.1f}s")),
                    dict(id="cross",status=cross_status,detail=cross),
                    dict(id="range",status="good" if has_range else "unknown",detail="Session range consistent" if has_range else "Session range unavailable or updating"),
                    dict(id="spread",status="unknown",detail="Order book not connected"),
                    dict(id="bars",status="good" if bars and bar_note=="receiving" else "warning" if bars else "unknown",
                         detail=f"{len(bars)} native bars; {bar_note}"),
                ]
                item=dict(key=i.key,symbol=i.symbol,name=i.name,group=i.group,slot=i.slot,decimals=i.decimals,
                    last=last,change=d.get("change"),change_pct=d.get("change_pct"),change_basis="native_session",
                    ticks=r["ticks"],status=severity,checks=checks,delay_seconds=None,update_mode="native_push",
                    bid=None,ask=None,open=d.get("open"),high=high,low=low,prev_close=d.get("prev_close"),
                    volume=d.get("volume"),candidate_volume=None,turnover=d.get("value"),
                    range_position=(last-low)/(high-low) if has_range and high>low else None,
                    realized_vol_pct=None,bar_count=len(bars),bar_updates=r["bar_updates"],history_ready=60 in r["ready"])
                if with_series:
                    item.update(bars=self.series(bars,60,now),micro_bars=self.series(r["micro_bars"],30,now))
                instruments.append(item)
                quotes[i.key]=dict(symbol=i.symbol,last=last,exchange_utc=utc(r["exchange"]) if r["exchange"] is not None else None,
                    received_utc=utc(r["received"]) if r["received"] is not None else None,price_age_s=ex_age,
                    receipt_age_s=age,update_mode="native_push",status=state,usable_short_term=eligible,
                    outcome=r["quote_state"],samples=r["ticks"],price_changes=r["changes"],
                    main_session=dict(r["sessions"].get("main_session",{})),
                    daily_session=dict(r["sessions"].get("daily_session",{})))
            payload=dict(instruments=instruments,quotes=quotes,connected=any(q["status"] in ("LIVE","UNVERIFIED") for q in quotes.values()),
                mode="native_push",reason=self.reason,history_source="takeprofit_native",micro_enabled=self.micro,
                history_ready=sum(i["history_ready"] for i in instruments),generated_utc=utc(now),
                uptime_seconds=time.monotonic()-self.started)
        if with_series:
            # Compute outside the lock so streaming updates aren't blocked by correlation.
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
