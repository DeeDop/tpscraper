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
