#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from textwrap import shorten
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "CS_encyclopedia_300plus.csv"
DEFAULT_OUT = ROOT / "static" / "generated" / "concepts"
IMAGE_COLUMNS = ["concept_image_url", "concept_image_alt"]
REVIEW_COLUMNS = ["known_status", "last_reviewed", "review_count"]

CATEGORY_STYLES = {
    "데이터베이스": ("#2563eb", "#eff6ff", "DB"),
    "운영체제": ("#475569", "#f1f5f9", "OS"),
    "네트워크": ("#0891b2", "#ecfeff", "NET"),
    "자료구조·알고리즘": ("#7c3aed", "#f5f3ff", "ALG"),
    "프로그래밍 언어": ("#16a34a", "#f0fdf4", "CODE"),
    "소프트웨어공학": ("#ca8a04", "#fefce8", "SW"),
    "컴퓨터구조": ("#9333ea", "#faf5ff", "CPU"),
    "보안": ("#dc2626", "#fef2f2", "SEC"),
    "클라우드·분산시스템": ("#0284c7", "#f0f9ff", "CLOUD"),
    "인공지능·데이터": ("#db2777", "#fdf2f8", "AI"),
    "금융IT·신기술": ("#0f766e", "#f0fdfa", "FIN"),
}
DEFAULT_STYLE = ("#1f3a5f", "#f6f1e8", "CS")

STOP_WORDS = {
    "그리고", "또는", "으로", "에서", "에게", "하는", "한다", "된다", "위해", "통해", "대한",
    "개념", "설명", "정의", "의미", "활용", "관련", "시스템", "데이터", "사용", "기준",
}

@dataclass(frozen=True)
class RenderedCard:
    card_id: str
    url: str
    alt: str
    path: str


def clean_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return cleaned or "card"


def text(value: object) -> str:
    return str(value or "").strip()


def esc(value: object) -> str:
    return html.escape(text(value), quote=True)


def parse_related(raw: str, limit: int = 4) -> list[str]:
    found = re.findall(r"\[\[([^\]]+)\]\]", raw or "")
    if not found:
        found = re.split(r"[,;/]", raw or "")
    result: list[str] = []
    for item in found:
        label = item.strip().split("|")[0].strip()
        if label and label not in result:
            result.append(label)
        if len(result) >= limit:
            break
    return result


def compact_sentence(value: str, max_chars: int = 118) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    value = re.sub(r"^(의미|활용|정의|특징)\s*[:：]\s*", "", value)
    if len(value) <= max_chars:
        return value
    return shorten(value, width=max_chars, placeholder="…")


def wrap_korean(value: str, width: int, max_lines: int) -> list[str]:
    words = re.split(r"(\s+)", text(value))
    lines: list[str] = []
    cur = ""
    for token in words:
        if not token:
            continue
        nxt = cur + token
        if len(nxt) > width and cur.strip():
            lines.append(cur.strip())
            cur = token.strip()
            if len(lines) >= max_lines:
                break
        else:
            cur = nxt
    if len(lines) < max_lines and cur.strip():
        lines.append(cur.strip())
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if len(lines) == max_lines and len(" ".join(lines)) < len(text(value)):
        lines[-1] = lines[-1].rstrip("…") + "…"
    return lines


def keywords(row: dict[str, str], limit: int = 5) -> list[str]:
    source = " ".join([text(row.get("term")), text(row.get("english")), text(row.get("definition")), text(row.get("exam_note"))])
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{1,}|[가-힣]{2,}", source)
    scored: dict[str, int] = {}
    for tok in tokens:
        norm = tok.strip()
        if norm in STOP_WORDS or len(norm) < 2:
            continue
        score = 3 if norm in text(row.get("term")) or norm in text(row.get("english")) else 1
        scored[norm] = scored.get(norm, 0) + score
    ordered = sorted(scored, key=lambda k: (-scored[k], len(k), k))
    return ordered[:limit]


