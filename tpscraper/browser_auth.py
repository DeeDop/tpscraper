"""Opt-in authorization in an isolated, visible browser.

The user signs in directly at TakeProfit. We request the first-party access-token
response with that browser session only after explicit permission. No existing
browser profiles, cookie databases, passwords, or other sites are inspected.
"""
import time
from .auth import AuthError, checked, expires_at

LOGIN_URL = "https://takeprofit.com/platform"
TOKEN_URL = "https://takeprofit.com/api/auth/token"


class BrowserAuth:
    def __init__(self, ask=input, emit=print, context=None):
        self.ask = ask
        self.emit = emit
        self._context = context
        self._external_context = context is not None
        self._playwright = None
        self._browser = None
        self._access = None
        self.renewals = 0

    def _open(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise AuthError("Install the optional browser dependencies first.") from None
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(channel="chrome", headless=False)
            self._context = self._browser.new_context()
            page = self._context.new_page()
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            self.close()
            raise AuthError("Could not open the isolated Chrome window; use manual token entry.") from None

    def refresh(self):
        action = "Open a separate TakeProfit login window and obtain an access token" if self._context is None else "Request a fresh access token from your authorized TakeProfit browser session"
        if self.ask(action + "? [y/N]: ").strip().lower() not in ("y", "yes"):
            raise AuthError("Browser authorization declined")
        if self._context is None:
            self._open()
            self.emit("Sign in yourself in the separate Chrome window. No password is collected by tpscraper.")
            self.ask("Once the TakeProfit platform is fully loaded, press Enter here: ")
        try:
            response = self._context.request.get(TOKEN_URL, headers={"Accept":"application/json","Cache-Control":"no-cache"}, max_redirects=0, timeout=15000)
            if response.status != 200 or response.url != TOKEN_URL:
                raise AuthError("TakeProfit did not authorize the token request; sign in normally or use manual mode.")
            data = response.json()
            if data.get("success") is not True:
                raise AuthError("TakeProfit did not issue an access token")
            access = checked(data["data"]["accessToken"])
            expiry = expires_at(access)
            if expiry is None or expiry <= time.time()+45:
                raise AuthError("The returned token is invalid or nearly expired")
            self._access = access
            self.renewals += 1
        except AuthError:
            raise
        except Exception:
            raise AuthError("Browser authorization failed; use manual token entry if needed.") from None
        finally:
            if "response" in locals():
                try:
                    response.dispose()
                except Exception:
                    pass
        self.emit("Access token received locally. No credential was printed or exported.")
        return self._access

    def headers(self):
        expiry = expires_at(self._access) if self._access else None
        if not self._access or expiry is None or expiry <= time.time()+45:
            self.refresh()
        return {"accesstoken":self._access}

    def close(self):
        self._access = None
        for obj, method in ((self._context if not self._external_context else None,"close"),(self._browser,"close"),(self._playwright,"stop")):
            if obj is not None:
                try:
                    getattr(obj,method)()
                except Exception:
                    pass
        self._context = self._browser = self._playwright = None
