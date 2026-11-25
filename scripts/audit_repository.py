"""Report potentially sensitive tracked files and reachable Git history.

No secret values or source lines are printed. Run only in a trusted checkout.
This is a heuristic audit, not a guarantee that no secrets exist.
"""
import argparse
import collections
import math
import re
import subprocess

PATTERNS = {
    "private-key": rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----",
    "github-token": rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b",
    "cloud-api-key": rb"\b(?:AKIA[A-Z0-9]{16}|ASIA[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{35})\b",
    "service-api-key": rb"\b(?:sk-[A-Za-z0-9_-]{24,}|xox[baprs]-[A-Za-z0-9-]{20,}|rk_live_[A-Za-z0-9]{20,}|sk_live_[A-Za-z0-9]{20,})\b",
    "jwt": rb"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,}\b",
    "discord-webhook": rb"https://(?:discord(?:app)?\.com)/api/webhooks/\d{10,}/[A-Za-z0-9_-]{20,}",
    "discord-token": rb"\b[A-Za-z0-9_-]{22,28}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{25,}\b",
    "url-credential": rb"\b(?:https?|postgres(?:ql)?|mysql|redis|mongodb(?:\+srv)?)://[^/\s:@]+:[^/\s@]+@",
    "literal-authorization": rb"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9_+/=-]{24,}",
    "personal-home-path": rb"(?i)(?:[a-z]:[\\/]+(?:users|documents and settings)[\\/]+[^\\/\s\"']+|/(?:home|users)/[a-z0-9_.-]+/)",
    "fixed-install-path": rb"(?i)\b[a-z]:[\\/]+(?:tools|downloads|desktop|documents)[\\/]+[a-z0-9_.-]+",
    "email-address": rb"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    "git-lfs-pointer": rb"(?m)^version https://git-lfs.github.com/spec/v1$",
}
RULES = {k: re.compile(v) for k, v in PATTERNS.items()}
ASSIGNMENT = re.compile(
    rb"(?i)(?:\b(?:access[_-]?token|refresh[_-]?token|session[_-]?token|api[_-]?key|"
    rb"client[_-]?secret|secret[_-]?key|password|passwd|authorization|cookie|token|"
    rb"pairing[_-]?(?:code|secret))\b)[\"']?\s*[:=]\s*[\"']([^\"'\r\n]{8,4096})[\"']"
)
SENSITIVE_NAME = re.compile(
    r"(?i)(?:^|/)(?:\.env(?:\..*)?|credentials(?:\.[^/]*)?|secrets(?:/|$)|"
    r"id_(?:rsa|ed25519|ecdsa)|cookies(?:\.[^/]*)?|login data|local state)$"
    r"|\.(?:har|dpapi|pem|p12|pfx|key|sqlite(?:3)?(?:-wal|-shm)?|db|log|jsonl|zip|7z|tar|gz)$"
    r"|(?:net-export|candle-bodies|probe_result|_report\.json)"
)
SECRET_RULES = set(PATTERNS) - {
    "personal-home-path", "fixed-install-path", "email-address", "git-lfs-pointer"
}


def git(*args):
    return subprocess.check_output(["git", *args], stderr=subprocess.PIPE)


def text_path(raw):
    return raw.decode("utf-8", "backslashreplace").replace("\r", "?").replace("\n", "?")


def entropy(value):
    counts = collections.Counter(value)
    return -sum((n / len(value)) * math.log2(n / len(value)) for n in counts.values())


def placeholder(value):
    lower = value.lower()
    return (
        lower.startswith((b"synthetic", b"example", b"dummy", b"placeholder", b"test-", b"rotated-synthetic"))
        or lower in {b"your_token_here", b"your_api_key", b"not-a-real-token"}
        or value.startswith((b"$" + b"{", b"<", b"{"))
        or re.fullmatch(rb"[xX*_.-]+", value) is not None
    )


