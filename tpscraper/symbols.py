"""Simple ticker input; captured catalog is a hint, never an allowlist."""
import csv
from pathlib import Path
import re

DOCS = Path(__file__).resolve().parent.parent / "docs"
PROVIDERS = {
    "BATS": "US equities / ETFs (CBOE, NASDAQ, NYSE)",
    "CXBITR": "Bitrue",
    "CXBNCE": "Binance spot",
    "CXBNF8": "Binance perpetuals",
    "CXBPOT": "Bybit spot",
    "CXBYBT": "Bybit derivatives",
    "CXHBDM": "HTX",
    "CXHYPE": "Hyperliquid",
    "CXOKEX": "OKEX",
    "CXTTMN": "Tothemoon",
    "CXXBSC": "Binance USD derivatives",
    "FXEXTS": "Exness Standard",
    "FXPPST": "Pepperstone",
}


def checked(value):
    value = value.strip()
    if not value or len(value) > 100 or any(c.isspace() or ord(c)<32 for c in value):
        raise ValueError("Enter a nonempty ticker or provider code without spaces.")
    return value


def load_catalog(path=None):
    try:
        with Path(path or DOCS / "takeprofit_tickers.csv").open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    except (OSError, UnicodeError, csv.Error):
        return []


def normalized(value):
    # Convenience for BTCUSDT and XAUUSD, without conflating .P, .F or -F contracts.
    return re.sub(r"[/]", "", value.upper())


def matches(symbol, rows):
    exact = [r for r in rows if r.get("symbol", "").upper() == symbol.upper()]
    found = exact or [r for r in rows if normalized(r.get("symbol", "")) == normalized(symbol)]
    pairs = {}
    for r in found:
        if r.get("provider") and r.get("symbol"):
            pairs[(r["provider"], r["symbol"])] = r
    return list(pairs.values())


def choose(symbol=None, provider=None, *, rows=None, ask=input, emit=print):
    if symbol is None:
        symbol = ask("Ticker (e.g. XAU/USD, BTCUSDT, AAPL; Enter cancels): ").strip()
        if not symbol:
            return None
    if ":" in symbol:
        if provider is not None:
            raise ValueError("Use either PROVIDER:TICKER or --provider, not both.")
        provider, symbol = symbol.split(":", 1)
    symbol = checked(symbol)
    rows = load_catalog() if rows is None else rows
    candidates = matches(symbol, rows)
    if provider is not None:
        provider = checked(provider).upper()
        selected = [r for r in candidates if r["provider"].upper() == provider]
        if len(selected) == 1:
            symbol = selected[0]["symbol"]
        return symbol, provider
    if len(candidates) == 1:
        r = candidates[0]
        emit(f"Catalog match: {r['provider']}:{r['symbol']}")
        return r["symbol"], r["provider"]
    if candidates:
        emit("Matching instruments:")
        for i, r in enumerate(candidates, 1):
            emit(f"  {i}. {r['provider']}:{r['symbol']}  {PROVIDERS.get(r['provider'], r.get('exchange_name', ''))}")
        answer = ask("Choose number, enter another provider code, or Enter to cancel: ").strip()
        if not answer:
            return None
        if answer.isdigit():
            i = int(answer)
            if not 1 <= i <= len(candidates):
                raise ValueError("Invalid instrument selection.")
            r = candidates[i-1]
            return r["symbol"], r["provider"]
        provider = checked(answer).upper()
        selected = [r for r in candidates if r["provider"].upper() == provider]
        return (selected[0]["symbol"] if len(selected)==1 else symbol), provider
    emit("Not in captured catalog. You can still test any exact TakeProfit ticker.")
    for code, label in PROVIDERS.items():
        emit(f"  {code:<8} {label}")
    answer = ask("Provider code (Enter cancels): ").strip()
    if not answer:
        return None
    return symbol, checked(answer).upper()
