# tpscraper

Experimental native HTTP/2 and gRPC-Web market-data research client. Use only with your own authorized account, where permitted by TakeProfit and its data providers. No entitlement bypass, browser credential extraction, or trading functionality.

## Install

```powershell
py -m pip install -r requirements.txt
py -m unittest discover -s tests -v
```

## First real quote test

```powershell
py -m tpscraper probe --prompt
```

Supply a newly issued accessToken locally when prompted. The credential stays in memory and is discarded when the process ends. Do not use a previously exposed token. No credentials are written to logs or diagnostics.

The request format matches the observed ListQuotes request structure, with the default instrument FXPPST:XAU/USD. A candidate price is decoded from a repeated fixed-point numeric field in captured responses, but its semantics and freshness are not verified. Compare it with the same provider and symbol in the chart. A successful HTTP response alone is not evidence of real-time access.

## Optional experimental renewal

Only if permitted, the session mode tests the observed first-party token endpoint with a session credential explicitly supplied by the user. It retains rotated credentials in memory, refreshes shortly before access-token expiry, and stops on refusal or rate limiting. It never reads browser storage. This is not a documented third-party authorization flow and has not been validated against the live service.

```powershell
py -m tpscraper probe --session --repeat 65 --interval 15
```

Run the single quote test first. The longer test is for observing expiration/renewal, not for production data collection. If authorization fails, stop and reauthorize normally. No automatic retries on 401/403/429.

## Other instruments

```powershell
py -m tpscraper probe --prompt --symbol XAU/JPY --provider FXPPST
```

Supply an actual available symbol/provider pair. Dynamic discovery remains pending.

## Local API

```powershell
py -m tpscraper.local_api
```

Loopback port 8789: /api/quotes, /api/snapshot, /api/health and /api/stream. The feed intentionally remains empty until actual quote semantics, exchange timestamps and entitlement are validated. Candle streaming and historical schemas remain unverified.

## Security

Never commit cookies, tokens, HAR files, raw network captures or account information. Share only probe_result.json, which contains bounded diagnostics and candidate prices, not credentials or raw response bytes.

## Regular Chrome console

Run `py -m tpscraper.console --local-chrome` on Windows. Approve opening your normal Chrome window. Copy the successful JSON response (or accessToken) on the first-party token page, then select `c` to explicitly permit a one-time local clipboard read, or `p` to paste the token into a hidden prompt. Renewal repeats this consent flow. No existing Chrome profile files or cookies are extracted, and Playwright is not required. The token remains in memory; clear the copied credential from the clipboard after use. Use only if permitted by the provider. The feed is polling and price semantics are not yet verified.

### Optional encrypted storage and Chrome profile selection

`py -m tpscraper.console --local-chrome --remember` stores only the access token, encrypted with current-user Windows DPAPI, at `%LOCALAPPDATA%\\tpscraper\\auth\\access.dpapi`. It reuses the token until near expiration, then prompts for fresh authorization in normal installed Chrome. Add `--chrome-profile "Profile 1"` (or `Default`) if Chrome opens a different profile. The profile directory name is visible on Chrome's chrome://version page; no profile files are read by tpscraper. No extra dependencies are needed. `py -m tpscraper.credential_store status` shows expiration without printing the token, and `py -m tpscraper.credential_store clear` deletes the local encrypted file. This does not renew the browser session unattended or revoke server-side credentials.

## Captured instrument catalog

See [instrument documentation](docs/INSTRUMENTS.md), [562 captured provider/symbol pairs](docs/takeprofit_tickers.csv), and [provider codes](docs/takeprofit_exchanges.csv). Rebuild offline with `py -m tpscraper.har_catalog path-to-local.har --output docs`. This catalog reflects captured screener results, not verified live quote entitlements.

## Easy ticker input

Run `py -m tpscraper.console --local-chrome --remember` and type a ticker at the prompt. Unique captured matches are filled automatically; ambiguous matches offer a numbered selection. For any new ticker, enter its exact provider code. The captured CSV remains reference documentation, not an allowlist. You can bypass it with an exact pair, e.g. `py -m tpscraper.console FXPPST:XAU/USD --local-chrome --remember --interval 1`. A returned candidate quote does not by itself verify real-time access or price semantics. The console stops on access denial or rate limiting.

## Dashboard and predictor service (TakeProfit)

Ported the original tvscraper dashboard frontend. Run:

```powershell
py -m tpscraper dashboard --remember
py -m tpscraper dashboard --watchlist gold --remember
py -m tpscraper serve --watchlist markets15 --remember
```

Run only one service per port. The dashboard defaults to http://127.0.0.1:8789/ and exposes /api/snapshot, /api/quotes, /api/health, /api/stream (full, tick and quotes SSE events). The older standalone local_api is an empty prototype; use serve instead. Auth is normal local Chrome with optional DPAPI storage. Add --no-browser to avoid opening the dashboard page. A minimum 15-second watchlist sweep is the default, with requests paced globally to at most one per second. No request bursts, no retries on rate limiting or authorization denial. Use only within provider permissions.

The default eight, gold nine and markets15 twelve keys match tvscraper. Candidate symbols not seen in the capture are labeled in the presets. Treasury instruments are price proxies, not yields. VIX and index instruments may be CFDs/forwards, not exact cash indexes. Custom watchlists: repeat --ticker FXPPST:XAU/USD --ticker CXBNCE:BTC/USDT. All symbols are tested as submitted; no catalog allowlist.

This initial dashboard uses quote snapshots, not native push streaming. 30s/1m candles are built from local receipt-time samples and 5m/15m rolled up; no historical exchange bars, exchange volume, bid/ask, or verified exchange timestamps yet. Correlation is exploratory and requires at least ten overlapping consecutive completed 1-minute returns. Tiles display changes since first observation, not session change. API marks every quote usable_short_term=false until exchange timestamp and price semantics are verified. Do not use as Kalshi settlement or as a verified trade signal. Native candle stream and history remain future work.
