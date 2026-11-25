# Local HTTP API (v1)

Base URL: `http://127.0.0.1:8789`. The service is local and unauthenticated; never publish it through a tunnel or reverse proxy. Requests must use the literal loopback address and matching port. Responses are JSON except HTML and server-sent events. JSON timestamps are UTC; numeric epoch timestamps are seconds. Prices and quantities use provider units. Missing values are JSON null or absent optional fields. Do not interpret missing data as zero.

## Routes

| Method | Path | Parameters / response |
|---|---|---|
| GET | /api/version | api_version, version |
| GET | /api/instruments | instruments: key, symbol, name, group, decimals |
| GET | /api/quotes | Optional key; quotes mapping, connected, mode, reason, generated_utc, api_version |
| GET | /api/bars | Required key; resolution=60 or 30 seconds, limit=1..1000 (360 default), closed=1 to filter elapsed bars |
| GET | /api/orderflow | Optional key; orderflow mapping, detailed profiles and trade tape |
| GET | /api/health | Global connection, freshness counts, uptime, PID, Python threads |
| GET | /api/diagnostics | Stream attempts, accepted messages, errors, retries, renewals |
| GET | /api/catalog | q, provider, limit (1..500); offline entries and counts |
| GET | /api/snapshot | Full dashboard state and retained history |
| GET | /api/stream | SSE: full, tick, quotes |
| GET | /api/stream/quotes | SSE: quotes only |
| GET | /api/workspace | Active/saved pairs, available presets, max instruments |
| POST | /api/workspace | JSON {"pairs":["PROVIDER:TICKER"]}; same-origin browser only; restart required |

Use `/api/instruments` to resolve exact active keys rather than assuming symbol text is the key. Known workspace instruments use preset keys. Unknown workspace keys are stable hashes. Direct CLI custom ticker keys use positional custom1, custom2, etc. Existing unversioned URLs are retained for compatibility; the quote payload includes api_version=1. Version 1 is an initial compatibility target, not a promise that pre-release fields never change.

Errors: invalid request 400; loopback host or origin mismatch 403; unknown route or instrument 404 (orderflow may return an empty mapping); unsupported method 501; overloaded or unavailable snapshot 503. Error responses normally contain `{"api_version":1,"error":{"status":404,"message":"Unknown instrument key"}}`. Overload may return an empty body. HTTP 200 means the service responded, not that the underlying market is live.

## Quotes

Example consumer:

```python
import json
from urllib.parse import urlencode
from urllib.request import urlopen

def read(path):
    with urlopen("http://127.0.0.1:8789" + path, timeout=3) as response:
        return json.load(response)

data = read("/api/quotes?" + urlencode({"key": "btc"}))
q = data["quotes"]["btc"]
if data["connected"] and q.get("live_price_usable"):
    print(q["live_price"], q["live_price_event_utc"])
```

| Field | Meaning |
|---|---|
| symbol | Exact provider/ticker |
| last | Raw provider quote; may be stale or untimestamped |
| exchange_utc / price_age_s | Raw quote provider timestamp and age, when supplied |
| received_utc / receipt_age_s | Raw quote receipt timestamp and age |
| status | LIVE, UNVERIFIED, STALE, UNAVAILABLE, DISCONNECTED (native mode) |
| usable_short_term | Raw quote passes event/receipt freshness and connection checks |
| live_price | Eligible timestamped candidate from quote or trade event; null otherwise |
| live_price_usable | Candidate passes current freshness gates |
| live_price_source | timestamped_quote or timestamped_trade_event |
| live_price_event_utc / live_price_received_utc | Candidate event and receipt times |
| live_price_age_s / live_price_arrival_lag_s | Event age and provider-to-local arrival lag (trade path) |
| bid / ask / spread | Fresh synchronized book values, otherwise null |
| volume / turnover | Provider session totals |
| volume_semantics | Provider-reported quantity or broker tick activity |
| history_vwap / history_vwap_bars | Weighted value over retained elapsed bars with complete volume and turnover |
| bar_receipt_age_s / missing_bar_intervals | Candle receipt age and observed timeline gaps |
| history_ready | Initial one-minute history marker received in current generation |
| orderflow | Optional independent flow summary |

A global connected flag means at least one instrument is receiving eligible or receipt-only updates. Always check the specific record. Freshness gates generally require recent provider and local receipt timestamps (five seconds, with limited clock-skew tolerance). These are observed time relationships, not independent exchange latency measurements. A raw quote may be unusable while a timestamped trade is usable. Reject stale data again at the consumer if delivery or processing takes too long.

## Candles

`GET /api/bars?key=btc&resolution=60&limit=120&closed=1`

The response contains key, symbol, resolution_seconds, history_ready, bars and generated_utc. Native rows use t (epoch seconds), o, h, l, c, v, optional value/other provider fields, and closed. Bars are ordered by timestamp. A repeated timestamp replaces its previous cumulative values, rather than adding volume. `closed` means the bar's time interval has elapsed; it is not a provider finalization guarantee. Late corrections can occur. History is in-memory and bounded; 30-second data requires the optional native subscription. Missing intervals are not synthesized. Gaps can reflect market closures or connectivity loss.

## Order flow

`GET /api/orderflow?key=btc` returns detailed snapshots, while quotes contain lightweight summaries when orderflow is enabled.

- **streams**: independent service status, connection status, receipt age.
- **book**: freshness, synchronized flag, version, provider time, bid/ask/spread, bounded top levels, size imbalance and depth changes where available. Sequence gaps, invalid levels or crossed books invalidate freshness.
- **latest_trade**: price, event_epoch, received_epoch, event_age_s, receipt_age_s, arrival_lag_s, fresh.
- **trade_windows**: 5/15/30/60-second counts, buy/sell/unknown volumes, delta, imbalance, largest quantity and price change. Use both fresh and complete. Complete describes observed window warm-up and retention, not lossless upstream coverage.
- **latency**: rolling arrival sample count, median_ms, p95_ms, max_ms. Timestamp skew and backfill may affect samples.
- **footprint**: latest profile, freshness, observed elapsed-profile CVD; detailed route includes recent profiles. Not full-session CVD.
- **tpo**, **heatmap**: provider profile state; some incremental quantity semantics are not verified. Do not infer unknown volume from row occupancy.
- **book_gaps**, **duplicates**, **unidentified**: observed diagnostic counts.

Broker tick activity is not exchange-traded volume. Unknown data must remain unknown.

## Streaming

Use `/api/stream/quotes` for consumers that only need prices and summary features. Each SSE message has event type quotes and a JSON data line. Dashboard clients use `/api/stream`, which additionally emits full and tick events. Cadence is approximately 250 ms for local ticks and two seconds for full history, plus computation and network overhead. This is not an upstream timing guarantee. SSE is a snapshot stream; there are no replay IDs and reconnects can miss intermediate changes.

```javascript
const feed = new EventSource("/api/stream/quotes");
feed.addEventListener("quotes", (event) => {
  const frame = JSON.parse(event.data);
  const q = frame.quotes.btc;
  if (frame.connected && q?.live_price_usable) {
    console.log(q.live_price);
  }
});
```

Run this in the local dashboard's origin. External websites are not granted CORS access. Disconnect or mark the local state stale on transport errors. Keep consumer counts small; the server caps concurrent requests, including SSE clients, at 16. Close unused streams.

## Health and diagnostics

Health distinguishes receipt-based connection from timestamped live-price eligibility and fresh book counts. Diagnostics counters are per process and service; authorization renewals count attempts, renewal_successes counts later-expiring token generations. This does not prove every stream remained connected during renewal. See [operations](OPERATIONS.md) for validation.
