"""Windows user-scoped DPAPI storage outside the source tree.

Only explicitly supplied access tokens are stored. No browser cookies or passwords.
"""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import tempfile


class StoreError(Exception):
    pass


class Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data, decrypt=False):
    if os.name != "nt":
        raise StoreError("Encrypted credential storage is available on Windows only.")
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p,
                   ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    try:
        # CRYPTPROTECT_UI_FORBIDDEN; no LOCAL_MACHINE flag, so current user scope.
        if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
            raise StoreError("Windows could not decrypt or encrypt the credential.")
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.memset(buf, 0, len(data))
        if output.pbData:
            ctypes.memset(output.pbData, 0, output.cbData)
            kernel.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))


def protect(data):
    return _dpapi(data)


def unprotect(data):
    return _dpapi(data, decrypt=True)


def default_path():
    root = os.environ.get("LOCALAPPDATA")
    if os.name != "nt" or not root:
        raise StoreError("Windows LocalAppData is unavailable.")
    return Path(root) / "tpscraper" / "auth" / "access.dpapi"


class CredentialStore:
    def __init__(self, path=None, encrypt=protect, decrypt=unprotect):
        self.path = Path(path) if path is not None else default_path()
        self.encrypt = encrypt
        self.decrypt = decrypt

    def load(self):
        try:
            data = self.path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError:
            raise StoreError("Cannot read local encrypted credential.") from None
        if not 0 < len(data) <= 262144:
            raise StoreError("Invalid encrypted credential file.")
        try:
            return self.decrypt(data).decode("utf-8")
        except UnicodeError:
            raise StoreError("Invalid encrypted credential.") from None

    def save(self, value):
        encrypted = self.encrypt(value.encode("utf-8"))
        temp = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as f:
                temp = Path(f.name)
                f.write(encrypted)
            os.replace(temp, self.path)
        except OSError:
            raise StoreError("Cannot save local encrypted credential.") from None
        finally:
            if temp is not None:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass

    def clear(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            raise StoreError("Cannot remove local encrypted credential.") from None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Manage tpscraper local encrypted access token")
    parser.add_argument("action", choices=("clear", "status"))
    args = parser.parse_args()
    try:
        store = CredentialStore()
        if args.action == "clear":
            store.clear()
            print("Local encrypted access token removed. Browser session unchanged.")
        else:
            from .auth import expires_at
            import time
            token = store.load()
            expiry = expires_at(token) if token else None
            print("Storage:", store.path)
            if not token:
                print("No saved access token.")
            elif expiry is None:
                print("Saved token expiration unknown.")
            else:
                remaining = int(expiry-time.time())
                print("Remaining token lifetime:", max(0, remaining), "seconds")
                if remaining <= 45:
                    print("Fresh authorization required.")
    except StoreError as exc:
        parser.exit(1, str(exc)+"\n")


if __name__ == "__main__":
    main()
