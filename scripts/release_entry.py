"""Entry point for the Windows portable distribution."""
from pathlib import Path
import sys

import httpx
from tpscraper import __version__
from tpscraper.catalog import load_catalog
from tpscraper.dashboard import main as dashboard_main
import tpscraper


def check():
    # Construct the HTTP/2 client without connecting to any provider.
    with httpx.Client(http2=True, trust_env=False):
        pass
    root = Path(tpscraper.__file__).parent
    if not (root / "static" / "dashboard.html").is_file() or not load_catalog():
        raise RuntimeError("Bundled dashboard or instrument catalog missing.")
    print("tpscraper", __version__, "- bundled dependencies and assets OK.")
    return 0


def main():
    args = sys.argv[1:]
    if args == ["--check"]:
        return check()
    if args == ["--version"]:
        print(__version__)
        return 0
    if not args or args == ["--reset-pairing"]:
        reset = bool(args)
        print("Use your own signed-in TakeProfit Chrome session.")
        try:
            answer = input("Do you have permission for the requested market-data subscriptions? [y/N]: ")
        except (EOFError, KeyboardInterrupt):
            return 130
        if answer.strip().lower() not in ("y", "yes"):
            return 0
        args = ["dashboard", "--workspace", "--watchlist", "btc", "--authorized",
                "--auto-renew", "--orderflow"]
        if reset:
            args.append("--reset-pairing")
    mode, *options = args
    if mode not in ("dashboard", "serve"):
        print("Usage: tpscraper.exe [dashboard|serve] [options] or --check")
        return 2
    if mode == "serve" and "--no-browser" not in options:
        options.append("--no-browser")
    return dashboard_main(options) or 0


if __name__ == "__main__":
    raise SystemExit(main())
