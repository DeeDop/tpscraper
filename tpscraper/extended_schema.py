"""Bounded read-only diagnostics for provider-permitted market data.

Field numbers follow the supplied client message definitions. No trading RPC,
credential logging, session extraction or entitlement overrides.
"""
from .native_schema import (
    integer, security, timeframe, get, decimal, stamp, fields, message,
    candle_request, history_request, quote_stream_request,
    candle_item, history_items, quote_item, CANDLE_STREAM, CANDLE_HISTORY, QUOTE_STREAM,
)
from collections import Counter
import time

PC = "takeprofit.marketdata.external.price_charts.v1."
OB = "takeprofit.marketdata.order_book.v1."
TRADE = "takeprofit.marketdata.trade.v1.TradeStreamExternalApi/GetTradeStream"
BOOK = OB + "OrderBookApi/GetOrderBookStream"
HEAT = OB + "OrderBookHistoryApi/GetOrderBookHistoryStream"
FP = PC + "VolumeFootprintStreamApi/VolumeFootprintSnapshotStream"
TPO = PC + "TpoStreamApi/TpoStream"
RENKO = "takeprofit.marketdata.charts.v1.ChartsApi/RenkoStream"

def many(f,n):
    values=f.get(n,[])
    if any(w!=2 for w,_ in values):
        raise ValueError("Unexpected repeated message")
    return [fields(raw) for _,raw in values]

def ts(f,n):
    return stamp(get(f,n,2))

def dec(f,n):
    return decimal(get(f,n,2))

def trade_rows(raw):
    f=fields(raw)
    rows=[]
    for t in many(f,1):
        p,q=dec(t,4),dec(t,5)
        if p is None or q is None or p<=0 or q<0:
            raise ValueError("Invalid trade")
        ident=get(t,12,2)
        number=get(t,1,2)
        trade_id=get(fields(ident),1,2,b"").decode() if ident is not None else None
        trade_no=get(fields(number),1,0,0) if number is not None else None
        rows.append(dict(time=ts(t,3),price=p,quantity=q,trade_id=trade_id or (str(trade_no) if trade_no is not None else None),
                         side={1:"buy",2:"sell"}.get(get(t,6,0,0),"unknown"),
                         open_interest=dec(t,8)))
    return rows

def levels(f,n):
    result=[]
    for level in many(f,n):
        p,q=dec(level,1),dec(level,2)
        # Omitted quantity is unknown until the provider deletion semantics are validated.
        if p is None or p<=0 or (q is not None and q<0):
            raise ValueError("Invalid price level")
        result.append(dict(price=p,size=q,max_size=dec(level,3),twa_size=dec(level,4)))
    return result

def book_summary(raw,heat=False,full=False):
    f=fields(raw)
    k=1 if get(f,1,2) is not None else 2 if not heat and get(f,2,2) is not None else None
    if k is None:
        return []
    b=fields(get(f,k,2))
    a,d=levels(b,2),levels(b,3)
    row=dict(kind="heatmap" if heat else "snapshot" if k==1 else "update",
             time=ts(b,1),asks=len(a),bids=len(d))
    if heat:
        row.update(price_step=dec(b,4),bucket_end=ts(b,5))
    else:
        row["version"]=get(b,4,0)
    # Never treat a delta as a complete book.
    if k==1 and not heat:
        ap=[x["price"] for x in a if (x["size"] or 0)>0]
        bp=[x["price"] for x in d if (x["size"] or 0)>0]
        row.update(best_ask=min(ap) if ap else None,best_bid=max(bp) if bp else None)
        if ap and bp and min(ap)>=max(bp):
            row["spread"]=min(ap)-max(bp)
    row.update(example_ask=a[0] if a else None,example_bid=d[0] if d else None)
    if full:
        row.update(ask_levels=a,bid_levels=d)
    return [row] if a or d else []

def footprint_rows(raw,full=False):
    f=fields(raw)
    b=get(f,1,2)
    if b is None:
        return []
    p=fields(b)
    rows=many(p,5)
    sell,buy=dec(p,6),dec(p,7)
    result=dict(start=ts(p,1),end=ts(p,2),row_size=dec(p,4),price_rows=len(rows),
                sell_volume=sell,buy_volume=buy,sell_trades=get(p,8,0),buy_trades=get(p,9,0))
    if sell is not None and buy is not None:
        result["delta"]=buy-sell
    if full:
        result["levels"]=[dict(price=dec(r,1),sell_volume=dec(r,2),buy_volume=dec(r,3),sell_trades=get(r,4,0,0),buy_trades=get(r,5,0,0)) for r in rows]
    if rows:
        r=rows[0]
        result["example_level"]=dict(price=dec(r,1),sell_volume=dec(r,2),buy_volume=dec(r,3),
                                     sell_trades=get(r,4,0),buy_trades=get(r,5,0))
    return [result] if rows or sell is not None or buy is not None else []

