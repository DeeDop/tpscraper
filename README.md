# tpscraper

Native push market-data research engine for TakeProfit: live quotes, historical and live OHLCV, optional order flow, responsive dashboard and a local JSON/SSE API. Inspired by [tvscraper](https://github.com/Drew4311/tvscraper); the separate TV scraper and Kalshi strategy repositories are unchanged.

**Read-only. Use with your own authorized account only where TakeProfit and its underlying data providers permit programmatic access.** This experimental client is not the official external market-data API. A working chart does not by itself grant external data usage rights. See the [official platform API](https://www.takeprofit.com/docs/platform-api/overview) for supported integration.

## Install / update

Windows with Python 3.10+ and regular Chrome:

```powershell
cd C:\tools\tpscraper
git pull
py -m pip install -r requirements.txt
py -m compileall -q tpscraper tests
py -m unittest discover -s tests -v
```

For a new checkout, clone this repository first. Run commands from its root.

## Quick start

```powershell
py -m tpscraper dashboard --remember
py -m tpscraper dashboard --watchlist gold --remember
py -m tpscraper serve --watchlist markets15 --remember
```

Dashboard: **http://127.0.0.1:8789/**. Stop with Ctrl+C. The headless `serve` command does not open the dashboard tab. Run only one process per port.

### Full Gold research engine

If your provider/account permits the advanced data subscriptions:

```powershell
py -m tpscraper dashboard --watchlist gold --remember --orderflow --authorized --auto-renew
```

This enables automatic capability detection for every selected instrument and adds the Binance Gold perpetual to the Gold watchlist. Install and pair the Chrome extension as described below. Omit `--auto-renew` for manual authorization.

### Custom watchlist

```powershell
py -m tpscraper dashboard --remember --orderflow --authorized --ticker "CXBNCE:BTC/USDT" --ticker "CXBNF8:XAU/USDT.P" --ticker "FXPPST:XAU/USD"
```

Repeat `--ticker PROVIDER:TICKER` for up to 12 instruments. This replaces the preset. Keys become `custom1`, `custom2`, etc. Exact pairs outside the catalog are accepted: no ticker allowlist.

## Authentication

### Manual handoff (default)

Approve opening your regular Chrome profile, sign in normally and copy only the successful first-party JSON token response or access token. Choose `c` to permit a local clipboard read or `p` for hidden manual paste. Never share credentials or unredacted HARs. `--remember` stores the access token using current-user Windows DPAPI at `%LOCALAPPDATA%\tpscraper\auth\access.dpapi`. It does not extend its lifetime. Add `--chrome-profile "Profile 1"` if necessary.

```powershell
py -m tpscraper.credential_store status
py -m tpscraper.credential_store clear
```

Clear removes the local saved token, not the server-side session.

### Extension-free renewal in your normal signed-in Chrome (Chrome 144+)

```powershell
py -m pip install -r requirements-browser.txt
py -m tpscraper dashboard --watchlist btc --remember --orderflow --authorized --browser-renew
```

Keep your ordinary signed-in Chrome open. Approve the terminal consent prompt. In that same browser open `chrome://inspect/#remote-debugging` and enable remote debugging for this browser instance. When the program connects, approve Chrome's native permission dialog. No new Chrome profile, extension, pairing code, browser security flags or sign-in copying is necessary.

This uses Chrome's documented [approval-based existing-browser connection](https://developer.chrome.com/docs/devtools/agents/use-cases/auto-connect). Chrome grants browser-wide debugging permission; this program limits its own authorization request to TakeProfit's first-party token endpoint. It does not read stored browser cookies, passwords, unrelated page content or authentication headers. It reads only the documented local DevTools endpoint locator from the standard Chrome user-data directory. It never logs the endpoint or token. The connected browser stays open when the scraper disconnects. Turn off remote debugging to revoke the connection. If Chrome rejects access or TakeProfit refuses authorization, the program stops rather than bypassing the refusal. Multiple browser contexts and nonstandard Chrome installations may require manual authorization. This new mode has not been tested against your actual signed-in Chrome.

The old separate-profile mode remains optional using `--dedicated-browser-renew` (and `--browser-login` when needed). Manual handoff is available by omitting all renewal flags. The legacy extension mode is unchanged.

The browser modes request replacement authorization before tearing down active streams; a later token expiration is required. Stream reconnection can still cause a gap. Long-duration renewal, network recovery and soak acceptance remain unverified.

### Paired Chrome automatic renewal (legacy)

1. Open `chrome://extensions/` in the signed-in regular Chrome profile.
2. Enable Developer mode and select **Load unpacked**.
3. Select `C:\tools\tpscraper\chrome-renew`.
4. Start the dashboard or headless service with `--auto-renew --authorized`.
5. Paste the terminal's local pairing code into the extension popup and select **Authorize and pair**.

The extension requests fresh authorization through the normal first-party signed-in session only when the paired local process asks. No browser profile inspection, password extraction or network interception. The renewal bridge binds to 127.0.0.1:8790 and requires its random per-process pairing code. Pair once per running process; keep Chrome signed in. Disable from the extension popup. Server-side refusal stops renewal. Initial paired Chrome token acquisition and ten-instrument Gold dashboard startup were confirmed by the user on November 24. Sustained unattended renewal across multiple expirations remains to be verified.

## Watchlists and market relationships

| Preset | Purpose | Instruments |
|---|---|---:|
| realtime (default) | Metals, crypto, indexes, volatility | 8 |
| gold | Gold and high-priority USD/rates context | 9 |
| gold + orderflow | Gold context plus exchange-traded gold perpetual | 10 |
| markets15 | Gold and six USD currency targets, plus context | 12 |
| crypto15 | Nine requested Kalshi crypto research proxies | 9 |
| btc | Bitcoin spot | 1 |
| btc-depth | Bitcoin spot and perpetual | 2 |

| Key | TakeProfit symbol | Research interpretation |
|---|---|---|
| gold | FXPPST:XAU/USD | Spot/CFD gold reference |
| gold_perp | CXBNF8:XAU/USDT.P | Supplementary exchange order flow; Gold + orderflow |
| silver | FXPPST:XAG/USD | Precious-metal context |
| dxy | FXPPST:USDX.F | Dollar-index forward proxy |
| eurusd | FXPPST:EUR/USD | USD context |
| usdjpy | FXPPST:USD/JPY | USD/risk context |
| audusd | FXPPST:AUD/USD | Commodity currency context |
| us02y | FXPPST:USTN2YR-F | Treasury price proxy, not yield |
| us05y | FXPPST:USTN5YR-F | Treasury price proxy, not yield |
| us10y | FXPPST:USTN10YR-F | Treasury price proxy, not yield |
| gbpusd | FXPPST:GBP/USD | markets15 only |
| usdcad | FXPPST:USD/CAD | markets15 only |
| usdmxn | FXPPST:USD/MXN | markets15 only |

The realtime preset includes copper, silver, gold, BTC, ETH, Nasdaq-100, S&P 500 and VIX candidates. Not all preset symbols or sessions have been live verified. Treasury prices generally move inversely to yields; they are not actual yield measurements. The perpetual and spot Gold prices have a basis: compare synchronized returns, not interchangeable absolute prices. Relationships are research hypotheses, not validated prediction signals.

### Crypto research presets

```powershell
py -m tpscraper dashboard --watchlist btc --remember --orderflow --authorized --auto-renew
py -m tpscraper dashboard --watchlist btc-depth --remember --orderflow --authorized --auto-renew
py -m tpscraper dashboard --watchlist crypto15 --remember --orderflow --authorized --auto-renew
```

The `crypto15` preset preserves stable keys `btc`, `eth`, `sol`, `xrp`, `doge`, `bnb`, `hype`, `near`, `zec`. It uses Binance spot USDT pairs (including the catalog-listed HYPE/USDT candidate). These are research proxies for the requested market list, not an automatically synchronized list of active Kalshi contracts. Only BTC spot advanced services have been verified in the earlier individual crypto probes.

### Saved workspace from the dashboard

Use **+ Manage tickers** at the top of the dashboard. Load a Kalshi research preset, import active tickers, search by name/symbol/provider, or add an exact pair. Remove pairs by clicking their chips. Save workspace stores up to 12 unique validated pairs locally; known research symbols retain stable predictor keys. Restart with:

```powershell
py -m tpscraper dashboard --workspace --watchlist btc --remember --orderflow --authorized --browser-renew
```

`--workspace` loads the saved list (or the chosen preset if no saved list exists). It is mutually exclusive with `--ticker`. Saving does not interrupt active streams; application requires a restart. The workspace is not a live Kalshi series discovery service.

## Instrument discovery

See [captured ticker list](docs/takeprofit_tickers.csv), [provider codes](docs/takeprofit_exchanges.csv), and [instrument notes](docs/INSTRUMENTS.md). The basic directory contains 562 captured pairs. To merge the separately supplied 3,653-row order-book catalog, place `orderbook_catalog.csv` in `docs/` (provider,symbol columns). The merged directory count depends on the files installed. It is not guaranteed to contain every TakeProfit instrument.

Search the local API: `/api/catalog?q=gold`, `/api/catalog?provider=CXBNF8&q=XAU&limit=100`. Directory searches do not subscribe to live feeds. Missing catalog entries do not exclude a symbol.

## Native feed architecture

Native mode starts one tagged multi-instrument quote stream and one native 1-minute candle stream per instrument. The latter requests 360 initial bars by default and then receives ongoing complete-bar updates. A repeated timestamp replaces the corresponding candle; cumulative volume is not added again. No artificial historical bars or quote ticks derived from historical data.

| Data | Source / behavior |
|---|---|
| Last price, session change, volume and turnover | Native quote stream |
| Historical and live OHLCV | Native candle stream |
| 30-second OHLCV | Optional native stream; not yet tested live |
| 5m/15m OHLCV | Browser rollup from available 1m bars |
| VWAP | Reported turnover / volume; chart estimate when turnover missing |
| Timestamped live price | Independently timestamped quote or trade event |
| Bid, ask, spread | Fresh, synchronized order book |
| Depth and imbalance | Snapshot + versioned depth updates, 1/5/10/25 bps |
| Trade pressure | Timestamped events, quantities and decoded direction |
| Footprint | Provider buy/sell volumes, counts and price rows |
| CVD | Sum of observed closed footprint deltas, not full-session CVD |
| Liquidity heatmap | Provider depth buckets |
| TPO | Initial profile, scalar updates, block-index union and indexed block metadata updates matching the captured worker; no inferred volume accumulation |
| Renko | Diagnostic only |

### True live versus receipt-only data

Upstream is native server push, not ListQuotes polling or screen scraping. However, an arriving message does not guarantee an exchange-real-time quote. Native quote probes for BTC and Gold did not supply exchange timestamps. The raw `last` value stays separate from the new timestamped `live_price` fields.

With orderflow enabled, a recent timestamped trade event for the same provider/ticker can supply `live_price` independently of the untimestamped quote. Event age and receipt age must both be within the configured freshness checks (five seconds; small clock-skew tolerance). The source is explicitly identified. The reported arrival lag is local receipt time minus provider event time, so synchronized clocks are necessary. Broker events may represent price ticks rather than actual executions.

The local dashboard sends SSE ticks/quotes every approximately 250 ms and full history every approximately 2 seconds. This is a local delivery cadence, not an upstream latency guarantee. Delayed, missing, stale or disconnected data cannot be made live by refreshing faster. No price feed here is the Kalshi settlement oracle.

### Automatic capability detection

`--orderflow --authorized` attempts trades, orderbook, footprint, heatmap and TPO for every requested ticker. Launches are staggered. Catalog-listed depth and previously observed services get priority within each service category. Missing catalog rows are not treated as unsupported.

By default the advanced-stream budget is five per selected ticker, up to 60. Use `--flow-budget 24` or lower to reduce resource usage; pending services remain explicitly queued when the budget is full. A large watchlist can require many subscriptions; use only within provider limits. Stop if access or rate restrictions occur, not by increasing the budget.

Expired negative observations are eligible for retesting during operation (checked about once per minute, subject to the stream budget). Feature-specific permission refusal or schema failure disables that feature for the remainder of the process, including token rotations. Global authorization and rate-limit refusals stop collection. No access-denial retries. Capability observations are cached in `%LOCALAPPDATA%\tpscraper\marketdata\capabilities.json`. No data is cached for 15 minutes, unavailable for one hour, unsupported for one day, and observed for seven days. A timeout or empty stream is **no data observed**, not definitive unsupported status. `--refresh-capabilities` ignores cached negatives on initial discovery.

The order book requires a snapshot and consecutive versions. A gap invalidates depth and triggers reconnect attempts with capped exponential backoff and jitter. Empty sides, invalid quantities and crossed books are not reported as valid bid/ask. Inspection of the captured order-book worker confirms that omitted size is converted to zero and zero-size updates delete the affected level. This convention is regression-tested synthetically; sustained live order-book parity still needs verification. Unknown fields or service errors remain errors, not zero values. Trade deduplication uses provider IDs when present; unidentified events are counted separately.

## Dashboard

Retains the TV-style price tiles, extraction checks, indexed comparison, correlation heatmap, candle/line detail chart, accessible tables and light/dark theme. Responsive layout wraps long labels and contains wide charts/tables rather than widening the page.

- Tiles show available volume, synchronized bid/ask/spread, and a separately labeled timestamped live price.
- Detail picker switches the instrument and its advanced feature panel.
- Timeframes: 30s (optional), 1m, 5m, 15m. Visible windows: 5m to 6h.
- Drag to zoom; double-click or reset to clear. Select a chart legend item to drill down.
- Overlays: VWAP, SMA20, session high/low.
- Advanced panel: independent service status, timestamped price age/arrival lag, rolling 5/15/30/60s trade pressure, footprint delta, observed CVD, TPO values, heatmap bucket count and top bid/ask levels. Unavailable or stale metrics are omitted instead of invented.
- Correlation: Pearson correlation of aligned completed 1m returns; at least 30 overlapping returns in native mode. Descriptive only.

The candle chart can fall back to line mode when there are too many bars for readable candlesticks. Scaling and browser JavaScript syntax were improved; visual testing across actual Windows display settings remains outstanding.

## Local API for other predictors

```powershell
py -m tpscraper serve --watchlist gold --remember --orderflow --authorized --auto-renew
```

All routes are read-only, on **127.0.0.1:8789**. Do not expose this unauthenticated local API through a public tunnel.

| GET endpoint | Purpose |
|---|---|
| /api/quotes | All quote keys, timestamps, volume, turnover, spread, completed-history VWAP, orderflow summaries and timestamped live price |
| /api/snapshot | Full history, correlation and dashboard state |
| /api/health | Connection, history ready, usable raw quotes, timestamped live count |
| /api/stream | SSE events: full, tick, quotes |
| /api/orderflow | Recent trade events, depth, footprint and heatmap profiles; optional `?key=btc` limits details to one instrument |
| /api/diagnostics | Per-stream attempts, accepted messages, retries, errors and renewal attempts |
| /api/catalog | Search offline instrument directory |

### Python consumer (standard library)

```python
import json
from urllib.request import urlopen

with urlopen("http://127.0.0.1:8789/api/quotes", timeout=3) as response:
    feed = json.load(response)

gold = feed["quotes"].get("gold", {})
if gold.get("live_price_usable"):
    print(gold["live_price"], gold["live_price_source"], gold["live_price_age_s"])

perp = feed["quotes"].get("gold_perp", {})
flow = perp.get("orderflow", {})
book = flow.get("book", {})
if book.get("fresh") and book.get("synchronized"):
    print(book["bid"], book["ask"], book["spread"])

w = flow.get("trade_windows", {}).get("15", {})
if w.get("fresh") and w.get("complete"):
    print(w["delta"], w["imbalance"])
```

### Important field definitions

| Field | Meaning |
|---|---|
| last | Raw provider quote, possibly stale |
| exchange_utc / price_age_s | Raw quote's event time/age if available |
| received_utc / receipt_age_s | Local quote arrival time/age |
| usable_short_term | Raw quote passes timestamp and freshness gates |
| live_price | Independently eligible timestamped quote or trade-event price, otherwise null |
| live_price_source | timestamped_quote or timestamped_trade_event |
| live_price_event_utc / live_price_received_utc | Timestamped event time and receipt time |
| live_price_age_s / live_price_arrival_lag_s | Age and measured event-to-receipt lag (lag provided for trade path) |
| live_price_usable | Timestamped candidate passes freshness gates; not proof of provider accuracy |
| bid / ask / spread | Null unless valid current depth supplies these values |
| volume / turnover | Provider session totals; units vary |
| history_vwap / history_vwap_bars | Weighted price over retained completed bars with complete volume and turnover |
| volume_semantics | Broker tick activity or provider-reported quantities |
| orderflow.streams | Independent status and receipt age for each feature |
| orderflow.book | Synchronization, version, event time, depth, best prices, imbalances |
| orderflow.trade_windows | 5/15/30/60s count, volume, delta, imbalance and warm-up flags |
| orderflow.footprint | Current footprint freshness and observed closed-profile CVD |

Consumers must reject stale, invalid, restricted and missing features; never convert them to a neutral vote. Trade pressure and book liquidity do not establish prediction accuracy. Price, provider and timestamps must be matched to the intended contract. Keep all Kalshi settlement and strategy logic in the separate predictor. This engine never places orders.

## Recording

```powershell
py -m tpscraper serve --watchlist gold --remember --orderflow --authorized --auto-renew --record-flow "$env:USERPROFILE\Downloads\tpscraper_flow.sqlite3"
```

Optional SQLite WAL journal of compact feature and quote snapshots approximately once per second, plus completed provider bars. Seven-day retention with hourly pruning. A data gap is not filled with synthetic values. No full raw depth snapshot replay, no authentication headers or tokens. Protect data according to provider terms.

## CLI reference

| Flag | Meaning |
|---|---|
| --watchlist realtime/gold/markets15/crypto15/btc/btc-depth | Preset |
| --ticker PROVIDER:TICKER | Repeat to override preset, max 12 |
| --history N | 360 default, max 1000 (500 with 30s) |
| --native-30s | Optional extra stream per instrument |
| --orderflow | Discover advanced features |
| --authorized | Confirm permitted advanced access/renewal |
| --flow-budget N | Maximum active advanced streams, 1–60; default 5 per ticker |
| --refresh-capabilities | Retest cached negatives once |
| --remember | Windows DPAPI token storage |
| --auto-renew | Legacy paired Chrome extension |
| --browser-renew | Existing signed-in Chrome; user-approved connection (144+) |
| --dedicated-browser-renew | Optional separate Chrome profile |
| --browser-login | Explicit sign-in again with --dedicated-browser-renew |
| --workspace | Load the watchlist saved in the dashboard |
| --record-flow PATH | SQLite feature journal |
| --port N | 8789 default |
| --no-browser | Don't open dashboard |
| --snapshot | Explicit legacy snapshot collector |
| --interval / --requests-per-second / --no-cache | Legacy snapshot controls |

Legacy snapshot mode polls quotes and stores locally sampled bars, not native history or volume; it does not support advanced streams or auto-renew. The old `local_api` is a prototype; use `serve` instead.

## Verification and diagnostics

```powershell
py -m unittest discover -s tests -v
py -m tpscraper.native_probe history --remember --count 360
py -m tpscraper.native_probe candles --remember --count 360 --seconds 15
py -m tpscraper.native_probe quotes --remember --seconds 15
```

Run live probes only where authorized. Advanced diagnostics:

```powershell
py -m tpscraper.data_suite --remember --authorized --ticker "CXBNCE:BTC/USDT" --only history candles quotes trades orderbook footprint heatmap tpo --output btc_report.json
py -m tpscraper.data_suite --remember --authorized --ticker "CXBNF8:XAU/USDT.P" --only history candles quotes trades orderbook footprint heatmap tpo --output gold_futures_report.json
py -m tpscraper.data_suite --remember --authorized --ticker "FXPPST:XAU/USD" --only history candles quotes trades orderbook footprint heatmap tpo --output gold_spot_report.json
```

Renko is omitted: the BTC test returned data but took 112 seconds. The observation timer is checked on message arrival, so it is not a strict wall-clock deadline. Ctrl+C saves completed diagnostic results. Do not share raw HAR captures or credentials.

### Observed live probe results — November 24, 2026

| Service | Binance BTC | Binance gold perpetual | Pepperstone XAU/USD |
|---|---:|---:|---:|
| History bars | 30 | 30 | 30 |
| Candle messages | 46 | 48 | 52 |
| Quote messages | 21 | 22 | 24 |
| Trade records | 913 | 282 | 56 |
| Book snapshots/updates | 61 | 57 | 0 |
| Footprint messages with data | 11 | 12 | 11 |
| Heatmap messages with data | 8 | 8 | 0 |
| TPO profiles/updates | 7 | 7 | 7 |
| Renko records | 31 | not tested | not tested |

These are sequential short observations, not concurrent synchronized market comparisons. The BTC book snapshot contained 64,275 price levels; Gold perpetual contained 24,332. Pepperstone footprint counts matched volume in the sample and trade-like events had unit quantities, consistent with tick-based activity. Heatmap availability does not establish all quantity semantics. Earlier Gold candle test returned 360 distinct 1m bars and 53 same-bar updates over 15 seconds. Quote exchange timestamps were absent.

### Current validation limits

The separate live probes succeeded as described above. Initial Chrome pairing/token acquisition and Gold dashboard startup are confirmed. Sustained all-ticker discovery, reconnections, renewal through token expiry, and long-run memory/performance remain unverified on the user's machine. On November 24, 2026, the user successfully compiled the checkout at `76ead12` and ran all 76 offline regression tests on Windows with Python 3.14 (1.625 seconds, zero failures). Two expected HTTP error responses produced test-only ResourceWarnings; the subsequent test cleanup closes those responses and still needs a rerun. The Bitcoin preset also successfully acquired authorization through the paired Chrome extension and started its one-instrument native dashboard. This verifies startup, not continuous feed availability.

A subsequent BTC-only live check on November 24 confirmed connected native push, one instrument with history ready, one fresh timestamped price and one fresh synchronized book at approximately 122 and 157 seconds of uptime. All seven streams (quotes, candles, trades, order book, footprint, heatmap and TPO) reported accepted messages, one attempt each, zero errors and zero retries. The raw quote usable count was zero because no eligible exchange timestamp was available on that path; the independent timestamped live-price count was one. This is a successful short-duration integration check, not evidence of renewal across expiration, lossless collection or long-run stability. The dashboard JavaScript syntax has been checked. Use the diagnostic results and freshness fields rather than assuming every service works. No verified prediction edge or latency guarantee.

## Reliability and acceptance checks

The dashboard includes a live reliability scorecard. Successful token rotations are counted separately from renewal attempts; an increment alone does not prove uninterrupted coverage. The Windows soak monitor samples local API health, per-stream diagnostics and the Python process CPU, private memory, working set, handles and threads. Run in a separate PowerShell window from the repository root:

```powershell
powershell -NoProfile -File .\\scripts\\soak.ps1 -Hours 6
```

The default output is `$env:USERPROFILE\\Downloads\\tpscraper_soak.jsonl`. Use `-Hours 0` for monitoring until Ctrl+C and `-Output` for a unique output file. CPU percentage is normalized across logical processors; Chrome/Playwright child processes are not included. Sample intervals do not establish continuous lossless coverage. Briefly disconnect/reconnect the network during the run and verify timestamped prices become ineligible during the outage and resume after recovery; check the stream counters and historical gaps. Do not disconnect while using the engine for real-money decisions. The monitor does not intentionally interrupt network access or change system settings.

The user reported a rolling sample of 4,096 BTC trade events with median provider timestamp-to-receipt lag 129.74 ms, P95 275.51 ms, maximum 464.62 ms and zero detected book gaps. Earlier an individual event showed negative arrival lag; the user's later clock check against Microsoft's time service was within 20 ms. These measurements are not independent exchange latency verification. No hardcoded clock-offset correction is applied.


- Stream recovery uses capped exponential backoff (up to 120 seconds) with jitter. Successful sustained streams reset the failure backoff. Worker shutdown must complete before a new credential generation starts; an incomplete shutdown stops collection rather than allowing overlapping writers.
- Duplicate or rejected trade messages do not renew the receipt-freshness clock. Timestamped prices remain separate from raw quotes. Best bid/ask are checked against the current synchronized book even within the cached depth-feature interval.
- A reconnect clears the candle history-ready marker until the provider's initial history marker arrives again. Existing historical bars are retained; `missing_bar_intervals` measures gaps in the observed timeline, including legitimate closed-market periods. `bar_receipt_age_s` is receipt age, not proof of exchange latency. No market-hours calendar is assumed.
- Completed-bar statistics are cached between historical revisions. Unknown or unavailable data is not interpreted as a trading signal.
- The browser renewal path still restarts upstream streams after obtaining a new credential; uninterrupted handover is not claimed.

Run `py -m compileall -q tpscraper tests` and `py -m unittest discover -s tests -v` after pulling. GitHub Actions runs these offline checks on Windows and Linux with Python 3.11 and 3.14, subject to repository Actions availability. The added regression suite checks stale/crossed depth, best-price cache correctness, explicit and omitted zero-size deletions, duplicate trade receipt, out-of-order events, reconnect history readiness, TPO block merges and disconnect invalidation. The 76-test Windows Python 3.14 run at `76ead12` passed; later revisions and the Linux/CI matrix still need independent confirmation.

For live acceptance, begin with `--watchlist btc` before expanding to Gold or `crypto15`. Keep Chrome signed in and observe at least two token expirations. Inspect `/api/health` and `/api/diagnostics` for continued accepted messages, recovered streams, fresh books, timestamped prices, and successful reauthorization. Test a brief network interruption, then confirm history backfill and that stale data became ineligible during the interruption. Verify prices and spread against the identical TakeProfit instrument; a healthy receipt connection alone does not prove undelayed exchange data.

## Maintenance

Update this README whenever CLI flags, API fields, feed semantics, or validation status change. Keep observed behavior separate from implemented-but-untested features. Record new live validation evidence with dates, instrument identifiers and exact limitations. Never commit secrets, raw authenticated captures, or user account data.

### Changelog — 2026-11-24

- Replaced legacy polling as default with native candle and quote streams.
- Added advanced market-data diagnostics, versioned depth state, flow recording and local catalog search.
- Added opt-in paired Chrome renewal.
- Removed advanced symbol whitelist; added capability cache, subscription budget, responsive dynamic market panels.
- Added independent timestamped live trade price, arrival-age metrics, explicit nullable spread/volume/VWAP, and ~250ms local SSE delivery.

- Reliability hardening: independent feature refusal handling, expiring capability rechecks, jittered reconnects, bounded shutdown, accepted-record counters, current-book checks, timestamp freshness guards, candle readiness invalidation, cached bar statistics, verified worker merge conventions, and offline CI coverage.

- Added optional consent-based dedicated Chrome renewal, workspace management, stable saved ticker keys, live reliability scorecard, Windows soak monitor, and offline browser/workspace tests. Live dedicated-browser renewal and soak acceptance remain pending.
