#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

REQUIRED_COLUMNS = [
    "id", "term", "english", "category", "definition", "detailed_explanation",
    "related_concepts", "source_files", "exam_note", "bok_appeared", "importance", "difficulty",
]
VALID_LEVELS = {"상", "중", "하"}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader), list(reader.fieldnames or [])


def preflight(args):
    root = repo_root()
    csv_path = root / args.csv
    errors = []
    if not csv_path.exists():
        errors.append(f"missing CSV: {csv_path}")
    else:
        rows, fields = read_csv(csv_path)
        missing = [c for c in REQUIRED_COLUMNS if c not in fields]
        if missing:
            errors.append(f"missing columns: {missing}")
        ids = [r.get("id", "") for r in rows]
        if not rows:
            errors.append("CSV has no rows")
        if any(not i for i in ids):
            errors.append("CSV contains blank id")
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            errors.append(f"duplicate IDs: {dupes[:20]}")
        bad_importance = sorted({r.get("importance", "") for r in rows if r.get("importance", "") not in VALID_LEVELS})
        bad_difficulty = sorted({r.get("difficulty", "") for r in rows if r.get("difficulty", "") not in VALID_LEVELS})
        if bad_importance:
            errors.append(f"bad importance values: {bad_importance}")
        if bad_difficulty:
            errors.append(f"bad difficulty values: {bad_difficulty}")
        stale = [r.get("id") for r in rows if "동작/활용:" in r.get("detailed_explanation", "")]
        if stale:
            errors.append(f"stale detailed_explanation format in IDs: {stale[:20]}")
        print(json.dumps({"csv": str(csv_path), "rows": len(rows), "columns": len(fields)}, ensure_ascii=False))


    if errors:
        print("FAIL", file=sys.stderr)
        for e in errors:
            print(f"- {e}", file=sys.stderr)
        raise SystemExit(1)
    print("PASS preflight")


def health(args):
    headers = {}
    password = args.password or os.environ.get("CS_FLASHCARDS_PASSWORD", "")
    username = args.username or os.environ.get("CS_FLASHCARDS_USERNAME", "cs")
    if password:
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    base = args.url.rstrip("/")
    for path in ["/api/health", "/api/cards"]:
        req = Request(base + path, headers=headers)
        with urlopen(req, timeout=args.timeout) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
        summary = data.get("summary", data)
        print(json.dumps({"url": base + path, "status": resp.status, "summary": summary}, ensure_ascii=False, default=str))
        if path == "/api/health" and not data.get("ok"):
            raise SystemExit("health ok is not true")


def main():
    parser = argparse.ArgumentParser(description="CS flashcards deploy guard")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preflight")
    p.add_argument("--csv", default="data/CS_encyclopedia_300plus.csv")
    p.set_defaults(func=preflight)
    p = sub.add_parser("health")
    p.add_argument("--url", required=True)
    p.add_argument("--username", default="cs")
    p.add_argument("--password", default="")
    p.add_argument("--timeout", type=float, default=5)
    p.set_defaults(func=health)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
