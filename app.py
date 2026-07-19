from __future__ import annotations

import base64
import csv
import html
import hashlib
import json

from contextlib import closing
import hmac
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request as UrlRequest, urlopen
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from question_generator import SUPPORTED_QUESTION_TYPES, generate_questions, normalize_card_ids

ROOT = Path(__file__).resolve().parent
DEFAULT_CSV_PATH = ROOT / "data" / "CS_encyclopedia_300plus.csv"
DEFAULT_PROGRESS_DB_PATH = ROOT / "state" / "progress.sqlite"
CSV_PATH = Path(os.environ.get("CS_FLASHCARD_CSV", DEFAULT_CSV_PATH)).expanduser().resolve()
PROGRESS_DB_PATH = Path(os.environ.get("CS_FLASHCARD_PROGRESS_DB", DEFAULT_PROGRESS_DB_PATH)).expanduser().resolve()
BACKUP_DIR = Path(os.environ.get("CS_FLASHCARD_BACKUP_DIR", ROOT / "backups")).expanduser().resolve()
STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_WIKI_BOOK_DIR = ROOT / "wiki_book"
LEGACY_WIKI_BOOK_DIR = ROOT.parent / "wikidocs-ebook"
WIKI_BOOK_DIR = Path(os.environ.get("CS_FLASHCARDS_WIKI_BOOK_DIR", DEFAULT_WIKI_BOOK_DIR)).expanduser().resolve()
WIKI_PAGES_DIRNAME = "pages"
WIKI_TOC_NAME = "TOC.md"
WIKI_BOOK_README_NAME = "README.md"
WIKI_BOOK_HOME_SLUG = "_book"
REVIEW_COLUMNS = ["known_status", "last_reviewed", "review_count"]
VALID_STATUSES = {"O", "X", ""}
QUESTION_ATTEMPT_RESULT_VALUES = {"all", "correct", "wrong", "pending", "ambiguous", "unknown"}
QUESTION_ATTEMPT_JUDGMENT_VALUES = {"correct", "ambiguous", "wrong", "unknown", "pending"}
QUESTION_ATTEMPT_JUDGMENT_LABELS = {
    "correct": "맞음",
    "ambiguous": "애매함",
    "wrong": "틀림",
    "unknown": "모름",
    "pending": "미채점",
}

PUBLIC_USERNAME = os.environ.get("CS_FLASHCARDS_USERNAME", "cs")
PUBLIC_PASSWORD = os.environ.get("CS_FLASHCARDS_PASSWORD", "")
AUTH_COOKIE_NAME = "cs_flashcards_auth"
WIKI_GITHUB_REPO = str(os.environ.get("CS_FLASHCARDS_WIKI_GITHUB_REPO", "")).strip()
WIKI_GITHUB_BRANCH = str(os.environ.get("CS_FLASHCARDS_WIKI_GITHUB_BRANCH", "main")).strip() or "main"
WIKI_GITHUB_TOKEN = str(os.environ.get("CS_FLASHCARDS_WIKI_GITHUB_TOKEN", "")).strip()
WIKI_GITHUB_PATH_PREFIX = str(os.environ.get("CS_FLASHCARDS_WIKI_GITHUB_PATH_PREFIX", "")).strip().strip("/")
WIKI_GITHUB_API_BASE = str(os.environ.get("CS_FLASHCARDS_WIKI_GITHUB_API_BASE", "https://api.github.com")).rstrip("/")
CARD_AI_EDITABLE_FIELDS = ("definition", "detailed_explanation", "exam_note", "concept_image_alt")
AI_PROGRESS_FIELDS = ("definition", "detailed_explanation", "exam_note", "concept_image_url", "concept_image_alt")
OPENAI_API_KEY = str(os.environ.get("OPENAI_API_KEY") or os.environ.get("CS_FLASHCARDS_OPENAI_API_KEY") or "").strip()
OPENAI_API_BASE = str(os.environ.get("CS_FLASHCARDS_OPENAI_API_BASE", "https://api.openai.com/v1")).rstrip("/")
CODEX_MODEL = str(os.environ.get("CS_FLASHCARDS_CODEX_MODEL", "codex-mini-latest")).strip() or "codex-mini-latest"
IMAGE_MODEL = str(os.environ.get("CS_FLASHCARDS_IMAGE_MODEL", "gpt-image-2")).strip() or "gpt-image-2"
IMAGE_SIZE = str(os.environ.get("CS_FLASHCARDS_IMAGE_SIZE", "1024x1024")).strip() or "1024x1024"
IMAGE_QUALITY = str(os.environ.get("CS_FLASHCARDS_IMAGE_QUALITY", "low")).strip() or "low"
AI_IMAGE_DIR = Path(os.environ.get("CS_FLASHCARDS_AI_IMAGE_DIR", ROOT / "state" / "ai_images")).expanduser().resolve()
AI_IMAGE_PREVIEW_DIR = Path(os.environ.get("CS_FLASHCARDS_AI_IMAGE_PREVIEW_DIR", ROOT / "state" / "ai_image_previews")).expanduser().resolve()





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

class QuestionAttemptRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=255)
    card_id: str = Field(min_length=1, max_length=255)
    question_type: str = Field(min_length=1, max_length=64)
    prompt: str = Field(default="", max_length=4000)
    body: str = Field(default="", max_length=12000)
    user_answer: str = Field(default="", max_length=20000)
    selected_choice_index: int | None = Field(default=None, ge=0, le=100)
    is_correct: bool | None = None
    judgment: str = Field(default="pending", max_length=32)
    wrong_note: str = Field(default="", max_length=20000)
    session_id: str = Field(default="", max_length=255)
    session_title: str = Field(default="", max_length=255)
    question_order: int | None = Field(default=None, ge=1, le=1000)
    question_elapsed_seconds: int | None = Field(default=None, ge=0, le=86400)
    session_elapsed_seconds: int | None = Field(default=None, ge=0, le=86400)
    time_limit_seconds: int | None = Field(default=None, ge=0, le=86400)
    question_started_at: str = Field(default="", max_length=64)
    answered_at: str = Field(default="", max_length=64)


class WikiChecklistRequest(BaseModel):
    source_path: str = Field(min_length=1, max_length=4096)
    line_number: int = Field(ge=1, le=200000)
    checked: bool
class CardAiRewriteRequest(BaseModel):
    instruction: str = Field(default="", max_length=4000)


class CardAiApplyRequest(BaseModel):
    definition: str | None = Field(default=None, max_length=12000)
    detailed_explanation: str | None = Field(default=None, max_length=50000)
    exam_note: str | None = Field(default=None, max_length=20000)
    concept_image_alt: str | None = Field(default=None, max_length=4000)


class CardAiImageApplyRequest(BaseModel):
    preview_name: str = Field(min_length=5, max_length=255)






def authorized_cookie_value() -> str:
    seed = f"{PUBLIC_USERNAME}:{PUBLIC_PASSWORD}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()



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



def is_authorized_cookie(cookie_value: str | None) -> bool:
    if not PUBLIC_PASSWORD:
        return True
    return bool(cookie_value) and hmac.compare_digest(cookie_value, authorized_cookie_value())



def is_authorized_request(authorization: str | None, cookie_value: str | None) -> bool:
    return is_authorized(authorization) or is_authorized_cookie(cookie_value)



