"""Validated local watchlist workspace. No credentials or executable commands."""
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from dataclasses import replace
from .instruments import WATCHLISTS, Instrument

PAIR=re.compile(r"[A-Za-z0-9_]+:[A-Za-z0-9_./!+\-]+")
GOLD_PERP=Instrument("gold_perp","CXBNF8:XAU/USDT.P","Gold perpetual (Binance)","Gold flow",5,2)

def workspace_path():
    root=Path(os.environ.get("LOCALAPPDATA",str(Path.home()/".cache")))
    return root/"tpscraper"/"marketdata"/"workspace.json"

def validate_pairs(pairs):
    if not isinstance(pairs,list) or not 1<=len(pairs)<=12:
        raise ValueError("Select 1–12 instruments.")
    out=[]
    for pair in pairs:
        if not isinstance(pair,str) or len(pair)>120 or not PAIR.fullmatch(pair):
            raise ValueError("Use exact PROVIDER:TICKER pairs.")
        if pair not in out:
            out.append(pair)
    return out

def preset_pairs():
    return {name:[i.symbol for i in items]+([GOLD_PERP.symbol] if name=="gold" else [])
            for name,items in WATCHLISTS.items()}

def instruments_for(pairs):
    known={i.symbol:i for items in WATCHLISTS.values() for i in items}
    known[GOLD_PERP.symbol]=GOLD_PERP
    out=[]
    for n,pair in enumerate(validate_pairs(pairs)):
        i=known.get(pair)
        if i is None:
            key="custom_"+hashlib.sha256(pair.encode()).hexdigest()[:16]
            i=Instrument(key,pair,pair.split(":",1)[1],"Custom",n%9+1,5)
        out.append(replace(i,slot=n%9+1))
    return tuple(out)

def load_workspace(path=None):
    path=Path(path or workspace_path())
    if not path.exists():
        return None
    return validate_pairs(json.loads(path.read_text(encoding="utf-8"))["pairs"])

def save_workspace(pairs,path=None):
    pairs=validate_pairs(pairs)
    path=Path(path or workspace_path())
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix="workspace-",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump({"pairs":pairs},f,indent=2)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return pairs
