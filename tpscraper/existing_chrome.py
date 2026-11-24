"""Use Chrome's approval-based debugging connection (Chrome 144+).

No browser launch, profile copying, cookie database reads, or security overrides.
The only profile file read is Chrome's documented DevTools endpoint locator.
The existing browser remains open when the scraper disconnects.
"""
import os
import re
from pathlib import Path
from .auth import AuthError
from .local_chrome import LocalChromeAuth
from .dedicated_chrome import DedicatedChromeAuth

def devtools_endpoint(path=None):
    if path is None:
        root=os.environ.get("LOCALAPPDATA")
        if not root:
            raise AuthError("Normal Chrome authorization requires Windows Chrome.")
        path=Path(root)/"Google"/"Chrome"/"User Data"/"DevToolsActivePort"
    try:
        with Path(path).open(encoding="utf-8") as f:
            lines=f.read(512).splitlines()
        port=int(lines[0].strip())
        route=lines[1].strip()
        if not 1<=port<=65535 or not re.fullmatch(r"/devtools/browser/[A-Za-z0-9-]{1,128}",route):
            raise ValueError()
        return f"ws://127.0.0.1:{port}{route}"
    except (OSError,ValueError,IndexError):
        raise AuthError("In your normal Chrome, open chrome://inspect/#remote-debugging and enable remote debugging for this browser instance.") from None

class ExistingChromeAuth(DedicatedChromeAuth):
    def __init__(self,store=None,**kwargs):
        LocalChromeAuth.__init__(self,store=store,**kwargs)
        self._playwright=None
        self._browser=None
        self._context=None
        self._approved=False
        self.emit("Use your existing signed-in Chrome (144+). No extension or separate profile.")
        self.emit("Chrome debugging permission is browser-wide; tpscraper only requests the TakeProfit token endpoint.")
        if self.ask("Allow this local program to connect to your normal Chrome and renew TakeProfit authorization? [y/N]: ").strip().lower() not in ("y","yes"):
            raise AuthError("Browser authorization declined")
        self._approved=True

    def _open(self):
        if not self._approved:
            raise AuthError("Browser authorization not approved")
        if self._context is not None:
            if not self._browser.is_connected():
                raise AuthError("Chrome connection ended or permission revoked. Restart to approve again.")
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise AuthError("Install browser support: py -m pip install -r requirements-browser.txt") from None
        try:
            endpoint=devtools_endpoint()
        except AuthError:
            self.emit("In your normal signed-in Chrome, open chrome://inspect/#remote-debugging.")
            self.emit("Enable remote debugging for this browser instance; do not launch another Chrome.")
            if self.ask("Press Enter when enabled, or type cancel: ").strip().lower()=="cancel":
                raise AuthError("Browser authorization cancelled")
            endpoint=devtools_endpoint()
        self.emit("Approve Chrome's native connection permission dialog if shown.")
        try:
            self._playwright=sync_playwright().start()
            self._browser=self._playwright.chromium.connect_over_cdp(endpoint,timeout=90000)
            contexts=self._browser.contexts
            if len(contexts)!=1:
                raise AuthError("Multiple or missing browser contexts; use one normal signed-in Chrome context or manual authorization.")
            self._context=contexts[0]
        except AuthError:
            self.close()
            raise
        except Exception:
            self.close()
            raise AuthError("Chrome connection unavailable or denied. Verify Chrome 144+, debugging permission and the signed-in account. No automatic retry.") from None

    def close(self):
        LocalChromeAuth.close(self)
        self._approved=False
        self._context=None
        self._browser=None
        driver,self._playwright=self._playwright,None
        # Do not call context.close() or browser.close() on the user's browser.
        if driver is not None:
            try:
                driver.stop()
            except Exception:
                pass