@app.middleware("http")
async def optional_basic_auth(request: Request, call_next):
    authorization = request.headers.get("authorization")
    cookie_value = request.cookies.get(AUTH_COOKIE_NAME)
    if is_authorized_request(authorization, cookie_value):
        response = await call_next(request)
        if PUBLIC_PASSWORD and is_authorized(authorization) and not is_authorized_cookie(cookie_value):
            response.set_cookie(
                AUTH_COOKIE_NAME,
                authorized_cookie_value(),
                httponly=True,
                secure=request.url.scheme == "https",
                samesite="lax",
                max_age=60 * 60 * 24 * 30,
            )
        return response
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
                definition TEXT NOT NULL DEFAULT '',
                detailed_explanation TEXT NOT NULL DEFAULT '',
                exam_note TEXT NOT NULL DEFAULT '',
                concept_image_url TEXT NOT NULL DEFAULT '',
                concept_image_alt TEXT NOT NULL DEFAULT '',
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
        for field in AI_PROGRESS_FIELDS:
            if field not in columns:
                conn.execute(f"ALTER TABLE card_progress ADD COLUMN {field} TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_card_progress_status ON card_progress(known_status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_card_progress_bookmarked ON card_progress(bookmarked)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS question_attempts (
                question_id TEXT PRIMARY KEY,
                card_id TEXT NOT NULL,
                question_type TEXT NOT NULL,
                prompt TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                user_answer TEXT NOT NULL DEFAULT '',
                selected_choice_index INTEGER,
                is_correct INTEGER,
                judgment TEXT NOT NULL DEFAULT 'pending',
                wrong_note TEXT NOT NULL DEFAULT '',
                session_id TEXT NOT NULL DEFAULT '',
                session_title TEXT NOT NULL DEFAULT '',
                question_order INTEGER,
                question_elapsed_seconds INTEGER,
                session_elapsed_seconds INTEGER,
                time_limit_seconds INTEGER,
                question_started_at TEXT NOT NULL DEFAULT '',
                answered_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(card_id) REFERENCES card_progress(card_id) ON DELETE CASCADE
            )
            """
        )
        question_columns = {row["name"] for row in conn.execute("PRAGMA table_info(question_attempts)").fetchall()}
        question_column_definitions = {
            "judgment": "TEXT NOT NULL DEFAULT 'pending'",
            "session_id": "TEXT NOT NULL DEFAULT ''",
            "session_title": "TEXT NOT NULL DEFAULT ''",
            "question_order": "INTEGER",
            "question_elapsed_seconds": "INTEGER",
            "session_elapsed_seconds": "INTEGER",
            "time_limit_seconds": "INTEGER",
            "question_started_at": "TEXT NOT NULL DEFAULT ''",
            "answered_at": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in question_column_definitions.items():
            if column not in question_columns:
                conn.execute(f"ALTER TABLE question_attempts ADD COLUMN {column} {definition}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_question_attempts_card_id ON question_attempts(card_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_question_attempts_result ON question_attempts(is_correct)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_question_attempts_session_id ON question_attempts(session_id)")

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
    select_fields = ["card_id", "known_status", "last_reviewed", "review_count", "bookmarked", "memo", "memo_updated_at", *AI_PROGRESS_FIELDS]
    with closing(connect_progress_db(progress_db_path)) as conn:
        rows = conn.execute(f"SELECT {', '.join(select_fields)} FROM card_progress").fetchall()
    progress: dict[str, dict[str, str]] = {}
    for row in rows:
        item = {
            "known_status": row["known_status"] if row["known_status"] in VALID_STATUSES else "",
            "last_reviewed": row["last_reviewed"] or "",
            "review_count": normalized_review_count(str(row["review_count"])),
            "bookmarked": normalized_bookmarked(row["bookmarked"]),
            "memo": row["memo"] or "",
            "memo_updated_at": row["memo_updated_at"] or "",
        }
        for field in AI_PROGRESS_FIELDS:
            value = str(row[field] or "").strip()
            if value:
                item[field] = value
        progress[row["card_id"]] = item
    return progress


def merge_progress(
    rows: list[dict[str, str]],
    progress: dict[str, dict[str, str]],
    question_stats: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    question_stats = question_stats or {}
    for row in rows:
        item = dict(row)
        item.setdefault("bookmarked", "0")
        item.setdefault("memo", "")
        item.setdefault("memo_updated_at", "")
        item.setdefault("question_attempt_count", 0)
        item.setdefault("question_correct_count", 0)
        item.setdefault("question_wrong_count", 0)
        item.setdefault("latest_wrong_note", "")
        item.setdefault("latest_wrong_note_updated_at", "")
        item.update(progress.get(row.get("id", ""), {}))
        item.update(question_stats.get(row.get("id", ""), {}))
        item["bookmarked"] = normalized_bookmarked(item.get("bookmarked"))
        item["memo"] = item.get("memo") or ""
        item["memo_updated_at"] = item.get("memo_updated_at") or ""
        item["question_attempt_count"] = int(item.get("question_attempt_count") or 0)
        item["question_correct_count"] = int(item.get("question_correct_count") or 0)
        item["question_wrong_count"] = int(item.get("question_wrong_count") or 0)
        item["latest_wrong_note"] = item.get("latest_wrong_note") or ""
        item["latest_wrong_note_updated_at"] = item.get("latest_wrong_note_updated_at") or ""
        merged.append(item)
    return merged


def read_cards(csv_path: Path = CSV_PATH, progress_db_path: Path | None = None) -> tuple[list[dict[str, str]], list[str]]:
    raw_rows, fieldnames = read_csv_cards(csv_path, keep_csv_progress=True)
    clean_rows, _ = read_csv_cards(csv_path, keep_csv_progress=False)
    db_path = progress_db_for(csv_path, progress_db_path)
    ensure_progress_db(db_path, raw_rows)
    rows = merge_progress(clean_rows, read_progress(db_path), read_question_attempt_stats(db_path))
    return rows, fieldnames


def save_card_progress_overrides(
    card_id: str,
    updates: dict[str, str],
    progress_db_path: Path,
) -> bool:
    effective_updates = {
        field: normalized_card_text(value, limit=AI_PROGRESS_FIELD_LIMITS[field])
        for field, value in updates.items()
        if field in AI_PROGRESS_FIELDS and value is not None
    }
    if not effective_updates:
        return False
    ensure_progress_db(progress_db_path)
    now = utc_now_iso()
    assignments = ", ".join(f"{field}=?" for field in effective_updates)
    values = list(effective_updates.values())
    with closing(connect_progress_db(progress_db_path)) as conn:
        conn.execute(
            """
            INSERT INTO card_progress (card_id, updated_at)
            VALUES (?, ?)
            ON CONFLICT(card_id) DO NOTHING
            """,
            (card_id, now),
        )
        before = conn.execute(
            f"SELECT {', '.join(effective_updates.keys())} FROM card_progress WHERE card_id=?",
            (card_id,),
        ).fetchone()
        changed = any(str((before[field] if before else "") or "") != value for field, value in effective_updates.items())
        if changed:
            conn.execute(
                f"UPDATE card_progress SET {assignments}, updated_at=? WHERE card_id=?",
                [*values, now, card_id],
            )
            conn.commit()
    return changed


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
AI_REWRITE_FIELD_LIMITS = {
    "definition": 12000,
    "detailed_explanation": 50000,
    "exam_note": 20000,
    "concept_image_alt": 4000,
}
AI_PROGRESS_FIELD_LIMITS = {
    **AI_REWRITE_FIELD_LIMITS,
    "concept_image_url": 4096,
}


def normalized_card_text(value: Any, *, limit: int) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return text[:limit]


def extract_json_object_text(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("AI 응답에서 JSON 객체를 찾지 못했습니다.")
    return text[start : end + 1]


def response_output_text(payload: dict[str, Any]) -> str:
    top_level = str(payload.get("output_text") or "").strip()
    if top_level:
        return top_level
    parts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text_value = content.get("text")
            if isinstance(text_value, str) and text_value.strip():
                parts.append(text_value)
    combined = "\n".join(part for part in parts if part).strip()
    if combined:
        return combined
    raise ValueError("AI 응답에서 텍스트를 찾지 못했습니다.")


def openai_error_message(raw: str, fallback: str) -> str:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip() or fallback
    error = payload.get("error") if isinstance(payload, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    return str(message or raw or fallback).strip()


def rewrite_card_with_codex(card: dict[str, str], instruction: str = "") -> dict[str, str]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않아 Codex AI 초안을 만들 수 없습니다.")
    payload = {
        "model": CODEX_MODEL,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You rewrite Korean CS flashcard content. Return only one JSON object with the keys "
                            "definition, detailed_explanation, exam_note, concept_image_alt. Keep facts grounded in the "
                            "provided card. Do not invent source files, links, or citations. definition should be 1-2 "
                            "sentences. detailed_explanation must stay in Korean and include both '의미:' and '활용:' "
                            "sections. exam_note should be concise interview/exam guidance. concept_image_alt should be a "
                            "short Korean alt text only, not a URL."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            {
                                "instruction": str(instruction or "").strip() or "현재 카드 내용을 더 명확하고 학습 친화적으로 다듬어 주세요.",
                                "card": {
                                    "id": card.get("id", ""),
                                    "term": card.get("term", ""),
                                    "english": card.get("english", ""),
                                    "category": card.get("category", ""),
                                    "definition": card.get("definition", ""),
                                    "detailed_explanation": card.get("detailed_explanation", ""),
                                    "related_concepts": card.get("related_concepts", ""),
                                    "exam_note": card.get("exam_note", ""),
                                    "bok_appeared": card.get("bok_appeared", ""),
                                    "importance": card.get("importance", ""),
                                    "difficulty": card.get("difficulty", ""),
                                    "concept_image_alt": card.get("concept_image_alt", ""),
                                },
                            },
                            ensure_ascii=False,
                        ),
                    }
                ],
            },
        ],
    }
    request = UrlRequest(
        f"{OPENAI_API_BASE}/responses",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(openai_error_message(raw, f"OpenAI API 오류 ({exc.code})")) from exc
    except URLError as exc:
        raise RuntimeError(f"OpenAI API 연결 실패: {exc.reason}") from exc
    try:
        parsed_response = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI API 응답을 JSON으로 해석하지 못했습니다.") from exc
    raw_text = response_output_text(parsed_response)
    try:
        parsed = json.loads(extract_json_object_text(raw_text))
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("Codex 응답을 카드 초안 JSON으로 해석하지 못했습니다.") from exc
    rewritten: dict[str, str] = {}
    for field in CARD_AI_EDITABLE_FIELDS:
        rewritten[field] = normalized_card_text(
            parsed.get(field, card.get(field, "")),
            limit=AI_REWRITE_FIELD_LIMITS[field],
        )
    return rewritten


def update_card_ai_content(
    card_id: str,
    payload: CardAiApplyRequest,
    csv_path: Path = CSV_PATH,
    backup_dir: Path = BACKUP_DIR,
    progress_db_path: Path | None = None,
) -> tuple[dict[str, str], Path | None]:
    del backup_dir
    db_path = progress_db_for(csv_path, progress_db_path)
    rows, _ = read_cards(csv_path, db_path)
    target = next((row for row in rows if row.get("id") == card_id), None)
    if target is None:
        raise KeyError(card_id)
    updates = {
        "definition": payload.definition,
        "detailed_explanation": payload.detailed_explanation,
        "exam_note": payload.exam_note,
        "concept_image_alt": payload.concept_image_alt,
    }
    changed_updates: dict[str, str] = {}
    for field, value in updates.items():
        if value is None:
            continue
        normalized = normalized_card_text(value, limit=AI_REWRITE_FIELD_LIMITS[field])
        if str(target.get(field, "")) != normalized:
            changed_updates[field] = normalized
    save_card_progress_overrides(card_id, changed_updates, db_path)
    updated_rows, _ = read_cards(csv_path, db_path)
    for row in updated_rows:
        if row.get("id") == card_id:
            return row, None
    raise KeyError(card_id)
AI_IMAGE_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{3,254}$")


def concept_image_alt_text(card: dict[str, str]) -> str:
    explicit = str(card.get("concept_image_alt") or card.get("image_alt") or "").strip()
    if explicit:
        return explicit[:4000]
    term = str(card.get("term") or card.get("english") or "개념").strip() or "개념"
    category = str(card.get("category") or "").strip()
    suffix = f"({category})" if category else ""
    return f"{term}{suffix} 이해를 돕는 AI 생성 개념 이미지"[:4000]


def concept_image_prompt(card: dict[str, str]) -> str:
    term = str(card.get("term") or "").strip() or "개념"
    english = str(card.get("english") or "").strip()
    category = str(card.get("category") or "").strip() or "CS"
    definition = normalized_card_text(card.get("definition", ""), limit=800)
    detail = normalized_card_text(card.get("detailed_explanation", ""), limit=1800)
    related = normalized_card_text(card.get("related_concepts", ""), limit=400)
    return (
        "Create a clean, minimal educational concept illustration for a Korean CS flashcard. "
        "No text, no letters, no labels, no UI, no watermark, no logo, no border, no collage. "
        "Use a simple single-scene composition with soft modern colors and high clarity. "
        f"Subject: {term}. "
        f"English term: {english or term}. "
        f"Category: {category}. "
        f"Definition: {definition}. "
        f"Detailed explanation: {detail}. "
        f"Related concepts: {related}. "
        "Visualize the core mechanism or mental model of the concept so a learner can understand it at a glance. "
        "Prefer a neutral academic diagram-like illustration, but rendered as a polished image rather than literal text diagram."
    )


def ensure_ai_image_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def validated_ai_image_name(value: str) -> str:
    name = str(value or "").strip()
    if not AI_IMAGE_FILENAME_RE.fullmatch(name):
        raise ValueError("잘못된 이미지 이름입니다.")
    return name


def ai_image_file_path(directory: Path, name: str) -> Path:
    normalized = validated_ai_image_name(name)
    base = ensure_ai_image_dir(directory).resolve()
    candidate = (base / normalized).resolve()
    if candidate.parent != base:
        raise ValueError("잘못된 이미지 경로입니다.")
    return candidate


def image_generation_result_bytes(payload: dict[str, Any]) -> bytes:
    items = payload.get("data") or []
    if not items:
        raise ValueError("이미지 생성 응답이 비어 있습니다.")
    first = items[0] if isinstance(items[0], dict) else {}
    b64_json = first.get("b64_json")
    if isinstance(b64_json, str) and b64_json.strip():
        try:
            return base64.b64decode(b64_json)
        except ValueError as exc:
            raise ValueError("이미지 base64 응답을 해석하지 못했습니다.") from exc
    image_url = first.get("url")
    if isinstance(image_url, str) and image_url.strip():
        try:
            with urlopen(image_url, timeout=120) as response:
                return response.read()
        except URLError as exc:
            raise RuntimeError(f"생성된 이미지 다운로드 실패: {exc.reason}") from exc
    raise ValueError("이미지 생성 응답에서 결과 이미지를 찾지 못했습니다.")


def generate_ai_concept_image_preview(
    card: dict[str, str],
    *,
    preview_dir: Path = AI_IMAGE_PREVIEW_DIR,
) -> dict[str, str]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않아 AI 이미지 초안을 만들 수 없습니다.")
    payload = {
        "model": IMAGE_MODEL,
        "prompt": concept_image_prompt(card),
        "size": IMAGE_SIZE,
        "quality": IMAGE_QUALITY,
    }
    request = UrlRequest(
        f"{OPENAI_API_BASE}/images/generations",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=180) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(openai_error_message(raw, f"OpenAI 이미지 API 오류 ({exc.code})")) from exc
    except URLError as exc:
        raise RuntimeError(f"OpenAI 이미지 API 연결 실패: {exc.reason}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI 이미지 API 응답을 JSON으로 해석하지 못했습니다.") from exc
    image_bytes = image_generation_result_bytes(parsed)
    preview_root = ensure_ai_image_dir(preview_dir)
    token = uuid4().hex
    preview_name = f"{token}.png"
    preview_path = ai_image_file_path(preview_root, preview_name)
    preview_path.write_bytes(image_bytes)
    preview_meta = {
        "card_id": str(card.get("id") or "").strip(),
        "alt": concept_image_alt_text(card),
        "created_at": utc_now_iso(),
        "model": IMAGE_MODEL,
        "size": IMAGE_SIZE,
        "quality": IMAGE_QUALITY,
    }
    preview_path.with_suffix(".json").write_text(json.dumps(preview_meta, ensure_ascii=False), encoding="utf-8")
    return {
        "preview_name": preview_name,
        "preview_url": f"/api/ai-image-previews/{quote(preview_name, safe='.-_')}",
        "alt": preview_meta["alt"],
        "model": IMAGE_MODEL,
    }


def read_ai_image_preview(preview_name: str, *, preview_dir: Path = AI_IMAGE_PREVIEW_DIR) -> tuple[Path, dict[str, Any]]:
    preview_path = ai_image_file_path(preview_dir, preview_name)
    meta_path = preview_path.with_suffix(".json")
    if not preview_path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"AI 이미지 미리보기를 찾지 못했습니다: {preview_name}")
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("AI 이미지 미리보기 메타데이터를 읽지 못했습니다.") from exc
    return preview_path, metadata if isinstance(metadata, dict) else {}


def apply_ai_concept_image(
    card_id: str,
    payload: CardAiImageApplyRequest,
    csv_path: Path = CSV_PATH,
    backup_dir: Path = BACKUP_DIR,
    progress_db_path: Path | None = None,
    image_dir: Path = AI_IMAGE_DIR,
    preview_dir: Path = AI_IMAGE_PREVIEW_DIR,
) -> tuple[dict[str, str], Path | None, str]:
    del backup_dir
    db_path = progress_db_for(csv_path, progress_db_path)
    rows, _ = read_cards(csv_path, db_path)
    target = next((row for row in rows if row.get("id") == card_id), None)
    if target is None:
        raise KeyError(card_id)
    preview_path, metadata = read_ai_image_preview(payload.preview_name, preview_dir=preview_dir)
    if str(metadata.get("card_id") or "").strip() != card_id:
        raise ValueError("다른 카드용 AI 이미지 미리보기입니다.")
    image_root = ensure_ai_image_dir(image_dir)
    safe_card_id = re.sub(r"[^A-Za-z0-9_-]+", "-", card_id).strip("-") or "card"
    final_name = f"{safe_card_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}.png"
    final_path = ai_image_file_path(image_root, final_name)
    shutil.copy2(preview_path, final_path)
    next_url = f"/api/ai-images/{final_name}"
    next_alt = normalized_card_text(metadata.get("alt", concept_image_alt_text(target)), limit=4000)
    save_card_progress_overrides(
        card_id,
        {"concept_image_url": next_url, "concept_image_alt": next_alt},
        db_path,
    )
    try:
        preview_path.unlink(missing_ok=True)
        preview_path.with_suffix(".json").unlink(missing_ok=True)
    except TypeError:
        if preview_path.exists():
            preview_path.unlink()
        meta_path = preview_path.with_suffix(".json")
        if meta_path.exists():
            meta_path.unlink()
    updated_rows, _ = read_cards(csv_path, db_path)
    for row in updated_rows:
        if row.get("id") == card_id:
            return row, None, next_url
    raise KeyError(card_id)


def discard_ai_concept_image_preview(
    card_id: str,
    payload: CardAiImageApplyRequest,
    *,
    preview_dir: Path = AI_IMAGE_PREVIEW_DIR,
) -> None:
    preview_path, metadata = read_ai_image_preview(payload.preview_name, preview_dir=preview_dir)
    if str(metadata.get("card_id") or "").strip() != card_id:
        raise ValueError("다른 카드용 AI 이미지 미리보기입니다.")
    try:
        preview_path.unlink(missing_ok=True)
        preview_path.with_suffix(".json").unlink(missing_ok=True)
    except TypeError:
        if preview_path.exists():
            preview_path.unlink()
        meta_path = preview_path.with_suffix(".json")
        if meta_path.exists():
            meta_path.unlink()






def resolved_question_attempt_judgment(value: str | None, is_correct: bool | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in QUESTION_ATTEMPT_JUDGMENT_VALUES:
        return normalized
    if is_correct is True:
        return "correct"
    if is_correct is False:
        return "wrong"
    return "pending"


def normalize_question_attempt_judgment(value: str | None, is_correct: bool | None = None) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "": "pending",
        "pending": "pending",
        "ungraded": "pending",
        "미채점": "pending",
        "correct": "correct",
        "right": "correct",
        "맞음": "correct",
        "정답": "correct",
        "ambiguous": "ambiguous",
        "uncertain": "ambiguous",
        "애매": "ambiguous",
        "애매함": "ambiguous",
        "wrong": "wrong",
        "incorrect": "wrong",
        "틀림": "wrong",
        "오답": "wrong",
        "unknown": "unknown",
        "dont_know": "unknown",
        "don't know": "unknown",
        "모름": "unknown",
    }
    normalized = aliases.get(raw)
    if normalized is None:
        raise ValueError(f"Unsupported question attempt judgment: {value}")
    if normalized == "pending" and is_correct is True:
        return "correct"
    if normalized == "pending" and is_correct is False:
        return "wrong"
    return normalized


def question_attempt_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    raw_result = row["is_correct"]
    is_correct = None if raw_result is None else bool(int(raw_result))
    judgment = resolved_question_attempt_judgment(row["judgment"] if "judgment" in row.keys() else None, is_correct)
    return {
        "question_id": row["question_id"],
        "card_id": row["card_id"],
        "question_type": row["question_type"],
        "prompt": row["prompt"] or "",
        "body": row["body"] or "",
        "user_answer": row["user_answer"] or "",
        "selected_choice_index": row["selected_choice_index"],
        "is_correct": is_correct,
        "judgment": judgment,
        "judgment_label": QUESTION_ATTEMPT_JUDGMENT_LABELS.get(judgment, QUESTION_ATTEMPT_JUDGMENT_LABELS["pending"]),
        "wrong_note": row["wrong_note"] or "",
        "session_id": row["session_id"] if "session_id" in row.keys() else "",
        "session_title": row["session_title"] if "session_title" in row.keys() else "",
        "question_order": row["question_order"] if "question_order" in row.keys() else None,
        "question_elapsed_seconds": row["question_elapsed_seconds"] if "question_elapsed_seconds" in row.keys() else None,
        "session_elapsed_seconds": row["session_elapsed_seconds"] if "session_elapsed_seconds" in row.keys() else None,
        "time_limit_seconds": row["time_limit_seconds"] if "time_limit_seconds" in row.keys() else None,
        "question_started_at": row["question_started_at"] if "question_started_at" in row.keys() else "",
        "answered_at": row["answered_at"] if "answered_at" in row.keys() else "",
        "created_at": row["created_at"] or "",
        "updated_at": row["updated_at"] or "",
    }


def normalize_question_attempt_result(value: str | None) -> str:
    raw = str(value or "all").strip().lower()
    aliases = {
        "": "all",
        "all": "all",
        "전체": "all",
        "correct": "correct",
        "right": "correct",
        "맞음": "correct",
        "정답": "correct",
        "ambiguous": "ambiguous",
        "uncertain": "ambiguous",
        "애매": "ambiguous",
        "애매함": "ambiguous",
        "wrong": "wrong",
        "incorrect": "wrong",
        "틀림": "wrong",
        "오답": "wrong",
        "unknown": "unknown",
        "모름": "unknown",
        "pending": "pending",
        "ungraded": "pending",
        "미채점": "pending",
    }
    normalized = aliases.get(raw)
    if normalized not in QUESTION_ATTEMPT_RESULT_VALUES:
        raise ValueError(f"Unsupported question attempt result: {value}")
    return normalized


def read_question_attempts(
    csv_path: Path = CSV_PATH,
    progress_db_path: Path | None = None,
    *,
    card_ids: list[str] | None = None,
    result: str = "all",
    limit: int = 200,
) -> dict[str, Any]:
    normalized_result = normalize_question_attempt_result(result)
    selected_ids = sorted(normalize_card_ids(card_ids) or [])
    safe_limit = max(1, min(int(limit or 200), 500))
    rows, _ = read_cards(csv_path, progress_db_path)
    card_map = {str(row.get("id") or "").strip(): row for row in rows if str(row.get("id") or "").strip()}
    db_path = progress_db_for(csv_path, progress_db_path)
    ensure_progress_db(db_path)

    where_clauses: list[str] = []
    where_params: list[Any] = []
    if selected_ids:
        placeholders = ", ".join(["?"] * len(selected_ids))
        where_clauses.append(f"card_id IN ({placeholders})")
        where_params.extend(selected_ids)

    judgment_sql = "CASE WHEN TRIM(COALESCE(judgment, '')) <> '' THEN LOWER(TRIM(judgment)) WHEN is_correct = 1 THEN 'correct' WHEN is_correct = 0 THEN 'wrong' ELSE 'pending' END"
    base_where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    list_clauses = list(where_clauses)
    list_params = list(where_params)
    if normalized_result != "all":
        list_clauses.append(f"{judgment_sql} = ?")
        list_params.append(normalized_result)
    list_where = f"WHERE {' AND '.join(list_clauses)}" if list_clauses else ""

    with closing(connect_progress_db(db_path)) as conn:
        summary_row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total_count,
                SUM(CASE WHEN {judgment_sql} = 'correct' THEN 1 ELSE 0 END) AS correct_count,
                SUM(CASE WHEN {judgment_sql} = 'ambiguous' THEN 1 ELSE 0 END) AS ambiguous_count,
                SUM(CASE WHEN {judgment_sql} = 'wrong' THEN 1 ELSE 0 END) AS wrong_count,
                SUM(CASE WHEN {judgment_sql} = 'unknown' THEN 1 ELSE 0 END) AS unknown_count,
                SUM(CASE WHEN {judgment_sql} = 'pending' THEN 1 ELSE 0 END) AS pending_count
            FROM question_attempts
            {base_where}
            """,
            tuple(where_params),
        ).fetchone()
        attempt_rows = conn.execute(
            f"""
            SELECT question_id, card_id, question_type, prompt, body, user_answer,
                   selected_choice_index, is_correct, judgment, wrong_note, session_id,
                   session_title, question_order, question_elapsed_seconds,
                   session_elapsed_seconds, time_limit_seconds, question_started_at,
                   answered_at, created_at, updated_at
            FROM question_attempts
            {list_where}
            ORDER BY updated_at DESC, created_at DESC, question_id DESC
            LIMIT ?
            """,
            tuple(list_params + [safe_limit]),
        ).fetchall()

    items: list[dict[str, Any]] = []
    for row in attempt_rows:
        item = question_attempt_row_to_dict(row) or {}
        card = card_map.get(item.get("card_id", ""), {})
        item["term"] = card.get("term") or card.get("english") or item.get("card_id") or ""
        item["english"] = card.get("english") or ""
        item["category"] = card.get("category") or ""
        item["card_url"] = flashcard_card_url(item.get("card_id") or "")
        item["result_key"] = item.get("judgment") or "pending"
        item["result_label"] = QUESTION_ATTEMPT_JUDGMENT_LABELS.get(item["result_key"], QUESTION_ATTEMPT_JUDGMENT_LABELS["pending"])
        items.append(item)

    return {
        "items": items,
        "summary": {
            "filter": normalized_result,
            "total": int(summary_row["total_count"] or 0) if summary_row else 0,
            "correct": int(summary_row["correct_count"] or 0) if summary_row else 0,
            "ambiguous": int(summary_row["ambiguous_count"] or 0) if summary_row else 0,
            "wrong": int(summary_row["wrong_count"] or 0) if summary_row else 0,
            "unknown": int(summary_row["unknown_count"] or 0) if summary_row else 0,
            "pending": int(summary_row["pending_count"] or 0) if summary_row else 0,
            "selected_card_count": len(selected_ids) if selected_ids else len(rows),
            "returned": len(items),
        },
    }