def category_icon(category: str, color: str) -> str:
    stroke = esc(color)
    attrs = f'fill="none" stroke="{stroke}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" opacity="0.92"'
    if category == "데이터베이스":
        return f'<ellipse cx="120" cy="66" rx="58" ry="20" {attrs}/><path d="M62 66v92c0 13 26 24 58 24s58-11 58-24V66" {attrs}/><path d="M62 112c0 13 26 24 58 24s58-11 58-24" {attrs}/>'
    if category == "보안":
        return f'<path d="M120 34l74 28v50c0 47-29 78-74 99-45-21-74-52-74-99V62z" {attrs}/><path d="M86 116l22 22 48-55" {attrs}/>'
    if category == "네트워크":
        return f'<circle cx="60" cy="74" r="22" {attrs}/><circle cx="181" cy="70" r="22" {attrs}/><circle cx="120" cy="166" r="26" {attrs}/><path d="M82 78l77-6M73 93l33 51M168 91l-34 54" {attrs}/>'
    if category == "자료구조·알고리즘":
        return f'<rect x="42" y="54" width="70" height="48" rx="10" {attrs}/><rect x="132" y="54" width="70" height="48" rx="10" {attrs}/><rect x="87" y="145" width="70" height="48" rx="10" {attrs}/><path d="M112 78h20M122 102v43" {attrs}/>'
    if category == "컴퓨터구조":
        return f'<rect x="54" y="48" width="136" height="120" rx="18" {attrs}/><path d="M82 28v20M122 28v20M162 28v20M82 168v22M122 168v22M162 168v22M34 80h20M34 124h20M190 80h20M190 124h20" {attrs}/>'
    if category == "클라우드·분산시스템":
        return f'<path d="M60 154h124c26 0 43-16 43-38 0-21-17-36-40-36-10-29-35-48-67-48-36 0-64 25-71 58-24 2-41 17-41 37 0 17 14 27 52 27z" {attrs}/><path d="M78 196h84M120 154v42" {attrs}/>'
    if category == "인공지능·데이터":
        return f'<path d="M72 94c0-34 24-62 50-62s50 28 50 62c0 24-11 40-27 53v28H99v-28C83 134 72 118 72 94z" {attrs}/><path d="M98 206h48M105 229h34M98 100h48M122 72v58" {attrs}/>'
    if category == "프로그래밍 언어":
        return f'<path d="M82 62l-54 56 54 56M162 62l54 56-54 56M142 44l-40 146" {attrs}/>'
    if category == "소프트웨어공학":
        return f'<path d="M38 166l82-101 82 101" {attrs}/><path d="M70 166v-52h100v52M94 166v-26h52v26" {attrs}/>'
    if category == "금융IT·신기술":
        return f'<rect x="40" y="62" width="164" height="104" rx="20" {attrs}/><path d="M40 98h164M78 135h42M156 135h22" {attrs}/><circle cx="122" cy="205" r="18" {attrs}/>'
    return f'<circle cx="122" cy="116" r="76" {attrs}/><path d="M82 116h80M122 76v80" {attrs}/>'


