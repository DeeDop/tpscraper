"""Extension-free authorization through an explicitly approved dedicated Chrome profile.

Only the normal first-party token response is requested. No existing-profile
inspection, cookie export, interception, or password collection.
"""
import os
from pathlib import Path
from .auth import AuthError
from .local_chrome import LocalChromeAuth, TOKEN_URL, parse_access
from .credential_store import StoreError

def dedicated_profile():
    root=Path(os.environ.get("LOCALAPPDATA",str(Path.home()/".cache")))
    return root/"tpscraper"/"browser-auth"/"chrome-profile"

class DedicatedChromeAuth(LocalChromeAuth):
    def __init__(self,store=None,login=False,**kwargs):
        super().__init__(store=store,**kwargs)
        self._playwright=None
        self._context=None
        self._login=login
        self._approved=False
        if self.ask("Allow tpscraper to request and renew your TakeProfit access token using a dedicated Chrome session? [y/N]: ").strip().lower() not in ("y","yes"):
            raise AuthError("Browser authorization declined")
        self._approved=True

    def _open(self):
        if self._context is not None:
            return
        if not self._approved:
            raise AuthError("Browser authorization not approved")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise AuthError("Install browser support: py -m pip install -r requirements-browser.txt") from None
        profile=dedicated_profile()
        first=not (profile/"Local State").is_file()
        try:
            profile.mkdir(parents=True,exist_ok=True)
            self._playwright=sync_playwright().start()
            self._context=self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile),channel="chrome",headless=False,
                timeout=20000,accept_downloads=False)
            if first or self._login:
                page=self._context.pages[0] if self._context.pages else self._context.new_page()
                page.goto("https://takeprofit.com/",wait_until="domcontentloaded",timeout=30000)
                self.emit("Sign in normally in the dedicated Chrome window. Keep it open.")
                if self.ask("Press Enter when signed in, or type cancel: ").strip().lower()=="cancel":
                    raise AuthError("Browser authorization cancelled")
        except AuthError:
            self.close()
            raise
        except Exception:
            self.close()
            raise AuthError("Could not open dedicated Chrome. Check installation and close any other tpscraper browser instance.") from None

    def headers(self):
        self._open()
        # Always obtain a token from this specific signed-in session at startup.
        # Do not reuse a cached token from a different browser account.
        self._restore_attempted=True
        return super().headers()

    def refresh(self):
        if not self._approved:
            raise AuthError("Browser authorization not approved")
        self._open()
        response=None
        try:
            # This context shares the dedicated browser's own session.
            # Never inspect cookies, request headers, or unrelated traffic.
            response=self._context.request.get(
                TOKEN_URL,headers={"Accept":"application/json","Cache-Control":"no-cache"},
                max_redirects=0,timeout=15000)
            if response.status!=200 or response.url!=TOKEN_URL:
                raise AuthError("TakeProfit authorization unavailable (HTTP %d). Sign in again only if permitted." % response.status)
            value=parse_access(response.text())
        except AuthError:
            raise
        except Exception:
            raise AuthError("Dedicated Chrome authorization request failed. Check connection and signed-in session.") from None
        finally:
            if response is not None:
                try:
                    response.dispose()
                except Exception:
                    pass
        self._access=value
        self.renewals+=1
        if self.store is not None:
            try:
                self.store.save(value)
            except StoreError:
                self.emit("Encrypted storage unavailable; using memory only.")
        self.emit("Dedicated Chrome authorization accepted.")
        return value

    def prepare_renewal(self):
        """Request new authorization on the collector thread before closing streams."""
        from .auth import expires_at
        old_expiry=expires_at(self._access) if self._access else None
        value=self.refresh()
        if old_expiry is not None and expires_at(value)<=old_expiry:
            raise AuthError("Provider did not extend authorization. Collection stopped; sign in again if permitted.")

    def close(self):
        super().close()
        self._approved=False
        context,self._context=self._context,None
        driver,self._playwright=self._playwright,None
        try:
            if context is not None:
                context.close()
        except Exception:
            pass
        finally:
            if driver is not None:
                try:
                    driver.stop()
                except Exception:
                    pass
