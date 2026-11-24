"""User-mediated authorization in normal, installed Windows Chrome.

No remote-debugging flags, profile access, or cookie extraction. The user
explicitly copies the first-party response and authorizes a local clipboard read.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from getpass import getpass

from .auth import AuthError, checked, expires_at

TOKEN_URL = "https://takeprofit.com/api/auth/token"
JWT = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


def chrome_path():
    candidates = [shutil.which("chrome.exe")]
    for root in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        if os.environ.get(root):
            candidates.append(str(Path(os.environ[root]) / "Google/Chrome/Application/chrome.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise AuthError("Installed Chrome not found. Open the TakeProfit token page manually or use manual token mode.")


def open_chrome():
    try:
        subprocess.Popen([chrome_path(), TOKEN_URL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        raise AuthError("Could not open installed Chrome.") from None


def read_clipboard():
    # No clipboard access unless the user explicitly selects the copy option.
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard -Raw"],
            capture_output=True, text=True, encoding="utf-8", timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise AuthError("Clipboard unavailable. Use hidden manual entry.")
        return result.stdout
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        raise AuthError("Clipboard unavailable. Use hidden manual entry.") from None


def parse_access(raw):
    if not isinstance(raw, str) or len(raw) > 65536:
        raise AuthError("Invalid authorization input")
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            response = json.loads(raw)
            if response.get("success") is not True:
                raise ValueError()
            raw = response["data"]["accessToken"]
        except (ValueError, KeyError, TypeError, AttributeError):
            raise AuthError("Copy only the accessToken or successful token response.") from None
    if not isinstance(raw, str) or not JWT.fullmatch(raw):
        raise AuthError("Expected an access token, not cookies or request headers.")
    raw = checked(raw)
    expiry = expires_at(raw)
    if expiry is None or expiry <= time.time()+45:
        raise AuthError("Token has expired or is nearly expired. Reload the token page.")
    return raw


class LocalChromeAuth:
    def __init__(self, ask=input, emit=print, opener=open_chrome, clipboard=read_clipboard, hidden=getpass):
        self.ask = ask
        self.emit = emit
        self.opener = opener
        self.clipboard = clipboard
        self.hidden = hidden
        self._access = None
        self.renewals = 0

    def refresh(self):
        self._access = None
        if self.ask("Open your regular installed Chrome for TakeProfit authorization? [y/N]: ").strip().lower() not in ("y", "yes"):
            raise AuthError("Authorization declined")
        self.opener()
        self.emit("Use your already signed-in Chrome profile. If needed, sign in normally and reload the token page.")
        self.emit("Copy only the successful JSON response or accessToken. Do not send it to chat or GitHub.")
        method = self.ask("Read your copied response from the local clipboard [c], hidden manual paste [p], or cancel [Enter]: ").strip().lower()
        if method == "c":
            raw = self.clipboard()
        elif method == "p":
            raw = self.hidden("Paste accessToken (hidden): ")
        else:
            raise AuthError("Authorization cancelled")
        self._access = parse_access(raw)
        self.renewals += 1
        self.emit("Authorization loaded into memory. Consider clearing the copied credential from your clipboard.")
        return self._access

    def headers(self):
        expiry = expires_at(self._access) if self._access else None
        if not self._access or expiry is None or expiry <= time.time()+45:
            self.refresh()
        return {"accesstoken": self._access}

    def close(self):
        self._access = None
