#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

LEVEL_SCORE = {"상": 3, "중": 2, "하": 1}


def read_cards(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_progress(path: Path):
    if not path.exists():
        return {}
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT card_id, known_status, last_reviewed, review_count FROM card_progress").fetchall()
    except sqlite3.Error:
        return {}
    finally:
        conn.close()
    return {r["card_id"]: dict(r) for r in rows}


def parse_time(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def priority(card, now):
    status = card.get("known_status", "")
    score = 0
    reasons = []
    if status == "X":
        score += 100; reasons.append("오답")
    elif status == "":
        score += 45; reasons.append("미학습")
    if card.get("importance") == "상":
        score += 30; reasons.append("중요도 상")
    if card.get("difficulty") == "상":
        score += 18; reasons.append("난이도 상")
    if card.get("bok_appeared") == "O":
        score += 20; reasons.append("한은 표시")
    try:
        count = int(card.get("review_count") or 0)
    except ValueError:
        count = 0
    if status == "X":
        score += min(count, 10)
    last = parse_time(card.get("last_reviewed", ""))
    if last:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        days = max(0, (now - last).days)
        if days >= 7:
            score += min(days, 30); reasons.append(f"{days}일 경과")
    return score, reasons


def build(args):
    cards = read_cards(args.csv)
    progress = read_progress(args.db)
    for c in cards:
        p = progress.get(c.get("id"), {})
        c["known_status"] = p.get("known_status", "")
        c["last_reviewed"] = p.get("last_reviewed", "")
        c["review_count"] = str(p.get("review_count", 0))
    if args.category:
        cards = [c for c in cards if c.get("category") == args.category]
    now = datetime.now(timezone.utc).astimezone()
    counts = Counter(c.get("known_status", "") for c in cards)
    by_cat = defaultdict(lambda: Counter())
    for c in cards:
        by_cat[c.get("category", "미분류")][c.get("known_status", "")] += 1
    queue = []
    for c in cards:
        score, reasons = priority(c, now)
        queue.append({
            "id": c.get("id"), "term": c.get("term"), "category": c.get("category"),
            "known_status": c.get("known_status", ""), "importance": c.get("importance"),
            "difficulty": c.get("difficulty"), "score": score, "reasons": reasons,
        })
    queue.sort(key=lambda x: (-x["score"], x["category"] or "", x["id"] or ""))
    return {
        "total": len(cards),
        "known": counts.get("O", 0),
        "unknown": counts.get("X", 0),
        "unreviewed": counts.get("", 0),
        "db_exists": args.db.exists(),
        "categories": {k: dict(v) for k, v in sorted(by_cat.items())},
        "review_queue": queue[:args.limit],
    }


def print_markdown(data):
    total = data["total"] or 1
    reviewed = data["known"] + data["unknown"]
    print("# CS 플래시카드 학습 분석")
    print()
    print(f"- 총 카드: {data['total']}")
    print(f"- 학습 완료/오답/미학습: O {data['known']} / X {data['unknown']} / 미학습 {data['unreviewed']}")
    print(f"- 리뷰 진행률: {reviewed / total:.1%}")
    print(f"- 진행 DB 존재: {'예' if data['db_exists'] else '아니오'}")
    print("\n## 카테고리별 현황")
    print("| 카테고리 | O | X | 미학습 |")
    print("|---|---:|---:|---:|")
    for cat, c in data["categories"].items():
        print(f"| {cat} | {c.get('O',0)} | {c.get('X',0)} | {c.get('',0)} |")
    print("\n## 우선 복습 큐")
    for i, item in enumerate(data["review_queue"], 1):
        why = ", ".join(item["reasons"]) or "균형 복습"
        print(f"{i}. {item['id']} {item['term']} [{item['category']}] — {why}")


def main():
    p = argparse.ArgumentParser(description="CS flashcards progress report")
    p.add_argument("--csv", type=Path, default=Path("data/CS_encyclopedia_300plus.csv"))
    p.add_argument("--db", type=Path, default=Path("state/progress.sqlite"))
    p.add_argument("--category")
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = p.parse_args()
    data = build(args)
    if args.format == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print_markdown(data)


if __name__ == "__main__":
    main()
