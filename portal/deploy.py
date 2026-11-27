"""Vercel deploy via REST API — no CLI dependency.

The Vercel CLI cannot deploy to personal accounts non-interactively
("No teams available" scope bug); the REST API can. This script uploads
portal/dist by content digest and creates a production deployment.
Used by .github/workflows/deploy-portal.yml on every push to main.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

TOKEN = os.environ.get("VERCEL_TOKEN")
PROJECT = os.environ.get("VERCEL_PROJECT_ID", "prj_Jm3TiCsk7IECdcaF7NrdUQsVGnEp")
DIST = Path(__file__).resolve().parent / "dist"


def api(method: str, path: str, data: bytes | None, headers: dict) -> dict:
    req = urllib.request.Request(
        f"https://api.vercel.com{path}",
        data=data,
        headers={"Authorization": f"Bearer {TOKEN}", **headers},
        method=method,
    )
    resp = urllib.request.urlopen(req, timeout=60)
    raw = resp.read()
    return json.loads(raw) if raw else {}


def main() -> None:
    if not TOKEN:
        sys.exit("VERCEL_TOKEN missing")
    files = sorted(DIST.rglob("*.html"))
    if not files:
        sys.exit("portal/dist empty — run build first")

    meta = []
    contents = {}
    for f in files:
        content = f.read_bytes()
        sha = hashlib.sha1(content).hexdigest()
        meta.append({"file": f.name, "sha": sha, "size": len(content)})
        contents[sha] = content

    for sha, content in contents.items():
        try:
            api("POST", "/v2/files", content, {"Content-Type": "application/octet-stream", "x-vercel-digest": sha})
        except urllib.error.HTTPError as e:
            if e.code != 409:  # already uploaded
                raise
    print(f"uploaded {len(contents)} digests", flush=True)

    resp = api(
        "POST",
        "/v13/deployments",
        json.dumps({
            "name": "hedgefund-evidence",
            "project": PROJECT,
            "target": "production",
            "files": meta,
        }).encode(),
        {"Content-Type": "application/json"},
    )
    print(f"deployment {resp.get('id')} → https://{resp.get('url')}", flush=True)


if __name__ == "__main__":
    main()
