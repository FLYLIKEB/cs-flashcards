from __future__ import annotations

import base64
import csv
import html
from contextlib import closing
import hmac
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import re
from urllib.parse import quote
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from question_generator import SUPPORTED_QUESTION_TYPES, generate_questions

ROOT = Path(__file__).resolve().parent
DEFAULT_CSV_PATH = ROOT / "data" / "CS_encyclopedia_300plus.csv"
DEFAULT_PROGRESS_DB_PATH = ROOT / "state" / "progress.sqlite"
CSV_PATH = Path(os.environ.get("CS_FLASHCARD_CSV", DEFAULT_CSV_PATH)).expanduser().resolve()
PROGRESS_DB_PATH = Path(os.environ.get("CS_FLASHCARD_PROGRESS_DB", DEFAULT_PROGRESS_DB_PATH)).expanduser().resolve()
BACKUP_DIR = Path(os.environ.get("CS_FLASHCARD_BACKUP_DIR", ROOT / "backups")).expanduser().resolve()
STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_WIKI_BOOK_DIR = ROOT.parent / "wikidocs-ebook"
WIKI_BOOK_DIR = Path(os.environ.get("CS_FLASHCARDS_WIKI_BOOK_DIR", DEFAULT_WIKI_BOOK_DIR)).expanduser().resolve()
WIKI_PAGES_DIRNAME = "pages"
WIKI_TOC_NAME = "TOC.md"
WIKI_BOOK_README_NAME = "README.md"
WIKI_BOOK_HOME_SLUG = "_book"
REVIEW_COLUMNS = ["known_status", "last_reviewed", "review_count"]
VALID_STATUSES = {"O", "X", ""}
PUBLIC_USERNAME = os.environ.get("CS_FLASHCARDS_USERNAME", "cs")
PUBLIC_PASSWORD = os.environ.get("CS_FLASHCARDS_PASSWORD", "")