def findings(data):
    result = []
    for name, rule in RULES.items():
        for match in rule.finditer(data):
            value = match.group()
            if name == "email-address" and value.lower().endswith(
                (b"@users.noreply.github.com", b"@github.com", b"@example.com", b"@example.org")
            ):
                continue
            if name == "personal-home-path" and value.lower().endswith(
                (b"\\username", b"/username/", b"\\user", b"/user/")
            ):
                continue
            result.append((name, data.count(b"\n", 0, match.start()) + 1))
    for match in ASSIGNMENT.finditer(data):
        value = match.group(1)
        if placeholder(value):
            continue
        if len(value) >= 16 and entropy(value) >= 3.4:
            result.append(("credential-like-literal", data.count(b"\n", 0, match.start()) + 1))
    return sorted(set(result))


def safe_label(path):
    raw = path.encode("utf-8", "replace")
    if any(kind in SECRET_RULES or kind in {"email-address", "credential-like-literal", "personal-home-path"}
           for kind, _ in findings(raw)):
        return "<redacted path>"
    return path


def scan(history=False):
    if history and git("rev-parse", "--is-shallow-repository").strip() == b"true":
        raise RuntimeError("Full-history audit requires a non-shallow checkout.")
    head = {}
    for entry in git("ls-tree", "-r", "-z", "HEAD").split(b"\0"):
        if not entry:
            continue
        meta, raw = entry.split(b"\t", 1)
        _, kind, oid = meta.split()
        if kind == b"blob":
            head[oid.decode()] = text_path(raw)
        elif kind == b"commit":
            print("UNINSPECTED submodule:", safe_label(text_path(raw)))
    current = set(head)
    refs = ["--all", "HEAD"] if history else ["HEAD"]
    commits = git("rev-list", *refs).splitlines() if history else [git("rev-parse", "HEAD").strip()]
    objects = dict(head)
    paths = set(head.values())
    historical_paths = set()
    if history:
        for commit in commits:
            for entry in git("ls-tree", "-r", "-z", commit.decode()).split(b"\0"):
                if not entry:
                    continue
                meta, raw = entry.split(b"\t", 1)
                _, kind, oid = meta.split()
                path = text_path(raw)
                if kind == b"blob":
                    objects.setdefault(oid.decode(), path)
                    historical_paths.add(path)
                elif kind == b"commit":
                    print("UNINSPECTED historical submodule:", safe_label(path))
    counts = collections.Counter()
    binary_count = 0
    for path in sorted(paths | historical_paths):
        if SENSITIVE_NAME.search(path):
            scope = "CURRENT" if path in paths else "HISTORY"
            counts[(scope, "sensitive-filename")] += 1
            print(scope, "sensitive-filename", safe_label(path))
    for oid, path in objects.items():
        data = git("cat-file", "blob", oid)
        scope = "CURRENT" if oid in current else "HISTORY"
        if b"\0" in data:
            binary_count += 1
            counts[(scope, "binary-not-decoded")] += 1
            print(scope, "binary-not-decoded", oid[:12], safe_label(path))
        for kind, line in findings(data):
            counts[(scope, kind)] += 1
            print(scope, kind, oid[:12], safe_label(path), "line", line)
    for commit in commits:
        oid = commit.decode()
        data = git("cat-file", "commit", oid)
        for kind, line in findings(data):
            counts[("COMMIT", kind)] += 1
            print("COMMIT", kind, oid[:12], "line", line)
    print("AUDIT SUMMARY")
    print("commits:", len(commits))
    print("current distinct blobs:", len(current))
    print("unique blobs scanned:", len(objects))
    print("unique historical paths:", len(paths | historical_paths))
    print("binary blobs not decoded:", binary_count)
    for (scope, kind), count in sorted(counts.items()):
        print(scope, kind, count)
    if not counts:
        print("No heuristic findings.")
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="Scan every commit reachable from local refs")
    parser.add_argument("--fail-current", action="store_true", help="Fail on current credential-like findings")
    args = parser.parse_args()
    counts = scan(args.history)
    if args.fail_current and any(
        scope == "CURRENT" and kind in SECRET_RULES | {"credential-like-literal", "sensitive-filename"}
        for scope, kind in counts
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
