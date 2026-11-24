# TakeProfit instrument catalog

Source: the supplied TakeProfit HAR, captured November 24, 2026. The 35 successful SearchWithGroups responses contained 836 instrument occurrences, deduplicated to 562 distinct provider/symbol pairs. All 562 identities matched the redundant provider and symbol columns in the captured responses. This is the observed subset of the screener, not the entire exchange universe or a verified subscription entitlement list.

- [Complete captured ticker catalog (CSV)](takeprofit_tickers.csv): exact provider and symbol, exchange display name, market type, category, group, base, asset type, quote currency, description.
- [Provider and exchange index (CSV)](takeprofit_exchanges.csv).

## Provider codes

| Provider input | Exchange display name(s) | Observed symbols |
|---|---|---:|
| BATS | CBOE, NASDAQ, NYSE | 83 |
| CXBITR | BITRUE | 1 |
| CXBNCE | BINANCE (spot) | 83 |
| CXBNF8 | BINANCE (perpetual futures) | 229 |
| CXBPOT | BYBIT (spot) | 2 |
| CXBYBT | BYBIT (derivatives) | 13 |
| CXHBDM | HTX | 6 |
| CXHYPE | HYPERLIQUID | 2 |
| CXOKEX | OKEX | 3 |
| CXTTMN | TOTHEMOON | 3 |
| CXXBSC | BINANCE (USD-denominated derivatives) | 8 |
| FXEXTS | Exness Standard | 32 |
| FXPPST | Pepperstone | 97 |

The exchange display name is not necessarily the provider code to send.

## Gold and macro research shortlist

Every pair below was actually present in the HAR. Only FXPPST:XAU/USD has been validated by the user's successful native quote request; the others require individual quote testing.

| Role | Provider | Exact symbol |
|---|---|---|
| Spot gold reference | FXPPST | XAU/USD |
| Alternate spot gold | FXEXTS | XAU/USD |
| Alternate 24/7 named gold instrument | FXEXTS | XAU/USD247 |
| Gold forward | FXPPST | XAU.F |
| US Dollar Index forward | FXPPST | USDX.F |
| US 2-year Treasury instrument | FXPPST | USTN2YR-F |
| US 5-year Treasury instrument | FXPPST | USTN5YR-F |
| US 10-year Treasury instrument | FXPPST | USTN10YR-F |
| US Treasury bond instrument | FXPPST | US_TBOND-F |
| Gold ETF | BATS | GLD |
| Gold miners ETF | BATS | GDX |
| Long Treasury ETF | BATS | TLT |
| Silver perpetual | CXBNF8 | XAG/USDT.P |
| Gold perpetual | CXBNF8 | XAU/USDT.P |
| Gold-backed token | CXBNCE | PAXG/USDT |
| Gold-backed token | CXBNCE | XAUT/USDT |
| GBP/USD | FXPPST | GBP/USD |
| USD/MXN | FXPPST | USD/MXN |
| Volatility index instrument | FXPPST | VIX |
| US equity index | FXPPST | US500 |
| US tech index | FXPPST | USTEC |
| Bitcoin spot | CXBNCE | BTC/USDT |
| Ethereum spot | CXBNCE | ETH/USDT |

Treasury prices and yields are different; do not treat a Treasury instrument as a yield series without validating its contract. The capture did not contain FXPPST:EUR/USD, FXPPST:USD/JPY, FXPPST:AUD/USD, FXPPST:USD/CAD or FXPPST:XAG/USD. Absence from this capture does not establish unavailability.

## Try a captured pair

```powershell
py -m tpscraper.console --local-chrome --remember --provider FXPPST --symbol USDX.F
py -m tpscraper.console --local-chrome --remember --provider CXBNCE --symbol BTC/USDT
```

## Rebuild from a new local HAR

```powershell
py -m tpscraper.har_catalog "C:\path\takeprofit.com.har" --output docs
```

The offline importer only exports selected instrument metadata from successful screener responses. Never commit a HAR, authentication headers, cookies, or tokens. Search results do not establish whether quotes are live, delayed, or authorized for programmatic use. Use only where permitted by the data provider.