app = FastAPI(title="CS Encyclopedia Flashcards", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class MarkRequest(BaseModel):
    known_status: str = Field(pattern="^(O|X|)$")


class BookmarkRequest(BaseModel):
    bookmarked: bool


class MemoRequest(BaseModel):
    memo: str = Field(default="", max_length=20000)


class QuestionGenerateRequest(BaseModel):
    card_ids: list[str] | None = None
    types: list[str] | None = None
    count: int = Field(default=10, ge=1, le=100)
    seed: int | None = None


def is_authorized(authorization: str | None) -> bool:
    if not PUBLIC_PASSWORD:
        return True
    if not authorization or not authorization.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(authorization.removeprefix("Basic "), validate=True).decode("utf-8")
    except Exception:
        return False
    username, sep, password = decoded.partition(":")
    if not sep:
        return False
    return hmac.compare_digest(username, PUBLIC_USERNAME) and hmac.compare_digest(password, PUBLIC_PASSWORD)


@app.middleware("http")
async def optional_basic_auth(request: Request, call_next):
    if is_authorized(request.headers.get("authorization")):
        return await call_next(request)
    return Response(
        "Authentication required",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="CS Flashcards"'},
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def ensure_review_columns(fieldnames: list[str] | None) -> list[str]:
    if not fieldnames:
        raise ValueError("CSV header is missing")
    fields = list(fieldnames)
    for col in REVIEW_COLUMNS:
        if col not in fields:
            fields.append(col)
    return fields


def normalized_review_count(value: str | None) -> str:
    try:
        count = int(value or "0")
    except ValueError:
        count = 0
    return str(max(0, count))


def normalized_bookmarked(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return "1" if value == 1 else "0"
    return "1" if str(value or "").strip().lower() in {"1", "true", "yes", "y", "o", "on"} else "0"


def progress_db_for(csv_path: Path, progress_db_path: Path | None = None) -> Path:
    if progress_db_path is not None:
        return progress_db_path.expanduser().resolve()
    if csv_path.resolve() == CSV_PATH:
        return PROGRESS_DB_PATH
    return csv_path.with_suffix(".progress.sqlite").resolve()


def read_csv_cards(csv_path: Path = CSV_PATH, *, keep_csv_progress: bool = False) -> tuple[list[dict[str, str]], list[str]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = ensure_review_columns(reader.fieldnames)
        rows: list[dict[str, str]] = []
        for row in reader:
            normalized = {field: (row.get(field) or "") for field in fieldnames}
            if normalized.get("known_status") not in VALID_STATUSES:
                normalized["known_status"] = ""
            normalized["review_count"] = normalized_review_count(normalized.get("review_count"))
            if not keep_csv_progress:
                normalized["known_status"] = ""
                normalized["last_reviewed"] = ""
                normalized["review_count"] = "0"
            rows.append(normalized)
    return rows, fieldnames


def progress_row_is_meaningful(row: dict[str, str]) -> bool:
    return bool(
        row.get("known_status") in {"O", "X"}
        or (row.get("last_reviewed") or "").strip()
        or int(normalized_review_count(row.get("review_count"))) > 0
        or normalized_bookmarked(row.get("bookmarked")) == "1"
        or (row.get("memo") or "").strip()
    )


def connect_progress_db(progress_db_path: Path) -> sqlite3.Connection:
    progress_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(progress_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_progress_db(progress_db_path: Path, seed_rows: list[dict[str, str]] | None = None) -> None:
    existed = progress_db_path.exists()
    with closing(connect_progress_db(progress_db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS card_progress (
                card_id TEXT PRIMARY KEY,
                known_status TEXT NOT NULL DEFAULT '' CHECK (known_status IN ('O', 'X', '')),
                last_reviewed TEXT NOT NULL DEFAULT '',
                review_count INTEGER NOT NULL DEFAULT 0 CHECK (review_count >= 0),
                bookmarked INTEGER NOT NULL DEFAULT 0 CHECK (bookmarked IN (0, 1)),
                memo TEXT NOT NULL DEFAULT '',
                memo_updated_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(card_progress)").fetchall()}
        if "bookmarked" not in columns:
            conn.execute("ALTER TABLE card_progress ADD COLUMN bookmarked INTEGER NOT NULL DEFAULT 0 CHECK (bookmarked IN (0, 1))")
        if "memo" not in columns:
            conn.execute("ALTER TABLE card_progress ADD COLUMN memo TEXT NOT NULL DEFAULT ''")
        if "memo_updated_at" not in columns:
            conn.execute("ALTER TABLE card_progress ADD COLUMN memo_updated_at TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_card_progress_status ON card_progress(known_status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_card_progress_bookmarked ON card_progress(bookmarked)")
        if not existed and seed_rows:
            now = utc_now_iso()
            conn.executemany(
                """
                INSERT OR REPLACE INTO card_progress
                    (card_id, known_status, last_reviewed, review_count, bookmarked, memo, memo_updated_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["id"],
                        row.get("known_status") if row.get("known_status") in VALID_STATUSES else "",
                        row.get("last_reviewed") or "",
                        int(normalized_review_count(row.get("review_count"))),
                        int(normalized_bookmarked(row.get("bookmarked"))),
                        row.get("memo") or "",
                        row.get("memo_updated_at") or (now if (row.get("memo") or "").strip() else ""),
                        now,
                    )
                    for row in seed_rows
                    if row.get("id") and progress_row_is_meaningful(row)
                ],
            )
        conn.commit()


def read_progress(progress_db_path: Path) -> dict[str, dict[str, str]]:
    ensure_progress_db(progress_db_path)
    with closing(connect_progress_db(progress_db_path)) as conn:
        rows = conn.execute(
            "SELECT card_id, known_status, last_reviewed, review_count, bookmarked, memo, memo_updated_at FROM card_progress"
        ).fetchall()
    return {
        row["card_id"]: {
            "known_status": row["known_status"] if row["known_status"] in VALID_STATUSES else "",
            "last_reviewed": row["last_reviewed"] or "",
            "review_count": normalized_review_count(str(row["review_count"])),
            "bookmarked": normalized_bookmarked(row["bookmarked"]),
            "memo": row["memo"] or "",
            "memo_updated_at": row["memo_updated_at"] or "",
        }
        for row in rows
    }


def merge_progress(rows: list[dict[str, str]], progress: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    for row in rows:
        item = dict(row)
        item.setdefault("bookmarked", "0")
        item.setdefault("memo", "")
        item.setdefault("memo_updated_at", "")
        item.update(progress.get(row.get("id", ""), {}))
        item["bookmarked"] = normalized_bookmarked(item.get("bookmarked"))
        item["memo"] = item.get("memo") or ""
        item["memo_updated_at"] = item.get("memo_updated_at") or ""
        merged.append(item)
    return merged


def read_cards(csv_path: Path = CSV_PATH, progress_db_path: Path | None = None) -> tuple[list[dict[str, str]], list[str]]:
    raw_rows, fieldnames = read_csv_cards(csv_path, keep_csv_progress=True)
    clean_rows, _ = read_csv_cards(csv_path, keep_csv_progress=False)
    db_path = progress_db_for(csv_path, progress_db_path)
    ensure_progress_db(db_path, raw_rows)
    rows = merge_progress(clean_rows, read_progress(db_path))
    return rows, fieldnames


def write_cards(rows: list[dict[str, str]], fieldnames: list[str], csv_path: Path = CSV_PATH) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{csv_path.name}.", suffix=".tmp", dir=csv_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_name, csv_path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def backup_csv(csv_path: Path = CSV_PATH, backup_dir: Path = BACKUP_DIR) -> Path | None:
    if not csv_path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = backup_dir / f"{csv_path.stem}_{stamp}{csv_path.suffix}"
    shutil.copy2(csv_path, dest)
    return dest


def mark_card(
    card_id: str,
    status: str,
    csv_path: Path = CSV_PATH,
    backup_dir: Path = BACKUP_DIR,
    progress_db_path: Path | None = None,
) -> dict[str, str]:
    del backup_dir  # Progress is stored in SQLite; CSV backup is kept only for backwards-compatible signature.
    if status not in VALID_STATUSES:
        raise ValueError("known_status must be O, X, or empty")

    rows, _ = read_cards(csv_path, progress_db_path)
    if not any(row.get("id") == card_id for row in rows):
        raise KeyError(card_id)

    db_path = progress_db_for(csv_path, progress_db_path)
    ensure_progress_db(db_path)
    with closing(connect_progress_db(db_path)) as conn:
        existing = conn.execute(
            "SELECT review_count FROM card_progress WHERE card_id = ?",
            (card_id,),
        ).fetchone()
        try:
            count = int(existing["review_count"] if existing else 0)
        except (TypeError, ValueError):
            count = 0
        last_reviewed = ""
        if status:
            count += 1
            last_reviewed = utc_now_iso()
        conn.execute(
            """
            INSERT INTO card_progress (card_id, known_status, last_reviewed, review_count, bookmarked, memo, memo_updated_at, updated_at)
            VALUES (?, ?, ?, ?, 0, '', '', ?)
            ON CONFLICT(card_id) DO UPDATE SET
                known_status = excluded.known_status,
                last_reviewed = excluded.last_reviewed,
                review_count = excluded.review_count,
                updated_at = excluded.updated_at
            """,
            (card_id, status, last_reviewed, max(0, count), utc_now_iso()),
        )
        conn.commit()

    updated_rows, _ = read_cards(csv_path, db_path)
    for row in updated_rows:
        if row.get("id") == card_id:
            return row
    raise KeyError(card_id)


def _ensure_card_exists(card_id: str, csv_path: Path, progress_db_path: Path | None = None) -> None:
    rows, _ = read_cards(csv_path, progress_db_path)
    if not any(row.get("id") == card_id for row in rows):
        raise KeyError(card_id)


def set_bookmark(
    card_id: str,
    bookmarked: bool,
    csv_path: Path = CSV_PATH,
    progress_db_path: Path | None = None,
) -> dict[str, str]:
    _ensure_card_exists(card_id, csv_path, progress_db_path)
    db_path = progress_db_for(csv_path, progress_db_path)
    ensure_progress_db(db_path)
    with closing(connect_progress_db(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO card_progress (card_id, known_status, last_reviewed, review_count, bookmarked, memo, memo_updated_at, updated_at)
            VALUES (?, '', '', 0, ?, '', '', ?)
            ON CONFLICT(card_id) DO UPDATE SET
                bookmarked = excluded.bookmarked,
                updated_at = excluded.updated_at
            """,
            (card_id, 1 if bookmarked else 0, utc_now_iso()),
        )
        conn.commit()

    updated_rows, _ = read_cards(csv_path, db_path)
    for row in updated_rows:
        if row.get("id") == card_id:
            return row
    raise KeyError(card_id)


def save_memo(
    card_id: str,
    memo: str,
    csv_path: Path = CSV_PATH,
    progress_db_path: Path | None = None,
) -> dict[str, str]:
    _ensure_card_exists(card_id, csv_path, progress_db_path)
    normalized_memo = str(memo or "")[:20000]
    memo_updated_at = utc_now_iso() if normalized_memo.strip() else ""
    db_path = progress_db_for(csv_path, progress_db_path)
    ensure_progress_db(db_path)
    with closing(connect_progress_db(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO card_progress (card_id, known_status, last_reviewed, review_count, bookmarked, memo, memo_updated_at, updated_at)
            VALUES (?, '', '', 0, 0, ?, ?, ?)
            ON CONFLICT(card_id) DO UPDATE SET
                memo = excluded.memo,
                memo_updated_at = excluded.memo_updated_at,
                updated_at = excluded.updated_at
            """,
            (card_id, normalized_memo, memo_updated_at, utc_now_iso()),
        )
        conn.commit()

    updated_rows, _ = read_cards(csv_path, db_path)
    for row in updated_rows:
        if row.get("id") == card_id:
            return row
    raise KeyError(card_id)


def summarize(rows: list[dict[str, str]]) -> dict[str, Any]:
    total = len(rows)
    known = sum(1 for row in rows if row.get("known_status") == "O")
    unknown = sum(1 for row in rows if row.get("known_status") == "X")
    unreviewed = total - known - unknown
    bookmarked = sum(1 for row in rows if normalized_bookmarked(row.get("bookmarked")) == "1")
    memo_count = sum(1 for row in rows if (row.get("memo") or "").strip())
    categories = sorted({row.get("category", "") for row in rows if row.get("category")})
    return {
        "total": total,
        "known": known,
        "unknown": unknown,
        "unreviewed": unreviewed,
        "bookmarked": bookmarked,
        "memo_count": memo_count,
        "categories": categories,
        "csv_path": str(CSV_PATH),
        "progress_db_path": str(PROGRESS_DB_PATH),
    }
WIKI_TOC_ITEM_RE = re.compile(r"^(?P<indent>\s*)-\s+\[(?P<title>.+?)\]\((?P<href>[^)]+)\)\s*$")
WIKI_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
WIKI_LIST_RE = re.compile(r"^(?P<indent>\s*)(?P<marker>[-*+]|\d+\.)\s+(?P<body>.*)$")
WIKI_CODE_FENCE_RE = re.compile(r"^```(?P<lang>[\w+-]*)\s*$")
WIKI_TABLE_SEPARATOR_RE = re.compile(r"^\|?\s*:?[-]{3,}:?(?:\s*\|\s*:?[-]{3,}:?)*\s*\|?$")
WIKI_INLINE_TOKEN_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)|\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*|\*([^*]+)\*")



def wiki_book_dir(repo_dir: Path = WIKI_BOOK_DIR) -> Path:
    resolved = Path(repo_dir).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Wiki book directory not found: {resolved}")
    return resolved



def wiki_pages_dir(repo_dir: Path) -> Path:
    return repo_dir / WIKI_PAGES_DIRNAME



def wiki_toc_path(repo_dir: Path) -> Path:
    return repo_dir / WIKI_TOC_NAME



def wiki_readme_path(repo_dir: Path) -> Path:
    return repo_dir / WIKI_BOOK_README_NAME



def wiki_page_url(slug: str) -> str:
    normalized = str(slug or "").strip("/") or WIKI_BOOK_HOME_SLUG
    return f"/wiki/page/{quote(normalized, safe='/')}"



def wiki_raw_url(relative_path: str) -> str:
    return f"/api/wiki/raw/{quote(str(relative_path).replace(os.sep, '/'), safe='/')}"



def wiki_heading_id(text: str) -> str:
    normalized = re.sub(r"[^\w가-힣ㄱ-ㅎㅏ-ㅣ -]", "", str(text or "").strip().lower())
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or "section"



def extract_markdown_title(markdown_text: str, fallback: str) -> str:
    for line in markdown_text.splitlines():
        match = WIKI_HEADING_RE.match(line.strip())
        if match and len(match.group(1)) == 1:
            return match.group(2).strip()
    return fallback



def safe_wiki_path(repo_dir: Path, relative_path: str) -> Path | None:
    root = repo_dir.resolve()
    candidate = (root / str(relative_path or "")).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate



def resolve_wiki_reference(repo_dir: Path, href: str, base_path: Path) -> Path | None:
    clean = str(href or "").strip()
    if not clean or clean.startswith("#") or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", clean) or clean.startswith("//"):
        return None
    clean = clean.split("#", 1)[0].split("?", 1)[0].strip()
    if not clean:
        return None
    candidates = [
        (base_path.parent / clean).resolve(),
        (repo_dir / clean).resolve(),
    ]
    for candidate in candidates:
        try:
            candidate.relative_to(repo_dir)
        except ValueError:
            continue
        if candidate.exists() and candidate.is_file():
            return candidate
    return None



def wiki_slug_for_source(repo_dir: Path, source_path: Path) -> str:
    if source_path.resolve() == wiki_readme_path(repo_dir).resolve():
        return WIKI_BOOK_HOME_SLUG
    relative = source_path.resolve().relative_to(wiki_pages_dir(repo_dir).resolve())
    return relative.with_suffix("").as_posix()



def split_markdown_cells(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]



def rewrite_markdown_href(repo_dir: Path, current_source: Path, href: str) -> str:
    clean = str(href or "").strip()
    if not clean:
        return "#"
    if clean.startswith("#") or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", clean) or clean.startswith("//"):
        return clean
    fragment = "#" + clean.split("#", 1)[1] if "#" in clean else ""
    target = resolve_wiki_reference(repo_dir, clean, current_source)
    if not target:
        return clean
    relative = str(target.relative_to(repo_dir)).replace(os.sep, "/")
    if target.suffix.lower() == ".md":
        return f"{wiki_page_url(wiki_slug_for_source(repo_dir, target))}{fragment}"
    return f"{wiki_raw_url(relative)}{fragment}"



def render_inline_markdown(text: str, repo_dir: Path, current_source: Path) -> str:
    parts = re.split(r"(`[^`]+`)", str(text or ""))
    rendered: list[str] = []
    for part in parts:
        if not part:
            continue
        if part.startswith("`") and part.endswith("`"):
            rendered.append(f"<code>{html.escape(part[1:-1])}</code>")
            continue
        rendered.append(render_inline_markdown_tokens(part, repo_dir, current_source))
    return "".join(rendered)



def render_inline_markdown_tokens(text: str, repo_dir: Path, current_source: Path) -> str:
    rendered: list[str] = []
    last = 0
    for match in WIKI_INLINE_TOKEN_RE.finditer(text):
        rendered.append(html.escape(text[last:match.start()]))
        if match.group(1) is not None:
            alt = html.escape(match.group(1))
            src = html.escape(rewrite_markdown_href(repo_dir, current_source, match.group(2)), quote=True)
            rendered.append(f'<img class="wiki-inline-image" src="{src}" alt="{alt}" loading="lazy" decoding="async" />')
        elif match.group(3) is not None:
            href = html.escape(rewrite_markdown_href(repo_dir, current_source, match.group(4)), quote=True)
            label = html.escape(match.group(3))
            if href.startswith("/wiki/") or href.startswith("/api/wiki/") or href.startswith("#"):
                rendered.append(f'<a href="{href}">{label}</a>')
            else:
                rendered.append(f'<a href="{href}" target="_blank" rel="noopener noreferrer">{label}</a>')
        elif match.group(5) is not None:
            rendered.append(f"<strong>{html.escape(match.group(5))}</strong>")
        elif match.group(6) is not None:
            rendered.append(f"<em>{html.escape(match.group(6))}</em>")
        last = match.end()
    rendered.append(html.escape(text[last:]))
    return "".join(rendered)



def render_markdown_list(lines: list[str], repo_dir: Path, current_source: Path) -> str:
    first_match = WIKI_LIST_RE.match(lines[0])
    tag = "ol" if first_match and first_match.group("marker").endswith(".") else "ul"
    items: list[str] = []
    for line in lines:
        match = WIKI_LIST_RE.match(line)
        if not match:
            continue
        items.append(f"<li>{render_inline_markdown(match.group('body').strip(), repo_dir, current_source)}</li>")
    return f"<{tag}>" + "".join(items) + f"</{tag}>"



def render_markdown_table(lines: list[str], repo_dir: Path, current_source: Path) -> str:
    rows = [split_markdown_cells(line) for line in lines]
    if len(rows) >= 2 and WIKI_TABLE_SEPARATOR_RE.match(lines[1].strip()):
        head, body_rows = rows[0], rows[2:]
    else:
        head, body_rows = rows[0], rows[1:]
    head_html = "".join(f"<th>{render_inline_markdown(cell, repo_dir, current_source)}</th>" for cell in head)
    body_html = "".join(
        "<tr>" + "".join(f"<td>{render_inline_markdown(cell, repo_dir, current_source)}</td>" for cell in row) + "</tr>"
        for row in body_rows
    )
    return "<div class=\"wiki-table-wrap\"><table><thead><tr>" + head_html + "</tr></thead><tbody>" + body_html + "</tbody></table></div>"



def is_markdown_block_start(line: str) -> bool:
    stripped = line.strip()
    return bool(
        not stripped
        or WIKI_HEADING_RE.match(stripped)
        or WIKI_CODE_FENCE_RE.match(stripped)
        or WIKI_LIST_RE.match(line)
        or stripped.startswith(">")
        or stripped.startswith("|")
        or re.fullmatch(r"[-*_]{3,}", stripped)
    )



def render_markdown_blocks(lines: list[str], repo_dir: Path, current_source: Path) -> list[str]:
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        fence = WIKI_CODE_FENCE_RE.match(stripped)
        if fence:
            language = fence.group("lang").strip()
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            class_attr = f' class="language-{html.escape(language, quote=True)}"' if language else ""
            blocks.append(f"<pre><code{class_attr}>{html.escape(chr(10).join(code_lines))}</code></pre>")
            continue
        heading = WIKI_HEADING_RE.match(stripped)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            blocks.append(f'<h{level} id="{wiki_heading_id(title)}">{render_inline_markdown(title, repo_dir, current_source)}</h{level}>')
            index += 1
            continue
        if stripped.startswith("|"):
            table_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            blocks.append(render_markdown_table(table_lines, repo_dir, current_source))
            continue
        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].lstrip().startswith(">"):
                quote_lines.append(re.sub(r"^\s*>\s?", "", lines[index]))
                index += 1
            inner = "".join(render_markdown_blocks(quote_lines, repo_dir, current_source))
            blocks.append(f"<blockquote>{inner}</blockquote>")
            continue
        if re.fullmatch(r"[-*_]{3,}", stripped):
            blocks.append("<hr />")
            index += 1
            continue
        if WIKI_LIST_RE.match(line):
            list_lines: list[str] = []
            while index < len(lines) and WIKI_LIST_RE.match(lines[index]):
                list_lines.append(lines[index])
                index += 1
            blocks.append(render_markdown_list(list_lines, repo_dir, current_source))
            continue
        paragraph_lines = [stripped]
        index += 1
        while index < len(lines) and not is_markdown_block_start(lines[index]):
            paragraph_lines.append(lines[index].strip())
            index += 1
        blocks.append(f"<p>{render_inline_markdown(' '.join(paragraph_lines), repo_dir, current_source)}</p>")
    return blocks



def render_markdown_page(markdown_text: str, repo_dir: Path, current_source: Path) -> str:
    return "".join(render_markdown_blocks(markdown_text.splitlines(), repo_dir, current_source))



def read_wiki_index(repo_dir: Path = WIKI_BOOK_DIR) -> dict[str, Any]:
    repo = wiki_book_dir(repo_dir)
    toc = wiki_toc_path(repo)
    if not toc.exists():
        raise FileNotFoundError(f"Wiki TOC not found: {toc}")
    readme = wiki_readme_path(repo)
    book_title = repo.name
    if readme.exists():
        book_title = extract_markdown_title(readme.read_text(encoding="utf-8"), book_title)
    tree: list[dict[str, Any]] = []
    stack: list[tuple[int, list[dict[str, Any]]]] = [(-1, tree)]
    flat: list[dict[str, Any]] = []
    pages: dict[str, dict[str, Any]] = {}
    for line in toc.read_text(encoding="utf-8").splitlines():
        match = WIKI_TOC_ITEM_RE.match(line)
        if not match:
            continue
        source_path = resolve_wiki_reference(repo, match.group("href"), toc)
        if not source_path:
            continue
        slug = wiki_slug_for_source(repo, source_path)
        source_relative = str(source_path.relative_to(repo)).replace(os.sep, "/")
        item = {
            "title": match.group("title").strip(),
            "slug": slug,
            "source_path": source_relative,
            "url": wiki_page_url(slug),
            "raw_url": wiki_raw_url(source_relative),
            "children": [],
        }
        indent = len(match.group("indent").replace("\t", "    "))
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        stack[-1][1].append(item)
        stack.append((indent, item["children"]))
        flat.append({key: value for key, value in item.items() if key != "children"})
        pages[slug] = {key: value for key, value in item.items() if key != "children"}
    breadcrumbs: dict[str, list[dict[str, str]]] = {}

    def walk(items: list[dict[str, Any]], trail: list[dict[str, str]]) -> None:
        for item in items:
            current = trail + [{"title": item["title"], "slug": item["slug"], "url": item["url"]}]
            breadcrumbs[item["slug"]] = current
            walk(item["children"], current)

    walk(tree, [])
    default_page_slug = flat[0]["slug"] if flat else (WIKI_BOOK_HOME_SLUG if readme.exists() else "")
    return {
        "book": {
            "title": book_title,
            "slug": WIKI_BOOK_HOME_SLUG,
            "url": wiki_page_url(WIKI_BOOK_HOME_SLUG),
            "raw_url": wiki_raw_url(WIKI_BOOK_README_NAME),
            "available": True,
        },
        "default_page_slug": default_page_slug,
        "tree": tree,
        "flat": flat,
        "pages": pages,
        "breadcrumbs": breadcrumbs,
    }



def resolve_wiki_page_source(repo_dir: Path, page_slug: str, pages: dict[str, dict[str, Any]]) -> Path | None:
    normalized = str(page_slug or "").strip().strip("/") or WIKI_BOOK_HOME_SLUG
    if normalized == WIKI_BOOK_HOME_SLUG:
        source = wiki_readme_path(repo_dir)
        return source if source.exists() else None
    page_meta = pages.get(normalized)
    if page_meta:
        source = safe_wiki_path(repo_dir, page_meta["source_path"])
        return source if source and source.exists() else None
    candidate = safe_wiki_path(wiki_pages_dir(repo_dir), f"{normalized}.md")
    return candidate if candidate and candidate.exists() else None



def read_wiki_page(page_slug: str | None = None, repo_dir: Path = WIKI_BOOK_DIR) -> dict[str, Any]:
    repo = wiki_book_dir(repo_dir)
    index = read_wiki_index(repo)
    slug = str(page_slug or index["default_page_slug"] or WIKI_BOOK_HOME_SLUG).strip().strip("/") or WIKI_BOOK_HOME_SLUG
    source_path = resolve_wiki_page_source(repo, slug, index["pages"])
    if not source_path:
        raise FileNotFoundError(f"Wiki page not found: {slug}")
    markdown_text = source_path.read_text(encoding="utf-8")
    source_relative = str(source_path.relative_to(repo)).replace(os.sep, "/")
    page_meta = index["pages"].get(slug, {})
    title = page_meta.get("title") or extract_markdown_title(markdown_text, source_path.stem)
    return {
        "slug": slug,
        "title": title,
        "source_path": source_relative,
        "raw_url": wiki_raw_url(source_relative),
        "url": wiki_page_url(slug),
        "breadcrumbs": index["breadcrumbs"].get(slug, [{"title": title, "slug": slug, "url": wiki_page_url(slug)}]),
        "html": render_markdown_page(markdown_text, repo, source_path),
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/wiki")
def wiki_shell() -> FileResponse:
    return FileResponse(STATIC_DIR / "wiki.html")


@app.get("/wiki/page/{page_slug:path}")
def wiki_page_shell(page_slug: str) -> FileResponse:
    del page_slug
    return FileResponse(STATIC_DIR / "wiki.html")


@app.get("/api/wiki/index")
def api_wiki_index() -> dict[str, Any]:
    try:
        return read_wiki_index(WIKI_BOOK_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/wiki/page/{page_slug:path}")
def api_wiki_page(page_slug: str) -> dict[str, Any]:
    try:
        return read_wiki_page(page_slug, WIKI_BOOK_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/wiki/raw/{relative_path:path}")
def api_wiki_raw(relative_path: str) -> FileResponse:
    try:
        repo = wiki_book_dir(WIKI_BOOK_DIR)
        target = safe_wiki_path(repo, relative_path)
        if not target or not target.exists() or not target.is_file():
            raise FileNotFoundError(f"Wiki file not found: {relative_path}")
        return FileResponse(target)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc



@app.get("/api/cards")
def api_cards() -> dict[str, Any]:
    try:
        rows, _ = read_cards(CSV_PATH, PROGRESS_DB_PATH)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"cards": rows, "summary": summarize(rows)}


@app.post("/api/cards/{card_id}/mark")
def api_mark(card_id: str, payload: MarkRequest) -> dict[str, Any]:
    try:
        card = mark_card(card_id, payload.known_status, CSV_PATH, BACKUP_DIR, PROGRESS_DB_PATH)
        rows, _ = read_cards(CSV_PATH, PROGRESS_DB_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"card": card, "summary": summarize(rows)}


@app.post("/api/cards/{card_id}/bookmark")
def api_bookmark(card_id: str, payload: BookmarkRequest) -> dict[str, Any]:
    try:
        card = set_bookmark(card_id, payload.bookmarked, CSV_PATH, PROGRESS_DB_PATH)
        rows, _ = read_cards(CSV_PATH, PROGRESS_DB_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"card": card, "summary": summarize(rows)}


@app.post("/api/cards/{card_id}/memo")
def api_memo(card_id: str, payload: MemoRequest) -> dict[str, Any]:
    try:
        card = save_memo(card_id, payload.memo, CSV_PATH, PROGRESS_DB_PATH)
        rows, _ = read_cards(CSV_PATH, PROGRESS_DB_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"card": card, "summary": summarize(rows)}


@app.post("/api/questions/generate")
def api_generate_questions(payload: QuestionGenerateRequest) -> dict[str, Any]:
    try:
        rows, _ = read_cards(CSV_PATH, PROGRESS_DB_PATH)
        return generate_questions(
            rows,
            card_ids=payload.card_ids,
            types=payload.types,
            count=payload.count,
            seed=payload.seed,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/questions/types")
def api_question_types() -> dict[str, Any]:
    return {
        "types": [
            {"value": "short", "label": "주관식"},
            {"value": "subjective", "label": "서술형"},
            {"value": "multiple_choice", "label": "객관식"},
            {"value": "essay", "label": "논술형"},
        ],
        "supported": list(SUPPORTED_QUESTION_TYPES),
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "csv_path": str(CSV_PATH),
        "csv_exists": CSV_PATH.exists(),
        "progress_db_path": str(PROGRESS_DB_PATH),
        "progress_db_exists": PROGRESS_DB_PATH.exists(),
        "wiki_book_dir": str(WIKI_BOOK_DIR),
        "wiki_book_exists": WIKI_BOOK_DIR.exists(),
    }
