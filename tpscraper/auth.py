"""Explicit local authorization. Secrets remain in memory; no browser extraction."""
import base64
import json
import time
from getpass import getpass
import httpx

AUTH_URL = "https://takeprofit.com/api/auth/token"

class AuthError(Exception):
    pass

def expires_at(token):
    try:
        part = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        return float(claims["exp"])
    except (ValueError, KeyError, IndexError, TypeError):
        return None

def checked(value):
    if not value or len(value) > 32768 or any(c.isspace() for c in value) or ";" in value:
        raise AuthError("Invalid credential input")
    return value

class Auth:
    def __init__(self, access=None, session=None, client=None):
        self._access = checked(access) if access else None
        self._session = checked(session) if session else None
        self._owns_client = client is None
        self._client = client or httpx.Client(http2=True, timeout=10, follow_redirects=False, trust_env=False)
        self.renewals = 0

    @classmethod
    def prompt(cls, session=False):
        if session:
            return cls(session=getpass("Your newly authorized TakeProfit session token (hidden): ").strip())
        return cls(access=getpass("Your newly authorized TakeProfit accessToken (hidden): ").strip())

    def refresh(self):
        if not self._session:
            raise AuthError("Fresh user authorization required")
        # Send only the explicitly supplied credential to its original first-party endpoint.
        try:
            r = self._client.get(AUTH_URL, headers={"Cookie":"token="+self._session,"Accept":"application/json"})
            if r.status_code != 200:
                raise AuthError("Renewal denied (HTTP %d)" % r.status_code)
            data = r.json()
            if data.get("success") is not True:
                raise AuthError("Renewal not accepted")
            access = checked(data["data"]["accessToken"])
            rotated = r.cookies.get("token")
            if rotated:
                self._session = checked(rotated)
            self._access = access
            self.renewals += 1
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise AuthError("Renewal response unavailable or invalid") from None
        finally:
            self._client.cookies.clear()
        return self._access

    def headers(self):
        exp = expires_at(self._access) if self._access else None
        if not self._access or (exp is not None and exp <= time.time()+45):
            self.refresh()
        return {"accesstoken": self._access}

    def close(self):
        self._access = self._session = None
        if self._owns_client:
            self._client.close()
