"""Install and launch from any checkout location without a global pip install."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent


def runtime_root():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    # A moved or separately downloaded checkout receives a fresh environment.
    identity = "\0".join((str(ROOT), str(Path(sys.executable).resolve()),
                          sys.implementation.name, sys.version))
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return base / "tpscraper" / "venvs" / key


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def prepare():
    env = runtime_root()
    python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    stamp = env / ".requirements-sha256"
    requirements = ROOT / "requirements.txt"
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    if not python.is_file():
        print("Creating a private Python environment...", flush=True)
        venv.EnvBuilder(with_pip=True).create(env)
    if not stamp.is_file() or stamp.read_text(encoding="ascii").strip() != digest:
        print("Installing tpscraper dependencies...", flush=True)
        run([str(python), "-m", "pip", "install", "-r", str(requirements)])
        run([str(python), "-m", "pip", "check"])
        stamp.write_text(digest, encoding="ascii")
    return python


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if sys.version_info < (3, 11):
        print("Install Python 3.11 or newer, then run this launcher again.", file=sys.stderr)
        return 2
    try:
        python = prepare()
        if args == ["--setup-only"]:
            print("Setup complete. Load the chrome-renew folder in Chrome, then launch again.")
            return 0
        if args == ["--check"]:
            run([str(python), "-m", "pip", "check"])
            run([str(python), "-m", "tpscraper", "dashboard", "--help"])
            run([str(python), "-c", "from pathlib import Path; from tpscraper.catalog import load_catalog; import tpscraper; assert (Path(tpscraper.__file__).parent / 'static' / 'dashboard.html').is_file(); assert load_catalog(); print('Local assets and instrument catalog available.')"])
            return 0
        if not args or args == ["--reset-pairing"]:
            reset = bool(args)
            print("Connect through your own signed-in TakeProfit Chrome session.")
            print("Load the chrome-renew folder in Chrome if not already installed.")
            answer = input("Do you have permission for these market-data subscriptions? [y/N]: ")
            if answer.strip().lower() not in ("y", "yes"):
                print("No connection made.")
                return 0
            args = ["dashboard", "--workspace", "--watchlist", "btc",
                    "--authorized", "--auto-renew", "--orderflow"]
            if reset:
                args.append("--reset-pairing")
        return subprocess.call([str(python), "-m", "tpscraper", *args], cwd=ROOT)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print("Unable to prepare or launch tpscraper:", type(exc).__name__, file=sys.stderr)
        print("Check Python, network access for package installation, and local folder permissions.",
              file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