def read_question_attempt_stats(progress_db_path: Path) -> dict[str, dict[str, Any]]:
    ensure_progress_db(progress_db_path)
    stats: dict[str, dict[str, Any]] = {}
    with closing(connect_progress_db(progress_db_path)) as conn:
        for row in conn.execute(
            """
            SELECT
                card_id,
                COUNT(*) AS question_attempt_count,
                SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS question_correct_count,
                SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) AS question_wrong_count
            FROM question_attempts
            GROUP BY card_id
            """
        ).fetchall():
            stats[row["card_id"]] = {
                "question_attempt_count": int(row["question_attempt_count"] or 0),
                "question_correct_count": int(row["question_correct_count"] or 0),
                "question_wrong_count": int(row["question_wrong_count"] or 0),
                "latest_wrong_note": "",
                "latest_wrong_note_updated_at": "",
            }
        seen_cards: set[str] = set()
        for row in conn.execute(
            """
            SELECT card_id, wrong_note, updated_at
            FROM question_attempts
            WHERE is_correct = 0 AND TRIM(wrong_note) <> ''
            ORDER BY updated_at DESC
            """
        ).fetchall():
            card_id = row["card_id"]
            if card_id in seen_cards:
                continue
            seen_cards.add(card_id)
            bucket = stats.setdefault(
                card_id,
                {
                    "question_attempt_count": 0,
                    "question_correct_count": 0,
                    "question_wrong_count": 0,
                    "latest_wrong_note": "",
                    "latest_wrong_note_updated_at": "",
                },
            )
            bucket["latest_wrong_note"] = row["wrong_note"] or ""
            bucket["latest_wrong_note_updated_at"] = row["updated_at"] or ""
    return stats


