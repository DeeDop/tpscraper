"""Experimental wire format based on observed ListQuotes messages."""
from decimal import Decimal

def varint(value):
    if value < 0:
        raise ValueError("negative varint")
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)

def message(field, data):
    return varint(field*8+2)+varint(len(data))+data

def quote_request(symbol, provider):
    if not symbol or not provider or len(symbol)>100 or len(provider)>100:
        raise ValueError("Invalid symbol/provider")
    security = message(1,symbol.encode())+message(2,provider.encode())
    return message(1,message(1,message(2,security))+b"\x10\x01")

def read_varint(data, pos):
    n=0
    for shift in range(0,70,7):
        if pos >= len(data):
            raise ValueError("Truncated varint")
        byte=data[pos]
        pos+=1
        n|=(byte&127)<<shift
        if byte<128:
            if n >= 1<<64:
                raise ValueError("Varint overflow")
            return n,pos
    raise ValueError("Invalid varint")

def fields(data):
    pos=0
    out={}
    while pos<len(data):
        tag,pos=read_varint(data,pos)
        field,wire=tag>>3,tag&7
        if not field:
            raise ValueError("Invalid field")
        if wire==0:
            val,pos=read_varint(data,pos)
        elif wire in (1,2,5):
            size=8 if wire==1 else 4
            if wire==2:
                size,pos=read_varint(data,pos)
            if size>len(data)-pos:
                raise ValueError("Truncated field")
            val=data[pos:pos+size]
            pos+=size
        else:
            raise ValueError("Unsupported wire type")
        out.setdefault(field,[]).append((wire,val))
    return out

def at(data, path, wire=2):
    for index, field in enumerate(path):
        expected=wire if index==len(path)-1 else 2
        values=fields(data).get(field,[])
        if len(values)!=1 or values[0][0]!=expected:
            raise ValueError("Unknown or ambiguous quote structure")
        data=values[0][1]
    return data

def candidate_price(data):
    # Repeated observed structure, not a documented or verified price schema.
    number=at(data,(2,2,1,1,1),0)
    divisor=at(data,(2,2,1,1,2),0)
    if number >= 1<<63:
        number-=1<<64
    if not 0<divisor<=10**12:
        raise ValueError("Invalid price divisor")
    return str(Decimal(number)/Decimal(divisor))


def candidate_details(data):
    """Observed fixed-point fields; only emit internally consistent candidates.
    No timestamp or bid/ask schema is established; volume/turnover are candidates.
    """
    def dec(path):
        n=at(data,path+(1,),0)
        d=at(data,path+(2,),0)
        if n>=1<<63:
            n-=1<<64
        if not 0<d<=10**12:
            raise ValueError("Invalid fixed point")
        return Decimal(n)/Decimal(d)
    prefix=(2,2,1)
    try:
        last=dec(prefix+(1,))
        change=dec(prefix+(3,))
        pct=dec(prefix+(4,))
        op=dec(prefix+(6,))
        hi=dec(prefix+(7,))
        lo=dec(prefix+(8,))
        prev=dec(prefix+(9,1))
        if not (prev>0 and lo<=min(last,op)<=max(last,op)<=hi):
            return {}
        if abs(last-prev-change)>Decimal("0.000001"):
            return {}
        if abs((last-prev)/prev*100-pct)>Decimal("0.02"):
            return {}
        out={k:str(v) for k,v in dict(open=op,high=hi,low=lo,prev_close=prev,
                                       change=change,change_pct=pct).items()}
        # In the Nov 24 Gold samples these two fields rise together, with
        # delta(turnover)/delta(volume) equal to the observed quote price.
        # BTC samples show a similar relationship; units/window unverified.
        try:
            volume=dec(prefix+(12,))
            turnover=dec(prefix+(13,))
            if volume>=0 and turnover>=0 and (volume>0 or turnover==0):
                out.update(candidate_volume=str(volume),candidate_turnover=str(turnover))
        except (ValueError,ArithmeticError):
            pass
        return out
    except (ValueError,ArithmeticError):
        return {}
