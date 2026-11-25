# tpscraper

A local, read-only market-data service for TakeProfit. Stream quotes and candles into a browser dashboard or consume them from another program through HTTP and server-sent events.

This is an unofficial integration. Use it only with your own account and where the platform and its data providers permit programmatic access. It does not grant exchange entitlements, guarantee real-time prices, place trades, or redistribute market data. For supported commercial integrations, see [TakeProfit's Platform API](https://www.takeprofit.com/docs/platform-api/overview).

## Quick start

Requirements: Windows, Python 3.11 or later, Chrome, and an authorized TakeProfit account.

```powershell
git clone https://github.com/DeeDop/tpscraper.git
cd tpscraper
py -m pip install -r requirements.txt
```

### Connect your account

1. Sign in to [TakeProfit](https://takeprofit.com/) in your usual Chrome profile.
2. Open `chrome://extensions/`, enable Developer mode, and select **Load unpacked**. Choose the repository's `chrome-renew` directory.
3. Start the service:

   ```powershell
   py -m tpscraper dashboard --workspace --watchlist btc --authorized --auto-renew --orderflow
   ```

4. On the first run, open the extension popup, enter the local pairing code printed in the terminal, and select **Authorize and pair**.

The extension remembers the pairing. Subsequent runs use the same signed-in Chrome session without another pairing code or token copy. Chrome must remain open and signed in. If authorization expires or is refused, sign in again where permitted and restart. This is browser-session reuse, not an independent OAuth or SSO provider.

Open **http://127.0.0.1:8789/**. Stop the service with Ctrl+C.

> Existing installations: reload the updated extension in Chrome and pair once using the new version. If the code is not displayed, start with `--reset-pairing`.

## Instruments

Use **+ Manage tickers** in the dashboard to search the catalog, choose a preset, or enter an exact provider/ticker pair. Save the workspace and restart to apply changes.

To specify instruments directly:

```powershell
py -m tpscraper dashboard --authorized --auto-renew --ticker "CXBNCE:BTC/USDT" --ticker "FXPPST:XAU/USD"
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

Run without opening the dashboard:

```powershell
py -m tpscraper serve --workspace --watchlist btc --authorized --auto-renew --orderflow
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
- [Security and local storage](SECURITY.md)

## Development

```powershell
py -m compileall -q tpscraper tests
py -m unittest discover -s tests -v
```

The test suite uses synthetic data and local loopback services. Live account access, browser renewal, provider availability and long-running resource usage require separate integration testing.

The project remains pre-release. Do not expose the API publicly, commit account credentials, or redistribute provider data. A source-code license and publication review are required before a public release.
