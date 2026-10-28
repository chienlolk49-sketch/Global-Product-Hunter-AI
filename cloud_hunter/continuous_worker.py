#!/usr/bin/env python3
"""Always-on Cloud Hunter worker for an independent Linux VM.

This is NOT a GitHub-hosted Actions job. The VM must stay online.
The worker invokes the existing bounded V9 scraper, synchronizes its
public ad observations with GitHub, and repeats with a cooling interval.

Requires GH_TOKEN with Contents read/write access to the selected repo.
Never commit a token to GitHub. Do not run concurrently with the GitHub
Actions schedule on the same data branch unless ready to handle conflicts.
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "cloud_hunter" / "data"
REPO = os.getenv("CLOUD_HUNTER_REPO", "chienlolk49-sketch/Global-Product-Hunter-AI")
BRANCH = os.getenv("CLOUD_HUNTER_BRANCH", "main")
TOKEN = os.getenv("GH_TOKEN", "").strip()
COOLDOWN = max(180, int(os.getenv("CLOUD_HUNTER_COOLDOWN_SECONDS", "300")))
SCAN_TIMEOUT = max(300, int(os.getenv("CLOUD_HUNTER_SCAN_TIMEOUT_SECONDS", "780")))
STOP = False
FILES = ("ads.json", "top50.json", "status.json")


def log(message):
    print(f"[{datetime.now(timezone.utc).isoformat()}] {message}", flush=True)


def stop(_signal, _frame):
    global STOP
    STOP = True
    log("Shutdown requested; will finish current cycle.")


def api_request(method, path, payload=None):
    if not TOKEN:
        raise RuntimeError("GH_TOKEN is missing. The worker cannot publish to the cloud dataset.")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = Request(
        "https://api.github.com/repos/" + REPO + "/contents/" + path,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + TOKEN,
            "User-Agent": "Global-Product-Hunter-Always-On",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        description = exc.read(350).decode("utf-8", errors="replace")
        if exc.code == 404 and method == "GET":
            return None
        raise RuntimeError(f"GitHub API returned HTTP {exc.code}: {description}") from exc


def github_file_path(filename):
    return "cloud_hunter/data/" + filename


def read_remote(filename):
    path = github_file_path(filename) + "?ref=" + quote(BRANCH, safe="")
    resource = api_request("GET", path)
    if resource is None:
        return {}, None
    if resource.get("type") != "file":
        raise RuntimeError("Unexpected response type from GitHub for " + filename)
    raw = base64.b64decode(resource["content"].replace("\n", ""))
    return json.loads(raw.decode("utf-8")), resource.get("sha")


def time_key(ad):
    return str(ad.get("active_checked_at") or ad.get("last_seen") or "")


def merge_ads(*collections):
    """Preserve unique Meta IDs and prefer the most recently checked record."""
    by_id = {}
    for entries in collections:
        for row in entries:
            if not isinstance(row, dict):
                continue
            ad_id = str(row.get("ad_id") or "")
            if not ad_id:
                continue
            old = by_id.get(ad_id)
            if old is None:
                by_id[ad_id] = dict(row)
                continue
            chosen = row if time_key(row) >= time_key(old) else old
            merged = dict(chosen)
            countries = {
                c
                for r in (old, row)
                for c in ((r.get("source_countries") or [r.get("source_country")]))
                if isinstance(c, str) and c
            }
            merged["source_countries"] = sorted(countries)
            first = [
                r.get("first_seen")
                for r in (old, row)
                if isinstance(r.get("first_seen"), str) and r["first_seen"]
            ]
            if first:
                merged["first_seen"] = min(first)
            by_id[ad_id] = merged
    return sorted(by_id.values(), key=time_key, reverse=True)


def write_json(filename, value):
    STORE.mkdir(parents=True, exist_ok=True)
    path = STORE / filename
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def local_json(filename, default=None):
    try:
        return json.loads((STORE / filename).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default if default is not None else {}


def sync_from_remote():
    cloud, _ = read_remote("ads.json")
    local = local_json("ads.json", {"ads": []})
    combined = merge_ads(cloud.get("ads", []), local.get("ads", []))
    write_json("ads.json", {"updated_at": datetime.now(timezone.utc).isoformat(), "ads": combined})
    log(f"Loaded {len(combined)} distinct ad IDs from cloud + local cache.")


def publish(filename):
    content = local_json(filename)
    if not content:
        raise RuntimeError(filename + " is missing or empty; refusing to overwrite cloud data.")
    # Optimistic concurrency via the latest GitHub blob sha.
    for attempt in range(3):
        remote, sha = read_remote(filename)
        if filename == "ads.json":
            # When another writer pushed meanwhile, keep every distinct ID.
            content["ads"] = merge_ads(remote.get("ads", []), content.get("ads", []))
            write_json(filename, content)
        obj = {
            "message": "data: always-on Cloud Hunter updates " + filename,
            "branch": BRANCH,
            "content": base64.b64encode(json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")).decode("ascii"),
        }
        if sha:
            obj["sha"] = sha
        try:
            api_request("PUT", github_file_path(filename), obj)
            log("Published " + filename)
            return
        except RuntimeError as exc:
            if any(s in str(exc) for s in ("HTTP 409", "HTTP 422")) and attempt < 2:
                log(filename + ": branch changed concurrently; retrying.")
                time.sleep(2)
            else:
                raise


def cycle(no_publish=False):
    log("Starting bounded active-ad scan.")
    if not no_publish:
        sync_from_remote()
    env = dict(os.environ)
    # Rotate more often when running on an always-on VM than on GitHub Actions.
    env.setdefault("CLOUD_HUNTER_ROTATION_SECONDS", "600")
    result = subprocess.run(
        [sys.executable, str(ROOT / "cloud_hunter" / "scan.py")],
        cwd=str(ROOT),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=SCAN_TIMEOUT,
        check=False,
    )
    log("Scanner exit code: " + str(result.returncode))
    if result.stdout:
        print(result.stdout[-15000:], flush=True)
    if not no_publish:
        # Even when all scrapes fail, publish diagnostic status if present,
        # but do not claim a successful scrape or invented active ads.
        for filename in FILES:
            if (STORE / filename).exists():
                publish(filename)
    if result.returncode:
        log("Scrape failed or returned no usable results. Review log/status.json.")
    return result.returncode


def inspect():
    print("Cloud Hunter always-on readiness:")
    print("  repository:", REPO)
    print("  branch:", BRANCH)
    print("  GitHub write token:", "present" if TOKEN else "MISSING")
    print("  scraper package:", "found" if importlib.util.find_spec("fb_ads_scraper") else "MISSING")
    print("  scan script:", "found" if (ROOT / "cloud_hunter" / "scan.py").is_file() else "MISSING")
    print("  cooldown after each run (seconds):", COOLDOWN)
    print("  Note: check does not launch a server or validate cloud credentials.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Show installation prerequisites only.")
    parser.add_argument("--once", action="store_true", help="Run one bounded scan.")
    parser.add_argument("--no-publish", action="store_true", help="Local test: do not read/write GitHub.")
    args = parser.parse_args()
    if args.check:
        inspect()
        return 0
    if not args.no_publish and not TOKEN:
        log("Missing GH_TOKEN. Configure it securely on the VM; cloud synchronization is disabled.")
        return 2
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    while True:
        try:
            result = cycle(no_publish=args.no_publish)
        except subprocess.TimeoutExpired:
            log("Scanner exceeded timeout; retrying after cooldown.")
            result = 2
        except (RuntimeError, URLError, OSError, ValueError) as exc:
            log("Cycle failed: " + str(exc))
            result = 2
        if args.once:
            return result
        if STOP:
            break
        log(f"Cooling down {COOLDOWN} seconds before the next scan.")
        for _ in range(COOLDOWN):
            if STOP:
                break
            time.sleep(1)
        if STOP:
            break
    log("Stopped cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
