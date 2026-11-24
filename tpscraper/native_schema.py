"""Read-only wire fields independently implemented from the Nov 24 worker schemas.

Market data availability and semantics still require a live test. No credentials
or original worker code are bundled.
"""
from decimal import Decimal
from .quote_schema import fields, message, varint

CANDLE_STREAM="takeprofit.marketdata.external.candle.v1.CandleStreamApi/CandleStream"
CANDLE_HISTORY="takeprofit.marketdata.external.candle.v1.CandleHistoryApi/ListCandles"
QUOTE_STREAM="takeprofit.marketdata.external.quote.v1.QuoteApi/QuoteStream"
PROPERTIES=(7,6,2,3,4,5,8)

def integer(field,value):
    return varint(field*8)+varint(value & ((1<<64)-1))

def security(symbol,provider):
    if not symbol or not provider or max(len(symbol),len(provider))>100:
        raise ValueError("Invalid instrument")
    return message(2,message(1,symbol.encode())+message(2,provider.encode()))

def timeframe(period):
    if period not in (30,60,300,900):
        raise ValueError("Unsupported period")
    unit,count=(1,period) if period<60 else (2,period//60)
    return integer(1,unit)+integer(2,count)

def candle_request(symbol,provider,period=60,count=360):
    if not 1<=count<=1000:
        raise ValueError("Invalid history count")
    item=message(1,security(symbol,provider))+message(2,timeframe(period))
    item+=message(3,integer(2,count))+message(5,bytes(PROPERTIES))
    item+=integer(6,100)+message(7,b"\x00")
    return message(1,item)

def history_request(symbol,provider,period=60,count=360,end=None):
    import time
    if not 1<=count<=1000:
        raise ValueError("Invalid history count")
    bound=message(1,integer(1,int(time.time() if end is None else end)))+integer(4,-count)
    return (message(1,security(symbol,provider))+message(2,timeframe(period))+
            message(3,bound)+message(4,bytes(PROPERTIES))+message(5,b"\x00"))

def quote_stream_request(pairs):
    if not 1<=len(pairs)<=12 or len(set(pairs))!=len(pairs):
        raise ValueError("Invalid watchlist")
    return b"".join(message(1,message(1,security(s,p))+integer(2,i+1))
                    for i,(s,p) in enumerate(pairs))+integer(3,250)

def get(obj,k,wire,default=None):
    vals=obj.get(k,[])
    if not vals:
        return default
    if len(vals)!=1 or vals[0][0]!=wire:
        raise ValueError("Unexpected field")
    return vals[0][1]

def signed(n):
    return n-(1<<64) if n>=1<<63 else n

def decimal(data):
    if data is None:
        return None
    f=fields(data)
    n=signed(get(f,1,0,0))
    scale=signed(get(f,2,0,0))
    if scale<0:
        raise ValueError("Negative scale")
    return float(Decimal(n)/Decimal(scale or 1))

def stamp(data):
    if data is None:
        return None
    f=fields(data)
    seconds=signed(get(f,1,0,0))
    nanos=get(f,2,0,0)
    if not 0<=nanos<10**9 or not 0<seconds<4102444800:
        raise ValueError("Invalid timestamp")
    return seconds+nanos/1e9

def status(f,k=1):
    raw=get(f,k,2)
    return get(fields(raw),1,0,0) if raw is not None else 0

def candle(data):
    f=fields(data)
    out={"t":stamp(get(f,1,2))}
    for field,name in ((2,"o"),(3,"h"),(4,"l"),(5,"c"),(6,"value"),(7,"v"),
                       (9,"buying_value"),(10,"selling_value"),(11,"buying_volume"),(12,"selling_volume")):
        out[name]=decimal(get(f,field,2))
    out.update(session_type=get(f,8,0,0),tick_count=get(f,14,0))
    if out["t"] is None or any(out[k] is None for k in ("o","h","l","c")):
        raise ValueError("Incomplete candle")
    if not out["l"]<=min(out["o"],out["c"])<=max(out["o"],out["c"])<=out["h"]:
        raise ValueError("Inconsistent OHLC")
    if out["v"] is not None and out["v"]<0:
        raise ValueError("Negative volume")
    return out

def candle_item(data):
    f=fields(data)
    code=status(f)
    if code:
        return {"status":code}
    raw=get(f,2,2)
    return {"status":0,"bar":candle(raw) if raw is not None else None,
            "is_last":bool(get(f,6,0,0))}

def history_items(data):
    f=fields(data)
    code=status(f)
    if code:
        return {"status":code,"bars":[]}
    if get(f,3,2) is not None:
        raise ValueError("Compressed history not supported")
    return {"status":0,"bars":[candle(raw) for wire,raw in f.get(2,[]) if wire==2]}

def quote_item(data,pairs):
    outer=fields(data)
    raw=get(outer,1,2)
    if raw is None:
        return None
    f=fields(raw)
    tag=get(f,4,0)
    ident=get(f,3,2)
    if ident is not None and tag is not None:
        raise ValueError("Ambiguous quote identity")
    if tag is not None and 1<=tag<=len(pairs):
        pair=pairs[tag-1]
    elif ident is not None:
        tick=fields(get(fields(ident),2,2,b""))
        pair=(get(tick,1,2,b"").decode(),get(tick,2,2,b"").decode())
        if pair not in pairs:
            raise ValueError("Unknown quote identity")
    else:
        raise ValueError("Missing quote identity")
    result={"symbol":pair[0],"provider":pair[1],"status":status(f)}
    quote=get(f,2,2)
    if result["status"] or quote is None:
        return result
    q=fields(quote)
    for idx,key in ((1,"main_session"),(2,"daily_session")):
        raw=get(q,idx,2)
        if raw is None:
            continue
        values=fields(raw)
        out={}
        for field,name in ((1,"last"),(2,"last_dir"),(3,"change"),(4,"change_pct"),
                           (6,"open"),(7,"high"),(8,"low"),(10,"last_volume"),(11,"last_value"),
                           (12,"volume"),(13,"value")):
            v=decimal(get(values,field,2))
            if v is not None:
                out[name]=v
        t=stamp(get(values,5,2))
        if t is not None:
            out["exchange_timestamp"]=t
        prev=get(values,9,2)
        if prev is not None:
            out["prev_close"]=decimal(get(fields(prev),1,2))
        result[key]=out
    return result
