"""TakeProfit equivalents of the TV watchlists. Candidate pairs are explicit."""
from dataclasses import dataclass, replace

@dataclass(frozen=True)
class Instrument:
    key: str
    symbol: str
    name: str
    group: str
    slot: int
    decimals: int = 2

REALTIME = (
    Instrument("copper","FXPPST:XCU/USD","Copper (candidate)","Metals",1,4),
    Instrument("silver","FXPPST:XAG/USD","Silver spot (candidate)","Metals",2,3),
    Instrument("gold","FXPPST:XAU/USD","Gold spot","Metals",3),
    Instrument("btc","CXBNCE:BTC/USDT","Bitcoin","Crypto",4),
    Instrument("eth","CXBNCE:ETH/USDT","Ethereum","Crypto",5),
    Instrument("nq","FXPPST:USTEC","Nasdaq-100 proxy","Index",6),
    Instrument("spx","FXPPST:US500","S&P 500 proxy","Index",7),
    Instrument("vix","FXPPST:VIX","VIX instrument","Vol",8),
)
GOLD = (
    Instrument("dxy","FXPPST:USDX.F","Dollar index forward","FX/Index",1,3),
    Instrument("eurusd","FXPPST:EUR/USD","EUR/USD (candidate)","FX",2,5),
    Instrument("usdjpy","FXPPST:USD/JPY","USD/JPY (candidate)","FX",3,3),
    Instrument("us10y","FXPPST:USTN10YR-F","US 10Y price proxy (not yield)","Rates",4,4),
    Instrument("gold","FXPPST:XAU/USD","Gold spot","Metals",5),
    Instrument("silver","FXPPST:XAG/USD","Silver spot (candidate)","Metals",6,3),
    Instrument("audusd","FXPPST:AUD/USD","AUD/USD (candidate)","FX",7,5),
    Instrument("us02y","FXPPST:USTN2YR-F","US 2Y price proxy (not yield)","Rates",8,4),
    Instrument("us05y","FXPPST:USTN5YR-F","US 5Y price proxy (not yield)","Rates",9,4),
)
MARKETS15 = GOLD + (
    Instrument("gbpusd","FXPPST:GBP/USD","GBP/USD","FX",1,5),
    Instrument("usdcad","FXPPST:USD/CAD","USD/CAD (candidate)","FX",2,5),
    Instrument("usdmxn","FXPPST:USD/MXN","USD/MXN","FX",3,5),
)
WATCHLIST=REALTIME
WATCHLISTS={"realtime":REALTIME,"gold":GOLD,"markets15":MARKETS15}
