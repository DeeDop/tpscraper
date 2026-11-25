"""Audit retained GitHub Actions logs without printing log contents.

Requires gh and read access to Actions. Run from a trusted checkout.
No logs are written to the repository or uploaded as artifacts.
"""
import argparse
import collections
import io
import json
import re
import subprocess
import sys
import zipfile
from audit_repository import RULES, ASSIGNMENT, SECRET_RULES, placeholder, entropy

# Hosted-runner paths are not personal computer paths.
RUNNER_NAMES = {b"runner", b"runneradmin", b"vsts", b"circleci"}
HOSTED_EMAILS = (b"@users.noreply.github.com", b"@github.com",
                 b"@example.com", b"@example.org")
EXTRA = {
    "local-git-identity": re.compile(rb"(?i)\b[a-z0-9_.-]+@[a-z0-9_.-]+\.\(none\)"),
    "local-network-hostname": re.compile(rb"(?i)\b(?:desktop|laptop)-[a-z0-9]{5,15}\b"),
    "local-windows-profile": re.compile(rb"(?i)\b[A-Z]:[\\/]+Users[\\/]+([^\\/\s\"']+)"),
    "machine-specific-variable": re.compile(
        rb"(?im)\b(?:COMPUTERNAME|USERNAME|USERPROFILE|LOGONSERVER)\s*[:=]\s*([^\r\n]+)"),
}
# CI metadata and build command lines can contain ordinary source or URLs.
# Do not suppress broad classes of credential matches.
MASK = re.compile(rb"^[*xX. -]+$")


def api(path):
    result = subprocess.run(["gh", "api", path], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    if result.returncode:
        # The caller reports only run ID and attempt, never server text.
        raise RuntimeError("GitHub API request failed")
    return result.stdout


def list_runs(repo):
    seen = set()
    page = 1
    while True:
        data = json.loads(api(f"repos/{repo}/actions/runs?per_page=100&page={page}"))
        rows = data["workflow_runs"]
        for run in rows:
            if run["id"] not in seen:
                seen.add(run["id"])
                yield run
        if len(rows) < 100:
            return
        page += 1


def inspect_line(line):
    found = set()
    for kind, rule in RULES.items():
        if kind == "git-lfs-pointer":
            continue
        for match in rule.finditer(line):
            value = match.group()
            if kind == "personal-home-path":
                user = re.split(rb"[\\/]", value.strip(b"\\/"))[-1].lower()
                if user in RUNNER_NAMES or user in {b"user", b"username"}:
                    continue
            if kind == "email-address" and value.lower().endswith(HOSTED_EMAILS):
                continue
            if kind in SECRET_RULES and (placeholder(value) or MASK.fullmatch(value)):
                continue
            found.add(kind)
    for match in ASSIGNMENT.finditer(line):
        value = match.group(1)
        if not placeholder(value) and len(value) >= 16 and entropy(value) >= 3.4:
            found.add("credential-like-literal")
    for kind, rule in EXTRA.items():
        for match in rule.finditer(line):
            if kind == "local-windows-profile" and match.group(1).lower() in RUNNER_NAMES:
                continue
            if kind == "machine-specific-variable":
                value = match.group(1).strip().lower()
                if value in RUNNER_NAMES or value.startswith((b"runner", b"fv-az", b"fv-")):
                    continue
            found.add(kind)
    return found


def audit(repo):
    runs = attempts = files = lines = 0
    bytes_read = 0
    counts = collections.Counter()
    failures = []
    # A running workflow may not yet have a downloadable log archive.
    # Report its exclusion separately instead of claiming it was scanned.
    active = []
    for run in list_runs(repo):
        if run.get("status") != "completed":
            active.append(run["id"])
            continue
        runs += 1
        for attempt in range(1, int(run.get("run_attempt") or 1) + 1):
            try:
                blob = api(f"repos/{repo}/actions/runs/{run['id']}/attempts/{attempt}/logs")
                with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                    for index, entry in enumerate(archive.infolist()):
                        if entry.is_dir():
                            continue
                        if entry.file_size > 50 * 1024 * 1024:
                            raise RuntimeError("Log exceeds audit size limit")
                        files += 1
                        with archive.open(entry) as handle:
                            for number, line in enumerate(handle, 1):
                                lines += 1
                                bytes_read += len(line)
                                for kind in sorted(inspect_line(line)):
                                    counts[kind] += 1
                                    if counts[kind] <= 25:
                                        print("FINDING", kind, "run", run["id"], "attempt", attempt,
                                              "entry", index, "line", number)
                attempts += 1
            except (OSError, ValueError, RuntimeError, zipfile.BadZipFile):
                failures.append((run["id"], attempt))
                print("UNAVAILABLE run", run["id"], "attempt", attempt)
    print("LOG AUDIT SUMMARY")
    print("runs:", runs)
    print("attempts scanned:", attempts)
    print("log entries:", files)
    print("lines:", lines)
    print("bytes:", bytes_read)
    print("unavailable attempts:", len(failures))
    print("active runs excluded:", len(active))
    for kind, count in sorted(counts.items()):
        print("COUNT", kind, count)
    if not counts:
        print("No heuristic findings.")
    return 1 if counts or failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    sys.exit(audit(args.repo))