def save_question_attempt(
    payload: QuestionAttemptRequest,
    csv_path: Path = CSV_PATH,
    progress_db_path: Path | None = None,
) -> dict[str, Any]:
    _ensure_card_exists(payload.card_id, csv_path, progress_db_path)
    question_type = str(payload.question_type or "").strip().lower()
    if question_type not in SUPPORTED_QUESTION_TYPES:
        raise ValueError(f"Unsupported question type: {payload.question_type}")

    question_id = str(payload.question_id or "").strip()
    if not question_id:
        raise ValueError("question_id is required")

    judgment = normalize_question_attempt_judgment(payload.judgment, payload.is_correct)
    is_correct_value = 1 if judgment == "correct" else 0 if judgment in {"ambiguous", "wrong", "unknown"} else None
    wrong_note = str(payload.wrong_note or "")[:20000]
    if is_correct_value == 1:
        wrong_note = ""
    db_path = progress_db_for(csv_path, progress_db_path)
    ensure_progress_db(db_path)
    now = utc_now_iso()
    answered_at = str(payload.answered_at or now)[:64]
    question_started_at = str(payload.question_started_at or "")[:64]
    session_id = str(payload.session_id or "")[:255]
    session_title = str(payload.session_title or "")[:255]
    with closing(connect_progress_db(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO card_progress (card_id, known_status, last_reviewed, review_count, bookmarked, memo, memo_updated_at, updated_at)
            VALUES (?, '', '', 0, 0, '', '', ?)
            ON CONFLICT(card_id) DO NOTHING
            """,
            (payload.card_id, now),
        )
        existing = conn.execute(
            "SELECT created_at, question_started_at FROM question_attempts WHERE question_id = ?",
            (question_id,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO question_attempts (
                question_id, card_id, question_type, prompt, body,
                user_answer, selected_choice_index, is_correct, judgment, wrong_note,
                session_id, session_title, question_order, question_elapsed_seconds,
                session_elapsed_seconds, time_limit_seconds, question_started_at,
                answered_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(question_id) DO UPDATE SET
                card_id = excluded.card_id,
                question_type = excluded.question_type,
                prompt = excluded.prompt,
                body = excluded.body,
                user_answer = excluded.user_answer,
                selected_choice_index = excluded.selected_choice_index,
                is_correct = excluded.is_correct,
                judgment = excluded.judgment,
                wrong_note = excluded.wrong_note,
                session_id = excluded.session_id,
                session_title = excluded.session_title,
                question_order = excluded.question_order,
                question_elapsed_seconds = excluded.question_elapsed_seconds,
                session_elapsed_seconds = excluded.session_elapsed_seconds,
                time_limit_seconds = excluded.time_limit_seconds,
                question_started_at = excluded.question_started_at,
                answered_at = excluded.answered_at,
                updated_at = excluded.updated_at
            """,
            (
                question_id,
                payload.card_id,
                question_type,
                str(payload.prompt or "")[:4000],
                str(payload.body or "")[:12000],
                str(payload.user_answer or "")[:20000],
                payload.selected_choice_index,
                is_correct_value,
                judgment,
                wrong_note,
                session_id,
                session_title,
                payload.question_order,
                payload.question_elapsed_seconds,
                payload.session_elapsed_seconds,
                payload.time_limit_seconds,
                question_started_at or (existing["question_started_at"] if existing and existing["question_started_at"] else ""),
                answered_at,
                existing["created_at"] if existing else now,
                now,
            ),
        )
        conn.commit()
        saved = conn.execute(
            """
            SELECT question_id, card_id, question_type, prompt, body, user_answer,
                   selected_choice_index, is_correct, judgment, wrong_note, session_id,
                   session_title, question_order, question_elapsed_seconds,
                   session_elapsed_seconds, time_limit_seconds, question_started_at,
                   answered_at, created_at, updated_at
            FROM question_attempts
            WHERE question_id = ?
            """,
            (question_id,),
        ).fetchone()

    updated_rows, _ = read_cards(csv_path, db_path)
    updated_card = next((row for row in updated_rows if row.get("id") == payload.card_id), None)
    if updated_card is None:
        raise KeyError(payload.card_id)
    return {
        "attempt": question_attempt_row_to_dict(saved),
        "card": updated_card,
    }


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
WIKI_TASK_BODY_RE = re.compile(r"^\[(?P<checked>[ xX])\]\s+(?P<text>.*)$")
WIKI_TASK_LINE_RE = re.compile(r"^(?P<prefix>\s*(?:[-*+]|\d+\.)\s+)\[(?P<checked>[ xX])\](?P<suffix>\s+.*)$")
WIKI_CODE_FENCE_RE = re.compile(r"^```(?P<lang>[\w+-]*)\s*$")
WIKI_TABLE_SEPARATOR_RE = re.compile(r"^\|?\s*:?[-]{3,}:?(?:\s*\|\s*:?[-]{3,}:?)*\s*\|?$")
WIKI_INLINE_TOKEN_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)|\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*|\*([^*]+)\*")


