# tpscraper — TakeProfit market data API

A Python market-data collector and local API for TakeProfit. Stream live quotes, historical OHLCV candles, trade events and available Level 2 order-book data into a browser dashboard or another application using JSON over HTTP and Server-Sent Events (SSE).

Designed for developers who need one local price-feed service for multiple instruments, with timestamped updates, freshness checks and automatic reconnection. Supports crypto, forex (FX), precious metals, equity indices and other available provider instruments.

This is an unofficial integration. Use it only with your own account and where the platform and its data providers permit programmatic access. It does not grant exchange entitlements, guarantee real-time prices, place trades, or redistribute market data. For supported commercial integrations, see [TakeProfit's Platform API](https://www.takeprofit.com/docs/platform-api/overview).

## Project origins

`tpscraper` is a separately maintained TakeProfit adaptation of [tvscraper](https://github.com/Tekyyy/tvscraper), originally developed by Tekyyy, and builds on the work in [DeeDop/tvscraper](https://github.com/DeeDop/tvscraper). The upstream project targets TradingView; this project targets TakeProfit and provides its own authorization, transport, dashboard, and Windows distribution. The repositories are maintained separately.

The original project is MIT-licensed. Its copyright notice is retained in [LICENSE](LICENSE), alongside the notice for this project's modifications.

## What you can build

Run one collector and let several local applications consume the same market-data feed instead of opening separate upstream connections for each application.

| Application | Typical integration |
|---|---|
| Discord ticker or price-alert bot | Read eligible quotes in a local bot process and evaluate price thresholds. Display or send data only to recipients covered by the provider's redistribution terms. |
| Prediction and forecasting application | Combine synchronized returns, recent candles, order-flow features and multiple market inputs. Use per-symbol freshness flags and reject stale or unverified data. |
| Custom stock, forex or crypto dashboard | Discover provider/ticker pairs and render quotes, candlesticks, and available depth from the JSON API. |
| Algorithmic trading research and paper trading | Record observations locally, calculate features and evaluate strategies independently of collection. No order execution is included. |
| Portfolio monitor and desktop price widget | Use a filtered quote endpoint or the quote-only SSE stream; handle closed markets and unavailable instruments explicitly. |
| Quantitative research and data validation | Analyze retained OHLCV, price relationships, trade pressure, timestamp alignment and observed feed quality. |

For example, a model tracking gold could consume gold, silver, currency and Treasury price proxies together, then make its own independent forecast. A crypto application could compare spot and perpetual instruments. Neither approach establishes a predictive edge or makes these prices official settlement references.

All clients run on the same trusted computer; the service does not expose a public market-data server or grant permission to republish prices in Discord, on websites or through another API. Access, supported features, delay and redistribution rights depend on the provider and account.

## Windows portable release

For a computer that does not need the development source, use the [Releases page](https://github.com/DeeDop/tpscraper/releases). Download the `tpscraper-windows-x64.zip` asset, verify it against `SHA256SUMS.txt`, extract the entire ZIP, and run `run.cmd`. The portable build bundles the Python runtime and dependencies; it requires Chrome, a supported Windows x64 installation, and first-time account pairing on each computer. It does not require Git or Python to be installed. The ZIP intentionally excludes Git history, source tests, development scripts, local databases and credentials. Builds are unsigned pre-releases for private testing; live authorization and feed behavior require separate validation.

## Quick start

Requirements: Windows 10/11, Python 3.11 or later, Chrome, and an authorized TakeProfit account. No administrator privileges or fixed installation directory are required.

```powershell
git clone https://github.com/DeeDop/tpscraper.git
cd tpscraper
```

Alternatively, download the repository as a ZIP from GitHub and extract it anywhere you have read access. Double-click `run.cmd` in the extracted folder. It creates an isolated per-checkout Python environment in your user data directory, installs dependencies on the first launch or when requirements change, and asks for permission before connecting. To install without connecting, run `run.cmd --setup-only`.

For a terminal-based setup, `py launch.py --setup-only` works from the checkout. You may also install dependencies into a virtual environment yourself and use the original `py -m tpscraper` commands with the appropriate interpreter.

### Connect your account

1. Sign in to [TakeProfit](https://takeprofit.com/) in your usual Chrome profile.
2. Open `chrome://extensions/`, enable Developer mode, and select **Load unpacked**. Choose the repository's `chrome-renew` directory.
3. Start the service:

   ```powershell
   .\run.cmd
   ```

4. Confirm permission in the launcher. On the first run, open the extension popup, enter the local pairing code printed in the terminal, and select **Authorize and pair**.

Pair once on each computer and in each Chrome profile you intend to use. Credentials are local to the operating-system user and are never transferred with a clone or ZIP. The extension remembers the pairing. Subsequent runs use the same signed-in Chrome session without another pairing code or token copy. Chrome must remain open and signed in. If authorization expires or is refused, sign in again where permitted and restart. This is browser-session reuse, not an independent OAuth or SSO provider.

Open **http://127.0.0.1:8789/**. Stop the service with Ctrl+C.

> Existing installations: use extension v1.2.0 or newer. Keep the extension in the same installed folder and reload it when updating. If the console says a saved pairing was loaded, open the popup and click **Check connection now**; do not reset pairing unless it is missing or mismatched. See [automatic connection and updates](docs/SETUP.md#automatic-connection-and-updates).

## Instruments

Use **+ Manage tickers** in the dashboard to search the catalog, choose a preset, or enter an exact provider/ticker pair. Save the workspace and restart to apply changes.

To specify instruments directly:

```powershell
.\run.cmd dashboard --authorized --auto-renew --ticker "CXBNCE:BTC/USDT" --ticker "FXPPST:XAU/USD"
```

Up to 12 instruments per process. Custom symbols do not have to appear in the offline catalog. Availability and data entitlement are determined by the provider.

| Preset | Instruments |
|---|---|
| `btc` | Bitcoin spot |
| `btc-depth` | Bitcoin spot and perpetual |
| `crypto15` | Nine crypto candidates |
| `gold` | Gold, silver, currencies and Treasury price proxies |
| `markets15` | Gold and FX |
| `realtime` | Metals, crypto and indices |

These presets are convenience lists, not exchange entitlement or latency guarantees.

## Local API

Run without opening the dashboard (using the launcher-managed environment):

```powershell
.\run.cmd serve --workspace --watchlist btc --authorized --auto-renew --orderflow
```

The API listens on `127.0.0.1:8789`. It is intended for trusted software on the same computer.

| Endpoint | Description |
|---|---|
| `GET /api/version` | API and application version |
| `GET /api/instruments` | Active instrument keys and metadata |
| `GET /api/quotes` | Latest quote records and freshness |
| `GET /api/quotes?key=btc` | One instrument |
| `GET /api/bars?key=btc&resolution=60&limit=100` | Retained candles |
| `GET /api/orderflow?key=btc` | Depth, tape and profiles, if available |
| `GET /api/stream/quotes` | Lightweight quote SSE stream |
| `GET /api/stream` | Dashboard SSE stream |
| `GET /api/health` | Collection status |
| `GET /api/diagnostics` | Stream counters |
| `GET /api/catalog?q=BTC` | Offline instrument search |

```python
import json
from urllib.request import urlopen

with urlopen("http://127.0.0.1:8789/api/quotes?key=btc", timeout=3) as response:
    data = json.load(response)

quote = data["quotes"]["btc"]
if data["connected"] and quote.get("live_price_usable"):
    print(quote["live_price"], quote["live_price_source"])
```

Do not substitute a stale or untimestamped quote for a usable timestamped price. The local API does not establish market-data entitlement or guarantee that a provider's timestamp is accurate.

## Data and reliability

- Native push quotes and one-minute OHLCV history; optional 30-second candles.
- Optional trades, depth, footprint, liquidity heatmap and TPO subscriptions.
- Independent event and receipt timestamps, freshness checks, and versioned order-book synchronization.
- Bounded stream retries, explicit permission failures, and local diagnostic counters.
- A missing feature is unavailable, not zero. No synthetic historical gaps are filled.

Advanced subscriptions require `--orderflow --authorized`. The default advanced subscription budget is at most 12 streams; lower it with `--flow-budget` as needed. Do not increase it to bypass service limits.

## Documentation

- [Installation and account connection](docs/SETUP.md)
- [HTTP and streaming API](docs/API.md)
- [Operations and validation](docs/OPERATIONS.md)
- [Instrument reference and ticker discovery](docs/INSTRUMENTS.md)
- [Security and local storage](SECURITY.md)

## Development

The main branch is the developer checkout. To publish a new portable build, increment `release/VERSION` to an unused version tag and push it to main. The Windows release workflow runs the regression and repository privacy checks, builds a fresh distribution, checks the executable before and after ZIP extraction, and publishes the ZIP and checksum only after those steps succeed. Use the custom release asset, not GitHub's automatically generated source archives. A build can also be triggered from the Actions tab. Release assets inherit repository visibility.


```powershell
py -m compileall -q tpscraper tests
py -m unittest discover -s tests -v
```

The offline test suite uses synthetic fixtures, decoder regression fixtures and local loopback services. Live account access, browser renewal, provider availability and long-running resource usage require separate integration testing.

The project remains pre-release. Do not expose the API publicly, commit account credentials, or redistribute provider data. Source code is available under the [MIT License](LICENSE); platform access and data rights are separate.