def svg_for(row: dict[str, str]) -> str:
    category = text(row.get("category"))
    color, soft, tag = CATEGORY_STYLES.get(category, DEFAULT_STYLE)
    term = text(row.get("term")) or text(row.get("english")) or text(row.get("id"))
    english = text(row.get("english"))
    definition = compact_sentence(text(row.get("definition")), 128)
    definition_lines = wrap_korean(definition, 28, 4)
    related = parse_related(text(row.get("related_concepts")), 4)
    keys = keywords(row, 4)
    alt_title = f"{term} 개념 이해 이미지"

    related_nodes = []
    for i, label in enumerate(related or keys[:3] or [category or "CS"]):
        x = 424 + (i % 2) * 204
        y = 222 + (i // 2) * 44
        related_nodes.append(f'<rect x="{x}" y="{y}" width="188" height="34" rx="17" fill="#fff" stroke="{esc(color)}" stroke-width="2" opacity="0.96"/>')
        related_nodes.append(f'<text x="{x+94}" y="{y+23}" text-anchor="middle" class="node">{esc(shorten(label, width=14, placeholder="…"))}</text>')

    kw_nodes = []
    for i, label in enumerate(keys[:4]):
        x = 104 + i * 120
        kw_nodes.append(f'<rect x="{x}" y="430" width="104" height="34" rx="17" fill="{esc(soft)}" stroke="{esc(color)}" opacity="0.95"/>')
        kw_nodes.append(f'<text x="{x+52}" y="452" text-anchor="middle" class="keyword">{esc(shorten(label, width=10, placeholder="…"))}</text>')

    def_text = []
    for i, line in enumerate(definition_lines):
        def_text.append(f'<text x="446" y="{327 + i*30}" class="definition">{esc(line)}</text>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="520" viewBox="0 0 900 520" role="img" aria-labelledby="title desc">
  <title id="title">{esc(alt_title)}</title>
  <desc id="desc">{esc(definition)}</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#ffffff"/>
      <stop offset="0.58" stop-color="{esc(soft)}"/>
      <stop offset="1" stop-color="#fffaf0"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="12" stdDeviation="14" flood-color="#1d1914" flood-opacity="0.11"/></filter>
    <style>
      text {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif; fill: #1f2937; }}
      .label {{ font-size: 22px; font-weight: 850; fill: {esc(color)}; letter-spacing: -0.03em; }}
      .term {{ font-size: 42px; font-weight: 900; letter-spacing: -0.06em; }}
      .english {{ font-size: 18px; font-weight: 740; fill: #64748b; }}
      .definition {{ font-size: 22px; font-weight: 650; letter-spacing: -0.04em; }}
      .node {{ font-size: 20px; font-weight: 860; fill: {esc(color)}; letter-spacing: -0.04em; }}
      .keyword {{ font-size: 14px; font-weight: 800; fill: {esc(color)}; letter-spacing: -0.04em; }}
    </style>
  </defs>
  <rect width="900" height="520" rx="36" fill="url(#bg)"/>
  <circle cx="168" cy="168" r="126" fill="{esc(color)}" opacity="0.065"/>
  <circle cx="742" cy="414" r="174" fill="{esc(color)}" opacity="0.05"/>
  <rect x="48" y="42" width="804" height="436" rx="32" fill="rgba(255,255,255,0.72)" stroke="{esc(color)}" stroke-width="2" opacity="0.72"/>
  <g transform="translate(76 66) scale(0.92)">{category_icon(category, color)}</g>
  <rect x="72" y="326" width="220" height="42" rx="21" fill="{esc(soft)}" stroke="{esc(color)}" opacity="0.95"/>
  <text x="182" y="354" text-anchor="middle" class="label">{esc(category or 'CS')}</text>
  <text x="452" y="92" class="label">{esc(tag)} · 핵심 구조</text>
  <text x="452" y="148" class="term">{esc(shorten(term, width=18, placeholder='…'))}</text>
  <text x="454" y="181" class="english">{esc(shorten(english, width=34, placeholder='…'))}</text>
  <rect x="424" y="204" width="390" height="6" rx="3" fill="{esc(color)}" opacity="0.22"/>
  {''.join(related_nodes)}
  <rect x="424" y="288" width="402" height="132" rx="22" fill="#fff" stroke="{esc(color)}" stroke-width="2" opacity="0.86"/>
  {''.join(def_text)}
  <text x="104" y="410" class="label">기억 단서</text>
  {''.join(kw_nodes)}
</svg>
'''


def read_rows(csv_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = [{field: (row.get(field) or "") for field in fieldnames} for row in reader]
    return rows, fieldnames


def write_rows(csv_path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    tmp = csv_path.with_name(f".{csv_path.name}.concept-images.tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(csv_path)


def render_one(row: dict[str, str], out_dir: Path, url_prefix: str) -> RenderedCard:
    card_id = text(row.get("id")) or text(row.get("\ufeffid"))
    safe = clean_id(card_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{safe}.svg"
    path.write_text(svg_for(row), encoding="utf-8")
    url = f"{url_prefix.rstrip('/')}/{path.name}"
    term = text(row.get("term")) or card_id
    category = text(row.get("category"))
    related = ", ".join(parse_related(text(row.get("related_concepts")), 3))
    alt = f"{term}({category})의 정의, 핵심 단서, 관련 개념을 요약한 학습용 개념 이미지"
    if related:
        alt += f"; 관련 개념: {related}"
    return RenderedCard(card_id=card_id, url=url, alt=alt, path=str(path))


def upload_to_s3(out_dir: Path, bucket: str, prefix: str, public_base_url: str | None) -> str:
    dest = f"s3://{bucket.strip('/')}/{prefix.strip('/')}" if prefix.strip("/") else f"s3://{bucket.strip('/')}"
    cmd = [
        "aws", "s3", "sync", str(out_dir), dest,
        "--exclude", "*", "--include", "*.svg",
        "--content-type", "image/svg+xml; charset=utf-8",
        "--cache-control", "public,max-age=31536000,immutable",
    ]
    subprocess.run(cmd, check=True)
    if public_base_url:
        return public_base_url.rstrip("/")
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "ap-northeast-2"
    host = f"https://{bucket}.s3.{region}.amazonaws.com"
    return f"{host}/{prefix.strip('/')}" if prefix.strip("/") else host


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate per-card educational concept SVGs and write image URLs to the flashcard CSV.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--url-prefix", default="/static/generated/concepts")
    parser.add_argument("--jobs", type=int, default=min(8, (os.cpu_count() or 4)))
    parser.add_argument("--write-csv", action="store_true", help="Persist concept_image_url/concept_image_alt columns to the CSV.")
    parser.add_argument("--s3-bucket", default=os.environ.get("CS_FLASHCARD_IMAGE_S3_BUCKET", ""))
    parser.add_argument("--s3-prefix", default=os.environ.get("CS_FLASHCARD_IMAGE_S3_PREFIX", "cs-flashcards/concepts"))
    parser.add_argument("--s3-public-base-url", default=os.environ.get("CS_FLASHCARD_IMAGE_PUBLIC_BASE_URL", ""))
    parser.add_argument("--manifest", type=Path, default=ROOT / "static" / "generated" / "concepts-manifest.json")
    args = parser.parse_args(list(argv) if argv is not None else None)

    rows, fieldnames = read_rows(args.csv)
    for col in IMAGE_COLUMNS:
        if col not in fieldnames:
            insert_at = next((fieldnames.index(c) for c in REVIEW_COLUMNS if c in fieldnames), len(fieldnames))
            fieldnames.insert(insert_at, col)

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        rendered = list(pool.map(lambda r: render_one(r, args.out_dir, args.url_prefix), rows))

    url_by_id = {item.card_id: item.url for item in rendered}
    alt_by_id = {item.card_id: item.alt for item in rendered}

    if args.s3_bucket:
        remote_prefix = upload_to_s3(args.out_dir, args.s3_bucket, args.s3_prefix, args.s3_public_base_url or None)
        url_by_id = {item.card_id: f"{remote_prefix.rstrip('/')}/{Path(item.path).name}" for item in rendered}

    for row in rows:
        card_id = text(row.get("id")) or text(row.get("\ufeffid"))
        row["concept_image_url"] = url_by_id.get(card_id, "")
        row["concept_image_alt"] = alt_by_id.get(card_id, "")

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps({"count": len(rendered), "images": [item.__dict__ for item in rendered]}, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.write_csv:
        write_rows(args.csv, rows, fieldnames)

    print(f"generated {len(rendered)} concept image(s) in {args.out_dir}")
    if args.s3_bucket:
        print(f"uploaded to s3://{args.s3_bucket}/{args.s3_prefix.strip('/')}")
    if args.write_csv:
        print(f"updated CSV columns: {', '.join(IMAGE_COLUMNS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