def wiki_book_dir(repo_dir: Path | None = None) -> Path:
    if repo_dir is not None:
        resolved = Path(repo_dir).expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Wiki book directory not found: {resolved}")
        return resolved
    candidates = [
        WIKI_BOOK_DIR,
        LEGACY_WIKI_BOOK_DIR,
        ROOT / "wikidocs-ebook",
    ]
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = Path(candidate).expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            return resolved
    searched = ", ".join(str(Path(candidate).expanduser().resolve()) for candidate in candidates)
    raise FileNotFoundError(f"Wiki book directory not found. Checked: {searched}")


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


def parse_markdown_task_item(body: str) -> tuple[bool, str] | None:
    match = WIKI_TASK_BODY_RE.match(str(body or "").strip())
    if not match:
        return None
    return match.group("checked").lower() == "x", match.group("text").strip()


def set_markdown_task_state(markdown_text: str, line_number: int, checked: bool) -> tuple[str, dict[str, Any]]:
    lines = markdown_text.splitlines(keepends=True)
    if line_number < 1 or line_number > len(lines):
        raise ValueError(f"Checklist line not found: {line_number}")
    raw_line = lines[line_number - 1]
    line_body = raw_line.rstrip("\r\n")
    newline = raw_line[len(line_body):]
    match = WIKI_TASK_LINE_RE.match(line_body)
    if not match:
        raise ValueError(f"Line {line_number} is not a Markdown checklist item")
    updated_line = f"{match.group('prefix')}[{'x' if checked else ' '}]{match.group('suffix')}"
    lines[line_number - 1] = updated_line + newline
    return "".join(lines), {
        "checked": checked,
        "previous_checked": match.group("checked").lower() == "x",
        "text": match.group("suffix").strip(),
        "changed": updated_line != line_body,
    }


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


