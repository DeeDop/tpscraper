"""Build a clean Windows x64 distribution; never archive the development checkout."""
import argparse
import hashlib
import importlib.metadata as metadata
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
DOCS = ("API.md", "INSTRUMENTS.md", "SETUP.md")
EXTENSION = ("manifest.json", "popup.html", "popup.js", "worker.js")
PACKAGES = (
    "httpx", "httpcore", "h11", "h2", "hpack", "hyperframe", "certifi",
    "idna", "anyio", "sniffio", "typing-extensions", "exceptiongroup",
    "pyinstaller", "altgraph", "packaging", "pefile", "pywin32-ctypes",
)
RUN_CMD = """@echo off
setlocal
pushd "%~dp0"
"%~dp0tpscraper.exe" %*
set "result=%errorlevel%"
popd
if not "%result%"=="0" (
    echo tpscraper exited with code %result%.
    pause
)
exit /b %result%
"""
README = """# tpscraper — Windows portable edition

Extract the entire ZIP into a folder of your choice. Keep the application,
_internal directory and chrome-renew directory together. No Python, pip,
Git or administrator privileges are required. Windows 10/11 x64 and a
current Chrome browser are required.

1. Sign in to TakeProfit in your normal Chrome profile.
2. At chrome://extensions/ enable Developer mode and load the included
   chrome-renew directory as an unpacked extension.
3. Double-click run.cmd and confirm permission to access the data.
4. On first use, copy the local pairing code from the console into the
   extension popup and choose Authorize and pair.
5. Keep Chrome open. The dashboard is at http://127.0.0.1:8789/.

Pairing and watchlists are stored locally under the Windows user account,
not in this package. Pair once on each computer. To reset pairing, run
run.cmd --reset-pairing. To verify the installation without connecting to
TakeProfit, run run.cmd --check. To run the API without opening the dashboard,
run run.cmd serve --workspace --watchlist btc --authorized --auto-renew --orderflow.

For updates, keep the installed Chrome extension in the same directory.
Replace its files from the new ZIP, then click Reload at chrome://extensions/.
Disable duplicate old extensions. If the console reports saved pairing,
open the extension popup and click Check connection now (v1.2.0 or newer).
Reset pairing only if missing or mismatched. See docs/SETUP.md for recovery.
Do not copy credentials between computers.

See docs/API.md for integration and docs/INSTRUMENTS.md for ticker discovery.
The service is loopback-only. Use only with your own authorized account,
within provider terms and subscription limits. It is an unofficial,
read-only integration, not a source of guaranteed real-time or settlement
prices and not permission to redistribute market data.

This is a pre-release build for private testing. The executable is not
code-signed. Verify its ZIP checksum against the accompanying SHA256 file
and your organization's security requirements before running it.
"""


def run(args, **kwargs):
    subprocess.run([str(x) for x in args], check=True, **kwargs)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def notices(stage):
    target = stage / "third-party-notices"
    target.mkdir()
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("Python runtime license not found")
    shutil.copy2(python_license, target / "Python-LICENSE.txt")
    for name in PACKAGES:
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        folder = target / name
        folder.mkdir()
        info = [name + " " + dist.version]
        for key in ("License-Expression", "License", "Home-page"):
            if dist.metadata.get(key):
                info.append(key + ": " + dist.metadata[key])
        (folder / "METADATA.txt").write_text("\n".join(info) + "\n", encoding="utf-8")
        for i, item in enumerate(dist.files or ()):
            if any(part.lower().startswith(("license", "copying", "notice")) for part in item.parts):
                source = Path(dist.locate_file(item))
                if source.is_file():
                    shutil.copy2(source, folder / (str(i) + "-" + source.name))


def build(output):
    if os.name != "nt" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise SystemExit("The Windows x64 package must be built on Windows x64.")
    if sys.maxsize <= 2**32:
        raise SystemExit("64-bit Python is required.")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tpscraper-release-") as work:
        work = Path(work)
        run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
             "--onedir", "--console", "--noupx", "--name", "tpscraper",
             "--paths", ROOT, "--distpath", work / "dist",
             "--workpath", work / "build", "--specpath", work,
             "--add-data", str(ROOT / "tpscraper/static/dashboard.html") + ":tpscraper/static",
             "--add-data", str(ROOT / "docs/takeprofit_tickers.csv") + ":docs",
             ROOT / "scripts/release_entry.py"], cwd=ROOT)
        stage = work / "dist" / "tpscraper"
        (stage / "chrome-renew").mkdir()
        for name in EXTENSION:
            shutil.copy2(ROOT / "chrome-renew" / name, stage / "chrome-renew" / name)
        (stage / "docs").mkdir()
        for name in DOCS:
            shutil.copy2(ROOT / "docs" / name, stage / "docs" / name)
        shutil.copy2(ROOT / "SECURITY.md", stage / "SECURITY.md")
        (stage / "README.md").write_text(README, encoding="utf-8")
        (stage / "run.cmd").write_text(RUN_CMD, encoding="ascii")
        notices(stage)
        # Exercise the frozen executable from a different working directory.
        run([stage / "tpscraper.exe", "--check"], cwd=work)
        run([stage / "tpscraper.exe", "serve", "--help"], cwd=work)
        # The archive is produced solely from the fresh build directory,
        # never from the checkout or local AppData.
        expected = {"tpscraper.exe", "_internal", "chrome-renew", "docs",
                    "third-party-notices", "README.md", "SECURITY.md", "run.cmd"}
        if {p.name for p in stage.iterdir()} != expected:
            raise RuntimeError("Unexpected top-level distribution files")
        archive = output / "tpscraper-windows-x64.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for path in sorted(stage.rglob("*")):
                if path.is_symlink():
                    raise RuntimeError("Unexpected symlink in release")
                if path.is_file():
                    rel = path.relative_to(stage)
                    if any(part.lower() in (".git", ".venv", "__pycache__", "secrets", "tests")
                           for part in rel.parts) or path.suffix.lower() in (
                               ".har", ".dpapi", ".log", ".jsonl", ".sqlite", ".sqlite3",
                               ".key", ".pem", ".pfx", ".p12"):
                        # certifi's public trust store is a required TLS dependency.
                        if rel.as_posix() != "_internal/certifi/cacert.pem":
                            raise RuntimeError("Forbidden file in distribution: " + rel.name)
                    z.write(path, Path("tpscraper") / rel)
        checksum = sha256(archive)
        (output / "SHA256SUMS.txt").write_text(
            checksum + "  " + archive.name + "\n", encoding="ascii")
        # Verify ZIP integrity and run the exact extracted artifact.
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None:
                raise RuntimeError("Corrupt release ZIP")
            z.extractall(work / "extracted")
        run([work / "extracted/tpscraper/tpscraper.exe", "--check"], cwd=work)
        print("Release ZIP created:", archive.name, archive.stat().st_size, "bytes")
        print("SHA256:", checksum)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    build(parser.parse_args().output.resolve())
