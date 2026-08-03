#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

REQUIRED = [
    "term", "english", "category", "definition", "detailed_explanation", "related_concepts",
    "source_files", "exam_note", "bok_appeared", "importance", "difficulty",
]
VALID_CATEGORIES = {
    "데이터베이스", "운영체제", "네트워크", "자료구조·알고리즘", "프로그래밍 언어", "소프트웨어공학",
    "컴퓨터구조", "보안", "클라우드·분산시스템", "인공지능·데이터", "금융IT·신기술",
}
VALID_LEVELS = {"상", "중", "하"}
PROGRESS_DEFAULTS = {"known_status": "", "last_reviewed": "", "review_count": "0"}


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader), list(reader.fieldnames or [])


def read_jsonl(path: Path):
    rows = []
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{lineno}: invalid JSON: {exc}")
    return rows


def max_id(rows):
    nums = []
    for r in rows:
        m = re.fullmatch(r"CS-(\d+)", r.get("id", ""))
        if m:
            nums.append(int(m.group(1)))
    return max(nums or [0])


def add_ids(csv_rows, candidates):
    start = max_id(csv_rows)
    width = max(3, len(str(start + len(candidates))))
    out = []
    for idx, c in enumerate(candidates, 1):
        item = dict(c)
        item["id"] = f"CS-{start + idx:0{width}d}"
        out.append(item)
    return out


def validate_candidates(csv_path: Path, candidates_path: Path):
    csv_rows, fields = read_csv(csv_path)
    candidates = read_jsonl(candidates_path)
    errors = []
    existing_terms = {norm(r.get("term")): r.get("id") for r in csv_rows if r.get("term")}
    existing_english = {norm(r.get("english")): r.get("id") for r in csv_rows if r.get("english")}
    seen_terms = set()
    for idx, c in enumerate(candidates, 1):
        missing = [k for k in REQUIRED if k not in c]
        if missing:
            errors.append(f"candidate {idx} missing {missing}")
        term = norm(c.get("term"))
        eng = norm(c.get("english"))
        if not term:
            errors.append(f"candidate {idx} blank term")
        if term in seen_terms:
            errors.append(f"candidate {idx} duplicate term within candidates: {c.get('term')}")
        seen_terms.add(term)
        if term in existing_terms:
            errors.append(f"candidate {idx} term already exists as {existing_terms[term]}: {c.get('term')}")
        if eng and eng in existing_english:
            errors.append(f"candidate {idx} english already exists as {existing_english[eng]}: {c.get('english')}")
        if c.get("category") not in VALID_CATEGORIES:
            errors.append(f"candidate {idx} invalid category: {c.get('category')}")
        if c.get("importance") not in VALID_LEVELS:
            errors.append(f"candidate {idx} invalid importance: {c.get('importance')}")
        if c.get("difficulty") not in VALID_LEVELS:
            errors.append(f"candidate {idx} invalid difficulty: {c.get('difficulty')}")
        if c.get("bok_appeared", "") not in {"", "O"}:
            errors.append(f"candidate {idx} invalid bok_appeared: {c.get('bok_appeared')}")
        detail = c.get("detailed_explanation", "")
        if not str(detail).startswith("의미:") or "활용:" not in str(detail):
            errors.append(f"candidate {idx} detailed_explanation must use 의미:/활용:")
    assigned = add_ids(csv_rows, candidates)
    if errors:
        raise SystemExit("FAIL\n" + "\n".join(f"- {e}" for e in errors[:100]))
    print(json.dumps({"status": "PASS", "candidate_count": len(candidates), "next_ids": [c["id"] for c in assigned]}, ensure_ascii=False))
    return csv_rows, fields, assigned


def cmd_validate(args):
    validate_candidates(args.csv, args.candidates)


def cmd_append(args):
    csv_rows, fields, assigned = validate_candidates(args.csv, args.candidates)
    for col in ["alphabet_index", "korean_initial", *PROGRESS_DEFAULTS.keys()]:
        if col not in fields:
            fields.append(col)
    output_rows = list(csv_rows)
    for c in assigned:
        row = {field: "" for field in fields}
        row.update(c)
        row.update(PROGRESS_DEFAULTS)
        output_rows.append(row)
    backup = args.csv.with_suffix(args.csv.suffix + f".bak-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(args.csv, backup)
    with args.csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)
    print(json.dumps({"status": "APPENDED", "count": len(assigned), "ids": [c["id"] for c in assigned], "backup": str(backup)}, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description="Validate and append CS flashcard candidates")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("validate")
    s.add_argument("--csv", type=Path, required=True)
    s.add_argument("--candidates", type=Path, required=True)
    s.set_defaults(func=cmd_validate)
    s = sub.add_parser("append")
    s.add_argument("--csv", type=Path, required=True)
    s.add_argument("--candidates", type=Path, required=True)
    s.set_defaults(func=cmd_append)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
