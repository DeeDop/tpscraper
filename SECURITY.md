# Security

tpscraper is a local integration, not a hosted service. The market-data HTTP server listens only on 127.0.0.1 and does not authenticate local consumers. The extension bridge uses a separate loopback port, a random pairing secret and a request identifier for each token response. Never expose either port to another computer, public tunnel or reverse proxy. Trust other software running under your OS account.

## Authorization

Use only an account you control and subscriptions you are permitted to access. Chrome manages the normal login. The extension makes requests only to the first-party authorization endpoint when a paired local process requests renewal and hands the resulting token to that local process. It does not request cookie, debugger or broad web access permissions. It never persists the provider token in extension storage. Do not share access tokens or pairing secrets.

Windows stores the pairing secret with current-user DPAPI under LocalAppData. Chrome retains its matching pairing secret in extension-local storage; Chrome storage is not an independent encrypted credential vault. The optional remember setting stores an access token with current-user DPAPI. Other local application files can contain market data but should not contain account credentials.

Disable renewal in the extension to remove its stored pairing. Stop the service and reset pairing to invalidate the prior local secret. Sign out or revoke provider access as appropriate; disabling renewal does not retroactively invalidate already-issued tokens.

## Scope and disclosure

Report suspected vulnerabilities privately to the repository maintainer rather than publishing credentials, network captures or account information in an issue. Include the version, affected component and sanitized reproduction steps. No security audit or production certification is claimed.