def render_markdown_list(lines: list[str], line_numbers: list[int], repo_dir: Path, current_source: Path) -> str:
    first_match = WIKI_LIST_RE.match(lines[0])
    tag = "ol" if first_match and first_match.group("marker").endswith(".") else "ul"
    source_relative = str(current_source.relative_to(repo_dir)).replace(os.sep, "/")
    items: list[str] = []
    is_task_list = True
    for line, line_number in zip(lines, line_numbers):
        match = WIKI_LIST_RE.match(line)
        if not match:
            continue
        task_item = parse_markdown_task_item(match.group("body"))
        if task_item:
            item_checked, item_text = task_item
            checked_attr = " checked" if item_checked else ""
            items.append(
                "<li class=\"wiki-task-item\"><label>"
                f"<input type=\"checkbox\" data-wiki-task-checkbox=\"1\" data-wiki-task-source=\"{html.escape(source_relative, quote=True)}\" data-wiki-task-line=\"{line_number}\"{checked_attr} />"
                f"<span>{render_inline_markdown(item_text, repo_dir, current_source)}</span>"
                "</label></li>"
            )
            continue
        is_task_list = False
        items.append(f"<li>{render_inline_markdown(match.group('body').strip(), repo_dir, current_source)}</li>")
    class_attr = ' class="wiki-task-list"' if items and is_task_list else ""
    return f"<{tag}{class_attr}>" + "".join(items) + f"</{tag}>"


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


def render_markdown_blocks(
    lines: list[str],
    repo_dir: Path,
    current_source: Path,
    line_numbers: list[int] | None = None,
) -> list[str]:
    effective_line_numbers = line_numbers or list(range(1, len(lines) + 1))
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
            quote_line_numbers: list[int] = []
            while index < len(lines) and lines[index].lstrip().startswith(">"):
                quote_lines.append(re.sub(r"^\s*>\s?", "", lines[index]))
                quote_line_numbers.append(effective_line_numbers[index])
                index += 1
            inner = "".join(render_markdown_blocks(quote_lines, repo_dir, current_source, quote_line_numbers))
            blocks.append(f"<blockquote>{inner}</blockquote>")
            continue
        if re.fullmatch(r"[-*_]{3,}", stripped):
            blocks.append("<hr />")
            index += 1
            continue
        if WIKI_LIST_RE.match(line):
            list_lines: list[str] = []
            list_line_numbers: list[int] = []
            while index < len(lines) and WIKI_LIST_RE.match(lines[index]):
                list_lines.append(lines[index])
                list_line_numbers.append(effective_line_numbers[index])
                index += 1
            blocks.append(render_markdown_list(list_lines, list_line_numbers, repo_dir, current_source))
            continue
        paragraph_lines = [stripped]
        index += 1
        while index < len(lines) and not is_markdown_block_start(lines[index]):
            paragraph_lines.append(lines[index].strip())
            index += 1
        blocks.append(f"<p>{render_inline_markdown(' '.join(paragraph_lines), repo_dir, current_source)}</p>")
    return blocks