def uints(f,n):
    result=[]
    for wire,value in f.get(n,[]):
        if wire==0:
            result.append(value)
        elif wire==2:
            acc=shift=0
            for b in value:
                acc|=(b&127)<<shift
                if b<128:
                    result.append(acc)
                    acc=shift=0
                else:
                    shift+=7
                    if shift>35:
                        raise ValueError("Invalid packed uint32")
            if shift:
                raise ValueError("Truncated packed uint32")
        else:
            raise ValueError("Invalid uint32 field")
    if any(x>=2**32 for x in result):
        raise ValueError("Invalid uint32 value")
    return result

def tpo_rows(raw,full=False):
    f=fields(raw)
    b=get(f,1,2)
    if b is not None:
        p=fields(b)
        row=dict(kind="profile",start=ts(p,1),end=ts(p,10),price_rows=len(many(p,5)),
                     blocks=len(many(p,6)),row_size=dec(p,4),poc=dec(p,7),
                     initial_balance_high=dec(p,8),initial_balance_low=dec(p,9))
        if full:
            row["levels"]=[dict(price=dec(r,1),block_indexes=uints(r,2),sell_volume=dec(r,5),buy_volume=dec(r,6)) for r in many(p,5)]
            row["block_infos"]=[get(b,1,0,0) for b in many(p,6)]
        return [row]
    b=get(f,2,2)
    if b is not None:
        p=fields(b)
        row=dict(kind="diff",start=ts(p,1))
        for n,k in ((4,"row_size"),(7,"poc"),(8,"initial_balance_high"),(9,"initial_balance_low")):
            if get(p,n,2) is not None:
                row[k]=dec(p,n)
        if get(p,10,2) is not None:
            row["end"]=ts(p,10)
        if full:
            # Do not guess row-diff application or nested block-append semantics.
            row["row_diff_count"]=len(many(p,5))
            row["block_append_count"]=len(many(p,6))
        return [row]
    return []

def renko_rows(raw):
    f=fields(raw)
    b=get(f,2,2)
    if b is None:
        return []
    outer=fields(b)
    brick=get(outer,2,2)
    if brick is None:
        return []
    p=fields(brick)
    return [dict(time=ts(p,1),index=get(p,2,0,0),open=dec(p,3),close=dec(p,4))]

def history_rows(raw):
    item=history_items(raw)
    return item["bars"],item["status"]

def candle_rows(raw):
    item=candle_item(raw)
    return ([item["bar"]] if item.get("bar") else []),item["status"]

def plans(symbol,provider,now=None):
    now=int(time.time() if now is None else now)
    pair=(symbol,provider)
    sec=message(1,security(*pair))
    since=lambda n:message(1,integer(1,now-n))
    # Main session, merged, automatic footprint row size.
    opts=message(1,b"\x00")+integer(2,1)+message(3,timeframe(60))
    tpo_opts=message(1,b"\x00")+integer(2,1)+message(3,integer(1,4)+integer(2,1))+integer(4,1)
    heat=sec+message(2,integer(1,now-120))+message(4,timeframe(60))+integer(5,1)+integer(7,20)+message(8,b"\x01")+integer(9,1000)
    renko=sec+message(2,timeframe(60))+message(3,integer(1,30))+message(5,integer(1,14))+integer(7,2)
    def quote(raw):
        item=quote_item(raw,[pair])
        if item is None:
            return [],0
        return ([item] if item.get("main_session") or item.get("daily_session") else []),item.get("status",0)
    def plain(fn):
        return lambda raw:(fn(raw),0)
    return {
        "history":(CANDLE_HISTORY,history_request(*pair,count=30),history_rows),
        "candles":(CANDLE_STREAM,candle_request(*pair,count=30),candle_rows),
        "quotes":(QUOTE_STREAM,quote_stream_request([pair]),quote),
        "trades":(TRADE,sec,plain(trade_rows)),
        "orderbook":(BOOK,sec,plain(book_summary)),
        "footprint":(FP,sec+message(2,since(300))+message(3,opts)+integer(4,1000),plain(footprint_rows)),
        "heatmap":(HEAT,heat,plain(lambda raw:book_summary(raw,True))),
        "tpo":(TPO,sec+message(2,since(86400))+message(3,tpo_opts)+integer(4,1000),plain(tpo_rows)),
        "renko":(RENKO,renko,plain(renko_rows)),
    }
