# Instruments

A subscription identifies a provider and a ticker, separated by a colon. Exchange display names may not be valid provider codes.

Use the dashboard instrument directory or `GET /api/catalog?q=BTC` to search locally available metadata. The directory is an offline subset, not a live entitlement or availability service. A symbol missing from the directory can still be entered manually.

## Examples

| Instrument | Exact candidate pair |
|---|---|
| Bitcoin spot | CXBNCE:BTC/USDT |
| Ethereum spot | CXBNCE:ETH/USDT |
| Bitcoin perpetual | CXBNF8:BTC/USDT.P |
| Gold reference | FXPPST:XAU/USD |
| Gold perpetual | CXBNF8:XAU/USDT.P |
| Silver reference | FXPPST:XAG/USD |
| EUR/USD | FXPPST:EUR/USD |
| Dollar index forward | FXPPST:USDX.F |
| US Treasury 10Y price proxy | FXPPST:USTN10YR-F |

These candidates are not guaranteed to be available or live. Provider codes, contracts, and subscriptions may change. A spot, CFD, perpetual or futures contract is not interchangeable with another price series; a Treasury price is not a yield.

```powershell
py -m tpscraper serve --authorized --auto-renew --ticker "CXBNCE:BTC/USDT" --ticker "FXPPST:XAU/USD"
```

An optional offline directory may be placed in the docs directory as takeprofit_tickers.csv or orderbook_catalog.csv with provider and symbol columns (ticker is also accepted in the basic directory). Use only metadata you are permitted to store or distribute. No authenticated captures should be included. The directory is loaded at process startup.