def render_markdown_page(markdown_text: str, repo_dir: Path, current_source: Path) -> str:
    lines = markdown_text.splitlines()
    return "".join(render_markdown_blocks(lines, repo_dir, current_source, list(range(1, len(lines) + 1))))


def wiki_checklist_sync_target() -> str:
    return "github" if WIKI_GITHUB_REPO and WIKI_GITHUB_TOKEN else "local"


def wiki_github_repo_parts() -> tuple[str, str]:
    repo_slug = WIKI_GITHUB_REPO.strip().strip("/")
    if repo_slug.count("/") != 1:
        raise ValueError(f"Invalid GitHub repo slug: {WIKI_GITHUB_REPO}")
    owner, repo = repo_slug.split("/", 1)
    if not owner or not repo:
        raise ValueError(f"Invalid GitHub repo slug: {WIKI_GITHUB_REPO}")
    return owner, repo


def wiki_github_content_path(relative_path: str) -> str:
    normalized = PurePosixPath(str(relative_path or "").replace(os.sep, "/").lstrip("/"))
    if not normalized.parts or any(part in {"", ".", ".."} for part in normalized.parts):
        raise ValueError(f"Invalid GitHub wiki path: {relative_path}")
    repo_path = normalized.as_posix()
    if WIKI_GITHUB_PATH_PREFIX:
        repo_path = f"{WIKI_GITHUB_PATH_PREFIX}/{repo_path}"
    return repo_path


def wiki_github_contents_api_url(relative_path: str) -> str:
    owner, repo = wiki_github_repo_parts()
    content_path = wiki_github_content_path(relative_path)
    return f"{WIKI_GITHUB_API_BASE}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/contents/{quote(content_path, safe='/')}"


