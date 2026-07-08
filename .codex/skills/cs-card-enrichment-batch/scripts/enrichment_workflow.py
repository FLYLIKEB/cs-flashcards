#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

REVIEW_COLUMNS = {"known_status", "last_reviewed", "review_count"}
REQUIRED_OUTPUT = {"id", "definition", "detailed_explanation", "review_passed", "review_notes"}


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader), list(reader.fieldnames or [])


def write_csv(path: Path, rows, fieldnames):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_jsonl(path: Path):
    records = []
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            records.append(obj)
    return records


def export(args):
    rows, _ = read_csv(args.csv)
    selected = rows
    if args.category:
        selected = [r for r in selected if r.get("category") == args.category]
    if args.ids:
        ids = set(args.ids.split(","))
        selected = [r for r in selected if r.get("id") in ids]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for row in selected:
            payload = {k: row.get(k, "") for k in [
                "id", "term", "english", "category", "definition", "detailed_explanation",
                "related_concepts", "source_files", "exam_note", "bok_appeared", "importance", "difficulty"
            ]}
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(f"exported {len(selected)} row(s) to {args.out}")


def validate_records(csv_path: Path, input_path: Path | None, output_path: Path):
    csv_rows, _ = read_csv(csv_path)
    csv_ids = {r.get("id") for r in csv_rows}
    outputs = read_jsonl(output_path)
    errors = []

    if input_path:
        inputs = read_jsonl(input_path)
        input_ids = [r.get("id") for r in inputs]
    else:
        input_ids = [r.get("id") for r in csv_rows]

    output_ids = [r.get("id") for r in outputs]
    if len(outputs) != len(input_ids):
        errors.append(f"line count mismatch: input {len(input_ids)} vs output {len(outputs)}")
    if output_ids != input_ids:
        errors.append("output IDs must match input IDs in the same order")
    dupes = [k for k, v in Counter(output_ids).items() if v > 1]
    if dupes:
        errors.append(f"duplicate output IDs: {dupes[:10]}")
    missing = [i for i in output_ids if i not in csv_ids]
    if missing:
        errors.append(f"IDs not present in CSV: {missing[:10]}")

    for idx, obj in enumerate(outputs, 1):
        missing_keys = REQUIRED_OUTPUT - set(obj)
        if missing_keys:
            errors.append(f"line {idx} missing keys: {sorted(missing_keys)}")
        if obj.get("review_passed") is not True:
            errors.append(f"line {idx} review_passed is not true")
        definition = str(obj.get("definition", "")).strip()
        detail = str(obj.get("detailed_explanation", "")).strip()
        if not definition:
            errors.append(f"line {idx} empty definition")
        if len(re.findall(r"[.!?。？！]", definition)) > 1:
            errors.append(f"line {idx} definition appears to contain multiple sentences")
        if not detail.startswith("의미:"):
            errors.append(f"line {idx} detailed_explanation must start with 의미:")
        if "활용:" not in detail:
            errors.append(f"line {idx} detailed_explanation must contain 활용:")
        if "동작/활용:" in detail:
            errors.append(f"line {idx} contains stale 동작/활용: format")

    if errors:
        raise SystemExit("FAIL\n" + "\n".join(f"- {e}" for e in errors[:100]))
    print(f"PASS {len(outputs)} records")


def validate(args):
    validate_records(args.csv, args.input, args.output)


def apply(args):
    validate_records(args.csv, args.input, args.output)
    rows, fieldnames = read_csv(args.csv)
    updates = {r["id"]: r for r in read_jsonl(args.output)}
    backup = args.csv.with_suffix(args.csv.suffix + f".bak-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(args.csv, backup)
    changed = 0
    for row in rows:
        upd = updates.get(row.get("id"))
        if not upd:
            continue
        for col in ["definition", "detailed_explanation"]:
            if row.get(col, "") != upd.get(col, ""):
                row[col] = upd.get(col, "")
                changed += 1
        for col in REVIEW_COLUMNS:
            # Preserve progress fields exactly as they were in the CSV.
            row[col] = row.get(col, "")
    write_csv(args.csv, rows, fieldnames)
    print(f"applied {len(updates)} record(s), changed {changed} cell(s), backup {backup}")


def main():
    parser = argparse.ArgumentParser(description="CS flashcard enrichment helper")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("export")
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--category")
    p.add_argument("--ids", help="comma-separated IDs")
    p.add_argument("--out", type=Path, required=True)
    p.set_defaults(func=export)
    p = sub.add_parser("validate")
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--input", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.set_defaults(func=validate)
    p = sub.add_parser("apply")
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--input", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.set_defaults(func=apply)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
