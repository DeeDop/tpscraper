"""Descriptive, timestamp-aligned research measures; no forecasts or orders."""
import math
from statistics import correlation

def aligned_lags(a,b,min_samples=30):
    """a(t) vs b(t+lag*60); positive lag means a precedes b.
    Input mappings contain completed, consecutive 1m log returns by epoch.
    """
    results=[]
    for lag in range(-5,6):
        pairs=[(a[t],b[t+60*lag]) for t in sorted(a) if t+60*lag in b]
        rho=None
        if len(pairs)>=min_samples:
            try:
                rho=correlation([x for x,y in pairs],[y for x,y in pairs])
            except (ValueError,ZeroDivisionError):
                pass
        results.append(dict(lag_minutes=lag,samples=len(pairs),correlation=rho))
    return results

def basis(spot,perp):
    """Price basis only for fresh same-asset timestamped prices, not an edge."""
    if not spot or not perp or not spot.get("live_price_usable") or not perp.get("live_price_usable"):
        return None
    from datetime import datetime
    try:
        st=datetime.fromisoformat(spot["live_price_event_utc"].replace("Z","+00:00")).timestamp()
        pt=datetime.fromisoformat(perp["live_price_event_utc"].replace("Z","+00:00")).timestamp()
        a,b=spot["live_price"],perp["live_price"]
        if abs(st-pt)>2 or not math.isfinite(a) or not math.isfinite(b) or a<=0 or b<=0:
            return None
        return dict(spot_symbol=spot["symbol"],perpetual_symbol=perp["symbol"],
                    spot_price=a,perpetual_price=b,basis=b-a,basis_bps=(b/a-1)*10000,
                    timestamp_skew_s=abs(st-pt))
    except (ValueError,TypeError,KeyError,AttributeError):
        return None