def wiki_github_api_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "cs-flashcards/wiki-checklist",
    }
    if WIKI_GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {WIKI_GITHUB_TOKEN}"
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = UrlRequest(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode(response.headers.get_content_charset() or "utf-8")
    except HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        message = raw_body or str(exc)
        try:
            parsed = json.loads(raw_body)
            message = str(parsed.get("message") or message)
        except json.JSONDecodeError:
            pass
        raise RuntimeError(f"GitHub API 요청 실패 ({exc.code}): {message}") from exc
    except URLError as exc:
        raise RuntimeError(f"GitHub API 연결 실패: {exc.reason}") from exc
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub API 응답을 해석하지 못했습니다.") from exc


def github_fetch_wiki_source(relative_path: str) -> tuple[str, str]:
    url = f"{wiki_github_contents_api_url(relative_path)}?ref={quote(WIKI_GITHUB_BRANCH, safe='')}"
    payload = wiki_github_api_json("GET", url)
    if str(payload.get("encoding") or "").lower() != "base64":
        raise RuntimeError(f"GitHub 파일 인코딩이 예상과 다릅니다: {relative_path}")
    sha = str(payload.get("sha") or "").strip()
    if not sha:
        raise RuntimeError(f"GitHub 파일 SHA를 찾지 못했습니다: {relative_path}")
    raw_content = str(payload.get("content") or "").replace("\n", "")
    decoded = base64.b64decode(raw_content.encode("ascii")).decode("utf-8")
    return decoded, sha


def github_update_wiki_source(relative_path: str, content: str, sha: str, message: str) -> dict[str, Any]:
    return wiki_github_api_json(
        "PUT",
        wiki_github_contents_api_url(relative_path),
        {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "sha": sha,
            "branch": WIKI_GITHUB_BRANCH,
        },
    )


def update_wiki_checklist_item(
    source_path: str,
    line_number: int,
    checked: bool,
    repo_dir: Path | None = None,
) -> dict[str, Any]:
    repo = wiki_book_dir(repo_dir)
    target = safe_wiki_path(repo, source_path)
    if not target or not target.exists() or not target.is_file():
        raise FileNotFoundError(f"Wiki file not found: {source_path}")
    if target.suffix.lower() != ".md":
        raise ValueError(f"Checklist updates support Markdown files only: {source_path}")
    source_relative = str(target.relative_to(repo)).replace(os.sep, "/")
    local_content = target.read_text(encoding="utf-8")
    sync_target = wiki_checklist_sync_target()
    if sync_target == "github":
        remote_content, remote_sha = github_fetch_wiki_source(source_relative)
        if remote_content != local_content:
            raise RuntimeError("GitHub 위키 원본과 현재 배포본이 달라 체크 동기화를 중단했습니다. 위키를 다시 배포한 뒤 재시도하세요.")
        updated_content, task_meta = set_markdown_task_state(remote_content, line_number, checked)
        if task_meta["changed"]:
            github_update_wiki_source(
                source_relative,
                updated_content,
                remote_sha,
                f"Toggle wiki checklist: {source_relative}#L{line_number}",
            )
    else:
        updated_content, task_meta = set_markdown_task_state(local_content, line_number, checked)
    if updated_content != local_content:
        target.write_text(updated_content, encoding="utf-8")
    return {
        "source_path": source_relative,
        "line_number": line_number,
        "page_slug": wiki_slug_for_source(repo, target),
        "sync_target": sync_target,
        **task_meta,
    }




def read_wiki_index(repo_dir: Path | None = None) -> dict[str, Any]:
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




def normalized_lookup_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def wiki_source_variants(value: str) -> set[str]:
    clean = str(value or "").strip().replace(os.sep, "/")
    clean = clean[2:] if clean.startswith("./") else clean
    if not clean:
        return set()
    variants = {clean}
    if clean.startswith("pages/"):
        variants.add(clean.removeprefix("pages/"))
    if clean.endswith(".md"):
        without_ext = clean.removesuffix(".md")
        variants.add(without_ext)
        if without_ext.startswith("pages/"):
            variants.add(without_ext.removeprefix("pages/"))
    return {item for item in variants if item}


def parse_card_source_files(value: Any) -> list[str]:
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def flashcard_card_url(card_id: str, *, side: str = "back") -> str:
    return "/?" + urlencode({"card": str(card_id or "").strip(), "side": side})


def linked_cards_for_wiki_page(
    page_slug: str,
    title: str,
    source_relative: str,
    *,
    csv_path: Path = CSV_PATH,
    progress_db_path: Path | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    rows, _ = read_cards(csv_path, progress_db_path)
    title_key = normalized_lookup_text(title)
    slug_key = normalized_lookup_text(page_slug.replace("/", " ").replace("-", " "))
    page_sources = wiki_source_variants(source_relative) | wiki_source_variants(page_slug) | wiki_source_variants(f"pages/{page_slug}.md")
    matches: list[tuple[int, str, dict[str, Any]]] = []
    for row in rows:
        reason = ""
        score = 0
        term_key = normalized_lookup_text(row.get("term"))
        english_key = normalized_lookup_text(row.get("english"))
        card_sources = set().union(*(wiki_source_variants(part) for part in parse_card_source_files(row.get("source_files"))))
        if title_key and title_key in {term_key, english_key}:
            score = 400
            reason = "문서 제목과 카드명이 일치합니다."
        elif page_sources & card_sources:
            score = 300
            reason = "문서 출처와 카드 출처가 연결됩니다."
        elif title_key and ((term_key and (title_key in term_key or term_key in title_key)) or (english_key and (title_key in english_key or english_key in title_key))):
            score = 220
            reason = "문서 제목과 카드명이 유사합니다."
        elif slug_key and slug_key in {term_key, english_key}:
            score = 180
            reason = "문서 경로와 카드명이 유사합니다."
        if score <= 0:
            continue
        matches.append(
            (
                score,
                normalized_lookup_text(row.get("term") or row.get("english") or row.get("id")),
                {
                    "id": row.get("id") or "",
                    "term": row.get("term") or row.get("english") or row.get("id") or "",
                    "english": row.get("english") or "",
                    "category": row.get("category") or "",
                    "question_attempt_count": int(row.get("question_attempt_count") or 0),
                    "question_wrong_count": int(row.get("question_wrong_count") or 0),
                    "latest_wrong_note": row.get("latest_wrong_note") or "",
                    "card_url": flashcard_card_url(row.get("id") or ""),
                    "reason": reason,
                },
            )
        )
    matches.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in matches[: max(1, limit)]]
def read_wiki_page(page_slug: str | None = None, repo_dir: Path | None = None) -> dict[str, Any]:
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
    linked_cards = linked_cards_for_wiki_page(slug, title, source_relative, csv_path=CSV_PATH, progress_db_path=PROGRESS_DB_PATH)
    return {
        "slug": slug,
        "title": title,
        "source_path": source_relative,
        "raw_url": wiki_raw_url(source_relative),
        "url": wiki_page_url(slug),
        "breadcrumbs": index["breadcrumbs"].get(slug, [{"title": title, "slug": slug, "url": wiki_page_url(slug)}]),
        "html": render_markdown_page(markdown_text, repo, source_path),
        "primary_card": linked_cards[0] if linked_cards else None,
        "linked_cards": linked_cards,
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
        return read_wiki_index()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/wiki/page/{page_slug:path}")
def api_wiki_page(page_slug: str) -> dict[str, Any]:
    try:
        return read_wiki_page(page_slug)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/wiki/checklist")
def api_wiki_checklist(payload: WikiChecklistRequest) -> dict[str, Any]:
    try:
        updated = update_wiki_checklist_item(payload.source_path, payload.line_number, payload.checked)
        return {
            "page": read_wiki_page(updated["page_slug"]),
            "updated": updated,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/wiki/raw/{relative_path:path}")
def api_wiki_raw(relative_path: str) -> FileResponse:
    try:
        repo = wiki_book_dir()
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
@app.post("/api/cards/{card_id}/ai-rewrite/preview")
def api_card_ai_rewrite_preview(card_id: str, payload: CardAiRewriteRequest) -> dict[str, Any]:
    try:
        rows, _ = read_cards(CSV_PATH, PROGRESS_DB_PATH)
        current = next((row for row in rows if row.get("id") == card_id), None)
        if current is None:
            raise KeyError(card_id)
        proposal = rewrite_card_with_codex(current, payload.instruction)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "card_id": card_id,
        "model": CODEX_MODEL,
        "proposal": proposal,
    }


@app.post("/api/cards/{card_id}/ai-rewrite/apply")
def api_card_ai_rewrite_apply(card_id: str, payload: CardAiApplyRequest) -> dict[str, Any]:
    try:
        card, backup_path = update_card_ai_content(card_id, payload, CSV_PATH, BACKUP_DIR, PROGRESS_DB_PATH)
        rows, _ = read_cards(CSV_PATH, PROGRESS_DB_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "card": card,
        "summary": summarize(rows),
        "backup_path": str(backup_path) if backup_path else "",
    }


@app.get("/api/ai-image-previews/{preview_name}")
def api_ai_image_preview_file(preview_name: str) -> FileResponse:
    try:
        preview_path, _ = read_ai_image_preview(preview_name, preview_dir=AI_IMAGE_PREVIEW_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return FileResponse(preview_path)


@app.get("/api/ai-images/{image_name}")
def api_ai_image_file(image_name: str) -> FileResponse:
    try:
        image_path = ai_image_file_path(AI_IMAGE_DIR, image_name)
        if not image_path.exists():
            raise FileNotFoundError(f"AI 이미지를 찾지 못했습니다: {image_name}")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return FileResponse(image_path)


@app.post("/api/cards/{card_id}/ai-image/preview")
def api_card_ai_image_preview(card_id: str) -> dict[str, Any]:
    try:
        rows, _ = read_cards(CSV_PATH, PROGRESS_DB_PATH)
        current = next((row for row in rows if row.get("id") == card_id), None)
        if current is None:
            raise KeyError(card_id)
        preview = generate_ai_concept_image_preview(current, preview_dir=AI_IMAGE_PREVIEW_DIR)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "card_id": card_id,
        **preview,
    }


@app.post("/api/cards/{card_id}/ai-image/discard")
def api_card_ai_image_discard(card_id: str, payload: CardAiImageApplyRequest) -> dict[str, Any]:
    try:
        discard_ai_concept_image_preview(card_id, payload, preview_dir=AI_IMAGE_PREVIEW_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, "card_id": card_id}



@app.post("/api/cards/{card_id}/ai-image/apply")
def api_card_ai_image_apply(card_id: str, payload: CardAiImageApplyRequest) -> dict[str, Any]:
    try:
        card, backup_path, image_url = apply_ai_concept_image(
            card_id,
            payload,
            CSV_PATH,
            BACKUP_DIR,
            PROGRESS_DB_PATH,
            AI_IMAGE_DIR,
            AI_IMAGE_PREVIEW_DIR,
        )
        rows, _ = read_cards(CSV_PATH, PROGRESS_DB_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "card": card,
        "summary": summarize(rows),
        "backup_path": str(backup_path) if backup_path else "",
        "image_url": image_url,
    }



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


@app.post("/api/questions/attempt")
def api_question_attempt(payload: QuestionAttemptRequest) -> dict[str, Any]:
    try:
        return save_question_attempt(payload, CSV_PATH, PROGRESS_DB_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {payload.card_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/questions/attempts")
def api_question_attempts(request: Request) -> dict[str, Any]:
    raw_limit = str(request.query_params.get("limit") or "200").strip()
    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid limit: {raw_limit}") from exc
    try:
        return read_question_attempts(
            CSV_PATH,
            PROGRESS_DB_PATH,
            card_ids=request.query_params.getlist("card_id"),
            result=request.query_params.get("result", "all"),
            limit=limit,
        )
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
    try:
        resolved_wiki_book_dir = wiki_book_dir()
        wiki_book_exists = True
    except FileNotFoundError:
        resolved_wiki_book_dir = WIKI_BOOK_DIR
        wiki_book_exists = False
    return {
        "ok": True,
        "csv_path": str(CSV_PATH),
        "csv_exists": CSV_PATH.exists(),
        "progress_db_path": str(PROGRESS_DB_PATH),
        "progress_db_exists": PROGRESS_DB_PATH.exists(),
        "wiki_book_dir": str(resolved_wiki_book_dir),
        "wiki_book_exists": wiki_book_exists,
        "wiki_book_configured_dir": str(WIKI_BOOK_DIR),
        "wiki_checklist_sync_target": wiki_checklist_sync_target(),
        "wiki_github_repo": WIKI_GITHUB_REPO,
        "wiki_github_branch": WIKI_GITHUB_BRANCH,
        "wiki_github_path_prefix": WIKI_GITHUB_PATH_PREFIX,
        "ai_rewrite_enabled": bool(OPENAI_API_KEY),
        "codex_model": CODEX_MODEL,
        "ai_image_model": IMAGE_MODEL,
    }
