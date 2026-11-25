# Installation and authorization

## Requirements

Windows 10/11, Python 3.11+, Google Chrome with an authorized TakeProfit account, and permission for the requested market-data subscriptions. Python dependencies are listed in `requirements.txt`. The Chrome extension is loaded locally; it does not require a Chrome Web Store account.

## Install anywhere

Download the repository ZIP from GitHub and extract it, or clone it into any writable folder, including paths with spaces. There is no fixed drive letter or required installation directory.

On Windows, double-click `run.cmd` or run `.\run.cmd --setup-only` from PowerShell. The launcher uses the installed Python to create a per-checkout virtual environment under the current user's local application-data directory. It installs requirements on first use and when `requirements.txt` changes. Moving the checkout or using another computer creates a separate environment. No existing Python installation or virtual environment is modified.

For a setup-only check that does not authorize or start market data:

```powershell
.\run.cmd --check
```

A manual virtual-environment setup is also supported:

```powershell
git clone https://github.com/DeeDop/tpscraper.git
cd tpscraper
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m tpscraper dashboard --workspace --watchlist btc --authorized --auto-renew
```

If using the system Python, replace the virtual-environment Python path with `py`. Keep commands in the checkout directory.

## Pair once

For the standalone Windows release, download the custom ZIP asset from [Releases](https://github.com/DeeDop/tpscraper/releases), not the automatic source archive. Extract all files, keep `_internal` next to the executable, and use `run.cmd`. Python and Git are not required for this distribution.

1. Open your existing Chrome profile and sign in normally at takeprofit.com.
2. Open `chrome://extensions/`, enable Developer mode, then Load unpacked; choose `chrome-renew`.
3. Start `run.cmd` (or the source launch command above). Approve access. If a new pairing code is printed, enter it in the extension popup and select **Authorize and pair**. If the console reports a saved pairing, do not enter another code.
4. Keep Chrome running. The dashboard opens once the account is authorized.

The extension requests authorization only when a paired local process has a pending renewal request. It uses Chrome's existing signed-in session; it does not inspect cookies, browser storage, unrelated network traffic, or passwords. The pairing secret is saved in Chrome extension-local storage and in Windows current-user DPAPI storage. The provider token is not saved by the extension.

On later launches the paired extension recognizes the local process and performs authorization again. No repeated pairing or token copying is needed while the session and pairing remain valid. The extension may take one alarm interval to respond. Pair separately on each computer; do not copy DPAPI files, browser profiles, or pairing secrets between machines. A moved source folder may require reloading the unpacked extension from its new location. This is not a substitute for TakeProfit's account login or entitlement checks.

If the extension is disabled, its pairing is lost, or the pairing secret is mismatched, stop the service and run with `--reset-pairing`. Reload the extension when upgrading its source. Select Disable renewal in the popup to remove its saved pairing. Existing provider credentials may remain valid until expiry; sign out of TakeProfit to end the browser session.

Windows DPAPI is used for persistent local pairing. On other systems or if secure storage is unavailable, pairing is per-process. The Python launcher can also be invoked with `python3 launch.py` on Linux/macOS with Python 3.11+ and venv support. Automatic extension pairing is per process outside Windows; manual browser/clipboard behavior and live operation on those platforms are not release-tested.

## Automatic connection and updates

A pairing code is a persistent local shared secret, not a TakeProfit access token. Reusing the same code is intentional. Each startup requests fresh authorization through the paired Chrome extension; it does not reuse an old provider token.

After the first successful pairing, stop tpscraper and restart it normally. The console should say **Saved local pairing loaded. No new code is required.** Keep Chrome open and signed in. The extension polls on its alarm, or immediately when you open its popup or click **Check connection now** (extension v1.2.0 or later). The popup shows whether a saved pairing exists. The console should then report **Chrome authorization accepted**.

Chrome's unpacked extension is associated with its installed directory/profile. To keep pairing across application updates, install the extension once into a stable folder of your choice, outside version-specific release folders. On updates, close the running application, replace the four extension files in that same folder with the new release's files, and click Reload at chrome://extensions/. Keep only one tpscraper renewal extension enabled. Do not remove and reinstall an already paired extension unnecessarily.

If the console reports a saved pairing but waits indefinitely, check that Chrome is signed in, that the popup reports a saved pairing, and that the enabled extension is v1.2.0 or newer. Open the popup and use Check connection now. If the extension has no saved pairing or reports a mismatch, stop tpscraper and run:

```powershell
.\run.cmd --reset-pairing
```

Pair with the newly displayed code once, then restart normally without the reset flag. On a source checkout, the equivalent is `py -m tpscraper dashboard --watchlist btc --authorized --auto-renew --orderflow --reset-pairing`. The older `--browser-renew` option is an alias for `--auto-renew`.

If authorization is refused, resolve the account sign-in or entitlement issue before reconnecting. Never post pairing codes or access tokens in support logs. Saved pairing on disk alone does not demonstrate a working connection or renewal.

## Manual authorization

Omit `--auto-renew`. When requested, approve opening Chrome and copy only the successful first-party authorization response or the access token. Choose the local clipboard or hidden input option. Never send credentials to an issue tracker or paste them into a shell command. `--remember` optionally stores the access token in current-user DPAPI storage on Windows. The token still expires. The extension mode always authenticates through the paired browser on startup.

```powershell
py -m tpscraper.credential_store status
py -m tpscraper.credential_store clear
```

These commands manage the saved access token, not the browser login or pairing.

## Configuration

| Option | Purpose |
|---|---|
| dashboard / serve | Open dashboard / run API without opening a tab |
| --authorized | Confirm account and provider permission |
| --auto-renew | Chrome extension sign-in and renewal |
| --reset-pairing | Replace the saved pairing |
| --remember | Optional encrypted access-token cache |
| --watchlist NAME | Select initial preset |
| --workspace | Load locally saved ticker list or fall back to preset |
| --ticker PROVIDER:TICKER | Repeat up to 12 times; overrides preset |
| --orderflow | Request available advanced market-data features |
| --flow-budget N | Limit simultaneous advanced subscriptions; default up to 12 |
| --history N | One-minute candles to retain; default 360, native max 1000 |
| --native-30s | Extra 30-second subscription; max history setting 500 |
| --record-flow PATH | Optional local SQLite feature journal; requires orderflow |
| --refresh-capabilities | Retry cached unavailable features once at startup |
| --port N | Local HTTP port; default 8789 |
| --no-browser | Do not open dashboard automatically |

Run `py -m tpscraper dashboard --help` for the complete command-line reference. The fixed extension bridge listens on 127.0.0.1:8790, so run only one extension-authorized process per computer. The dashboard port may be changed separately. Use the API address 127.0.0.1, not a hostname.

The workspace editor saves configuration locally and does not change active subscriptions until restart. The advanced stream budget can leave some features queued. An entitlement refusal or schema failure is not a reason to try another account or increase request rates.

## Updates and clean downloads

For existing Git clones, run `git pull` from the checkout, then launch normally. For ZIP installations, download and extract a fresh copy; you may keep the old source directory until the new one works. Reload the unpacked extension after changing its source. Never copy an existing virtual environment from another PC.

A ZIP contains the current files only, not old Git history. If you prefer Git updates but do not need old commits, `git clone --depth 1 https://github.com/DeeDop/tpscraper.git` is a shallow checkout of the current version. Full-history audits require a non-shallow clone. Existing clones do not need a reset or force-pull.

## Troubleshooting

- **Python not found:** install Python 3.11 or newer with the Windows launcher or PATH enabled, then rerun `run.cmd`.
- **Setup failed:** check the package-installation network connection and local application-data permissions; retry `run.cmd --check`.
- **Pairing expired:** reload the extension, stop Python, run with reset-pairing, and enter the new local code.
- **Authorization denied:** check your actual TakeProfit account and permitted access. The service will not bypass a refusal.
- **Port in use:** stop the other instance. For dashboard-only port conflicts use another port with `--port`.
- **No timestamped price:** a provider may supply receipt-only quotes, closed-market values, or no eligible trade stream. Inspect health and diagnostics; do not assume the price is live.
- **Unsupported ticker:** confirm its exact provider and symbol. Offline catalog membership does not imply entitlement.
