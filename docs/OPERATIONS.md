# Operations

## Start and stop

Use dashboard for interactive use and serve for a headless local API. Stop with Ctrl+C. Run one instance on the fixed browser bridge port. Use `/api/instruments` to discover active keys and `/api/health` to check readiness before consuming prices.

## Collection behavior

The native collector uses a tagged quote subscription and a candle subscription per ticker. Optional order flow opens additional independent subscriptions with a bounded budget and staggered startup. Feature-specific access denial disables that feature for the process; global authorization and rate refusals stop collection. Transient transport failures use exponential backoff and jitter, capped at 120 seconds. Cached no-data, unavailable and unsupported observations are eligible for later rechecks. A quiet session is not definitive proof that a feature is unsupported.

A credential rotation requires a fresh authorized token, closes the previous stream generation, then restores history and subscriptions. A gap is possible. Stale prices or unsynchronized books must not be used while reconnecting. Local receipt cadence is not proof of current exchange data.

## Test suite

```powershell
py -m compileall -q tpscraper tests
py -m unittest discover -s tests -v
```

The offline regression workflow runs on Windows and Linux with Python 3.11 and 3.14. No real credentials are required. Review the workflow results on the exact revision under test.

## Live acceptance

Perform this checklist before a public release or using the service in production:

1. Install from a clean checkout; start with one instrument and confirm initial history.
2. Pair the extension, stop and restart Python and Chrome, then verify pairing persists and the extension reauthorizes without copying a token.
3. Run through at least two token expiration cycles. Confirm successful rotations and fresh streams afterward.
4. Briefly interrupt network access during a noncritical test. Confirm stale state becomes ineligible and data recovers without duplicated workers.
5. Compare timestamps, prices and depth with the identical provider instrument in TakeProfit.
6. Verify the quote, bar, catalog, workspace and SSE endpoints from separate local clients.
7. Expand to the intended watchlist within provider limits; monitor CPU, memory, threads and handles over several hours.
8. Disable the extension, test denied access, and verify no retry loop attempts to bypass a provider refusal.

Windows monitor:

```powershell
powershell -NoProfile -File .\scripts\soak.ps1 -Hours 6
```

See the script parameters for custom duration, output and port. The monitor writes JSONL of local API and Python process metrics, not credentials. It does not include Chrome's own resource usage.

A successful short sample or offline test is not evidence of a lossless feed, exchange latency, unattended renewal, or a predictive strategy.

## Storage and cleanup

Workspace and capability cache live under LocalAppData on Windows. Optional SQLite feature journals are written to the explicitly selected path. These are local research files, not redistributable datasets. Delete only after stopping the service. Never commit logs, authenticated network captures, credentials or recorded market-data samples.

## Publication checklist

- Review the entire working tree and every reachable commit/tag for secrets, personal paths, captures, and data that cannot be redistributed. Removing a file from the current branch does not remove it from history.
- Confirm provider terms and permitted use of each integration, including catalog redistribution.
- Choose a source-code license; this does not license third-party market data.
- Verify fresh install, test matrix, pairing persistence, expiry, network recovery and long-duration performance.
- Review platform dependencies, extension permissions and the API's loopback-only security boundary.
- Keep visibility private until the above checks are complete.
