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
CARD_CONTENT_COLUMNS = [
    "id",
    "term",
    "english",
    "category",
    "alphabet_index",
    "korean_initial",
    "definition",
    "detailed_explanation",
    "related_concepts",
    "source_files",
    "exam_note",
    "bok_appeared",
    "importance",
    "difficulty",
    "concept_image_url",
    "concept_image_alt",
    "concept_media_type",
    "concept_media_payload",
]
CARD_CONTENT_DB_COLUMNS = [field for field in CARD_CONTENT_COLUMNS if field != "id"]
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
# Legacy-only SQLite columns that older deployments may still carry until they
# are flushed into the canonical card-content rows.
AI_PROGRESS_FIELDS = ("definition", "detailed_explanation", "exam_note", "concept_image_url", "concept_image_alt")
CONCEPT_MEDIA_TYPES = {"", "image", "gif", "video", "mermaid", "html"}
LEGACY_CONCEPT_MEDIA_PREFIXES = ("/static/generated/", "/api/concept-images/")


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


class QuestionBankEntryRequest(BaseModel):
    question_bank_id: str | None = Field(default=None, max_length=255)
    card_id: str | None = Field(default=None, max_length=255)
    question_type: str = Field(min_length=1, max_length=64)
    prompt: str = Field(min_length=1, max_length=4000)
    body: str = Field(default="", max_length=12000)
    answer: str = Field(default="", max_length=20000)
    explanation: str = Field(default="", max_length=50000)
    rubric: list[str] = Field(default_factory=list)
    choices: list[str] = Field(default_factory=list)
    answer_index: int | None = Field(default=None, ge=0, le=100)
    topic: str = Field(default="", max_length=255)
    field_name: str = Field(default="", max_length=255)
    category: str = Field(default="", max_length=128)
    keywords: list[str] = Field(default_factory=list)
    difficulty: str = Field(default="", max_length=64)
    issuer: str = Field(default="", max_length=255)
    source_location: str = Field(default="", max_length=255)
    section: str = Field(default="", max_length=64)
    points: int | None = Field(default=None, ge=0, le=1000)
    expected_time_seconds: int | None = Field(default=None, ge=0, le=86400)
    answer_guide: str = Field(default="", max_length=255)
    session_mode: str = Field(default="practice", max_length=32)


class QuestionBankUpsertRequest(BaseModel):
    questions: list[QuestionBankEntryRequest] = Field(min_length=1, max_length=500)


class QuestionAttemptRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=255)
    question_bank_id: str | None = Field(default=None, max_length=255)
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
    session_mode: str = Field(default="practice", max_length=32)
    section: str = Field(default="", max_length=64)
    points: int | None = Field(default=None, ge=0, le=1000)
    expected_time_seconds: int | None = Field(default=None, ge=0, le=86400)
    answer_guide: str = Field(default="", max_length=255)
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


class WikiPageUpdateRequest(BaseModel):
    source_path: str = Field(min_length=1, max_length=4096)
    content: str = Field(max_length=2_000_000)
    previous_content: str | None = Field(default=None, max_length=2_000_000)


class WikiRenderPreviewRequest(BaseModel):
    source_path: str = Field(min_length=1, max_length=4096)
    content: str = Field(max_length=2_000_000)


class WikiAiRewriteRequest(BaseModel):
    source_path: str = Field(min_length=1, max_length=4096)
    content: str = Field(max_length=2_000_000)
    instruction: str = Field(default="", max_length=4000)
class CardAiRewriteRequest(BaseModel):
    instruction: str = Field(default="", max_length=4000)


class CardAiApplyRequest(BaseModel):
    definition: str | None = Field(default=None, max_length=12000)
    detailed_explanation: str | None = Field(default=None, max_length=50000)
    exam_note: str | None = Field(default=None, max_length=20000)
    concept_image_alt: str | None = Field(default=None, max_length=4000)


class CardAiImageApplyRequest(BaseModel):
    preview_name: str = Field(min_length=5, max_length=255)


class CardConceptMediaRequest(BaseModel):
    concept_media_type: str = Field(default="", max_length=32)
    concept_media_payload: str = Field(default="", max_length=200000)
    concept_image_alt: str | None = Field(default=None, max_length=4000)






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


def content_fieldnames() -> list[str]:
    return ensure_review_columns(list(CARD_CONTENT_COLUMNS))


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


def progress_db_for(csv_path: Path | None = None, progress_db_path: Path | None = None) -> Path:
    del csv_path  # Legacy bootstrap path no longer participates in runtime card reads.
    if progress_db_path is not None:
        return progress_db_path.expanduser().resolve()
    return PROGRESS_DB_PATH



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


def seed_rows_from_csv(csv_path: Path = CSV_PATH) -> list[dict[str, str]] | None:
    if not csv_path.exists():
        return None
    rows, _ = read_csv_cards(csv_path, keep_csv_progress=True)
    return rows

def bootstrap_cards_from_csv(csv_path: Path = CSV_PATH, progress_db_path: Path | None = None) -> int:
    seed_rows = seed_rows_from_csv(csv_path)
    if not seed_rows:
        return 0
    db_path = progress_db_for(None, progress_db_path)
    ensure_progress_db(db_path, seed_rows)
    sync_legacy_ai_progress_to_db(db_path)
    return len(seed_rows)



def progress_row_is_meaningful(row: dict[str, str]) -> bool:
    return bool(
        row.get("known_status") in {"O", "X"}
        or (row.get("last_reviewed") or "").strip()
        or int(normalized_review_count(row.get("review_count"))) > 0
        or normalized_bookmarked(row.get("bookmarked")) == "1"
        or (row.get("memo") or "").strip()
    )

def normalized_runtime_media_url(value: Any) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    for prefix in LEGACY_CONCEPT_MEDIA_PREFIXES:
        if url.startswith(prefix):
            tail = url[len(prefix):].lstrip("/")
            return f"/api/ai-images/{tail}" if tail else ""
    return url



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
            CREATE TABLE IF NOT EXISTS cards (
                card_id TEXT PRIMARY KEY,
                term TEXT NOT NULL DEFAULT '',
                english TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '',
                alphabet_index TEXT NOT NULL DEFAULT '',
                korean_initial TEXT NOT NULL DEFAULT '',
                definition TEXT NOT NULL DEFAULT '',
                detailed_explanation TEXT NOT NULL DEFAULT '',
                related_concepts TEXT NOT NULL DEFAULT '',
                source_files TEXT NOT NULL DEFAULT '',
                exam_note TEXT NOT NULL DEFAULT '',
                bok_appeared TEXT NOT NULL DEFAULT '',
                importance TEXT NOT NULL DEFAULT '',
                difficulty TEXT NOT NULL DEFAULT '',
                concept_image_url TEXT NOT NULL DEFAULT '',
                concept_image_alt TEXT NOT NULL DEFAULT '',
                concept_media_type TEXT NOT NULL DEFAULT '',
                concept_media_payload TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        card_columns = {row["name"] for row in conn.execute("PRAGMA table_info(cards)").fetchall()}
        card_column_definitions = {
            "term": "TEXT NOT NULL DEFAULT ''",
            "english": "TEXT NOT NULL DEFAULT ''",
            "category": "TEXT NOT NULL DEFAULT ''",
            "alphabet_index": "TEXT NOT NULL DEFAULT ''",
            "korean_initial": "TEXT NOT NULL DEFAULT ''",
            "definition": "TEXT NOT NULL DEFAULT ''",
            "detailed_explanation": "TEXT NOT NULL DEFAULT ''",
            "related_concepts": "TEXT NOT NULL DEFAULT ''",
            "source_files": "TEXT NOT NULL DEFAULT ''",
            "exam_note": "TEXT NOT NULL DEFAULT ''",
            "bok_appeared": "TEXT NOT NULL DEFAULT ''",
            "importance": "TEXT NOT NULL DEFAULT ''",
            "difficulty": "TEXT NOT NULL DEFAULT ''",
            "concept_image_url": "TEXT NOT NULL DEFAULT ''",
            "concept_image_alt": "TEXT NOT NULL DEFAULT ''",
            "concept_media_type": "TEXT NOT NULL DEFAULT ''",
            "concept_media_payload": "TEXT NOT NULL DEFAULT ''",
            "sort_order": "INTEGER NOT NULL DEFAULT 0",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in card_column_definitions.items():
            if column not in card_columns:
                conn.execute(f"ALTER TABLE cards ADD COLUMN {column} {definition}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cards_category ON cards(category)")
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
            CREATE TABLE IF NOT EXISTS question_bank (
                id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL UNIQUE,
                card_id TEXT,
                question_type TEXT NOT NULL,
                prompt TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                answer TEXT NOT NULL DEFAULT '',
                explanation TEXT NOT NULL DEFAULT '',
                rubric_json TEXT NOT NULL DEFAULT '[]',
                choices_json TEXT NOT NULL DEFAULT '[]',
                answer_index INTEGER,
                topic TEXT NOT NULL DEFAULT '',
                field_name TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '',

                keywords_json TEXT NOT NULL DEFAULT '[]',
                difficulty TEXT NOT NULL DEFAULT '',
                issuer TEXT NOT NULL DEFAULT '',
                source_location TEXT NOT NULL DEFAULT '',
                section TEXT NOT NULL DEFAULT '',
                points INTEGER,
                expected_time_seconds INTEGER,
                answer_guide TEXT NOT NULL DEFAULT '',
                session_mode TEXT NOT NULL DEFAULT 'practice',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(card_id) REFERENCES card_progress(card_id) ON DELETE SET NULL
            )
            """
        )
        question_bank_columns = {row["name"] for row in conn.execute("PRAGMA table_info(question_bank)").fetchall()}
        question_bank_column_definitions = {
            "fingerprint": "TEXT NOT NULL DEFAULT ''",
            "card_id": "TEXT",
            "question_type": "TEXT NOT NULL DEFAULT ''",
            "prompt": "TEXT NOT NULL DEFAULT ''",
            "body": "TEXT NOT NULL DEFAULT ''",
            "answer": "TEXT NOT NULL DEFAULT ''",
            "explanation": "TEXT NOT NULL DEFAULT ''",
            "rubric_json": "TEXT NOT NULL DEFAULT '[]'",
            "choices_json": "TEXT NOT NULL DEFAULT '[]'",
            "answer_index": "INTEGER",
            "topic": "TEXT NOT NULL DEFAULT ''",
            "field_name": "TEXT NOT NULL DEFAULT ''",
            "category": "TEXT NOT NULL DEFAULT ''",

            "keywords_json": "TEXT NOT NULL DEFAULT '[]'",
            "difficulty": "TEXT NOT NULL DEFAULT ''",
            "issuer": "TEXT NOT NULL DEFAULT ''",
            "source_location": "TEXT NOT NULL DEFAULT ''",
            "section": "TEXT NOT NULL DEFAULT ''",
            "points": "INTEGER",
            "expected_time_seconds": "INTEGER",
            "answer_guide": "TEXT NOT NULL DEFAULT ''",
            "session_mode": "TEXT NOT NULL DEFAULT 'practice'",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in question_bank_column_definitions.items():
            if column not in question_bank_columns:
                conn.execute(f"ALTER TABLE question_bank ADD COLUMN {column} {definition}")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_question_bank_fingerprint ON question_bank(fingerprint)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_question_bank_card_id ON question_bank(card_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_question_bank_type ON question_bank(question_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_question_bank_topic ON question_bank(topic)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_question_bank_field_name ON question_bank(field_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_question_bank_category ON question_bank(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_question_bank_issuer ON question_bank(issuer)")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS question_attempts (
                question_id TEXT PRIMARY KEY,
                question_bank_id TEXT,
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
                session_mode TEXT NOT NULL DEFAULT 'practice',
                section TEXT NOT NULL DEFAULT '',
                points INTEGER,
                expected_time_seconds INTEGER,
                answer_guide TEXT NOT NULL DEFAULT '',
                question_order INTEGER,
                question_elapsed_seconds INTEGER,
                session_elapsed_seconds INTEGER,
                time_limit_seconds INTEGER,
                question_started_at TEXT NOT NULL DEFAULT '',
                answered_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(card_id) REFERENCES card_progress(card_id) ON DELETE CASCADE,
                FOREIGN KEY(question_bank_id) REFERENCES question_bank(id) ON DELETE SET NULL
            )
            """
        )
        question_columns = {row["name"] for row in conn.execute("PRAGMA table_info(question_attempts)").fetchall()}
        question_column_definitions = {
            "question_bank_id": "TEXT",
            "judgment": "TEXT NOT NULL DEFAULT 'pending'",
            "session_id": "TEXT NOT NULL DEFAULT ''",
            "session_title": "TEXT NOT NULL DEFAULT ''",
            "session_mode": "TEXT NOT NULL DEFAULT 'practice'",
            "section": "TEXT NOT NULL DEFAULT ''",
            "points": "INTEGER",
            "expected_time_seconds": "INTEGER",
            "answer_guide": "TEXT NOT NULL DEFAULT ''",
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_question_attempts_bank_id ON question_attempts(question_bank_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_question_attempts_result ON question_attempts(is_correct)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_question_attempts_session_id ON question_attempts(session_id)")

        if seed_rows:
            now = utc_now_iso()
            conn.executemany(
                """
                INSERT OR IGNORE INTO cards
                    (card_id, term, english, category, alphabet_index, korean_initial, definition, detailed_explanation,
                     related_concepts, source_files, exam_note, bok_appeared, importance, difficulty,
                     concept_image_url, concept_image_alt, concept_media_type, concept_media_payload, sort_order, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["id"],
                        row.get("term") or "",
                        row.get("english") or "",
                        row.get("category") or "",
                        row.get("alphabet_index") or "",
                        row.get("korean_initial") or "",
                        row.get("definition") or "",
                        row.get("detailed_explanation") or "",
                        row.get("related_concepts") or "",
                        row.get("source_files") or "",
                        row.get("exam_note") or "",
                        row.get("bok_appeared") or "",
                        row.get("importance") or "",
                        row.get("difficulty") or "",
                        row.get("concept_image_url") or "",
                        row.get("concept_image_alt") or "",
                        row.get("concept_media_type") or "",
                        row.get("concept_media_payload") or "",
                        index,
                        now,
                    )
                    for index, row in enumerate(seed_rows)
                    if row.get("id")
                ],
            )
        if seed_rows:
            now = utc_now_iso()
            conn.executemany(
                """
                INSERT OR IGNORE INTO card_progress
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
    select_fields = ["card_id", "known_status", "last_reviewed", "review_count", "bookmarked", "memo", "memo_updated_at"]
    with closing(connect_progress_db(progress_db_path)) as conn:
        rows = conn.execute(f"SELECT {', '.join(select_fields)} FROM card_progress").fetchall()
    progress: dict[str, dict[str, str]] = {}
    for row in rows:
        progress[row["card_id"]] = {
            "known_status": row["known_status"] if row["known_status"] in VALID_STATUSES else "",
            "last_reviewed": row["last_reviewed"] or "",
            "review_count": normalized_review_count(str(row["review_count"])),
            "bookmarked": normalized_bookmarked(row["bookmarked"]),
            "memo": row["memo"] or "",
            "memo_updated_at": row["memo_updated_at"] or "",
        }
    return progress


def read_card_content(progress_db_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    ensure_progress_db(progress_db_path)
    select_fields = ["card_id", *CARD_CONTENT_DB_COLUMNS]
    with closing(connect_progress_db(progress_db_path)) as conn:
        rows = conn.execute(
            f"SELECT {', '.join(select_fields)} FROM cards ORDER BY sort_order ASC, card_id ASC"
        ).fetchall()
    cards: list[dict[str, str]] = []
    for row in rows:
        item = {"id": row["card_id"] or ""}
        for field in CARD_CONTENT_DB_COLUMNS:
            item[field] = row[field] or ""
        item["concept_image_url"] = normalized_runtime_media_url(item.get("concept_image_url"))
        media_type = normalized_concept_media_type(item.get("concept_media_type")) if item.get("concept_media_type") else ""
        if media_type in {"image", "gif", "video"}:
            item["concept_media_payload"] = normalized_runtime_media_url(item.get("concept_media_payload"))
        cards.append(item)

    return cards, content_fieldnames()


def read_legacy_ai_progress(progress_db_path: Path) -> dict[str, dict[str, str]]:
    ensure_progress_db(progress_db_path)
    select_fields = ["card_id", *AI_PROGRESS_FIELDS]
    with closing(connect_progress_db(progress_db_path)) as conn:
        rows = conn.execute(f"SELECT {', '.join(select_fields)} FROM card_progress").fetchall()
    legacy: dict[str, dict[str, str]] = {}
    for row in rows:
        updates = {}
        for field in AI_PROGRESS_FIELDS:
            value = str(row[field] or "").strip()
            if value:
                updates[field] = value
        if updates:
            legacy[row["card_id"]] = updates
    return legacy


def clear_legacy_ai_progress(progress_db_path: Path, card_ids: list[str]) -> int:
    normalized_ids = [str(card_id or "").strip() for card_id in card_ids if str(card_id or "").strip()]
    if not normalized_ids:
        return 0
    ensure_progress_db(progress_db_path)
    assignments = ", ".join(f"{field}=''" for field in AI_PROGRESS_FIELDS)
    placeholders = ", ".join("?" for _ in normalized_ids)
    with closing(connect_progress_db(progress_db_path)) as conn:
        before = conn.total_changes
        conn.execute(
            f"UPDATE card_progress SET {assignments} WHERE card_id IN ({placeholders})",
            normalized_ids,
        )
        conn.commit()
        return conn.total_changes - before


def sync_legacy_ai_progress_to_db(progress_db_path: Path) -> bool:
    legacy = read_legacy_ai_progress(progress_db_path)
    if not legacy:
        return False
    ensure_progress_db(progress_db_path)
    migrated_ids: list[str] = []
    changed = False
    with closing(connect_progress_db(progress_db_path)) as conn:
        for card_id, updates in legacy.items():
            current = conn.execute(
                "SELECT definition, detailed_explanation, exam_note, concept_image_url, concept_image_alt FROM cards WHERE card_id=?",
                (card_id,),
            ).fetchone()
            if current is None:
                continue
            normalized_updates = {
                field: normalized_card_text(value, limit=AI_CARD_FIELD_LIMITS[field])
                for field, value in updates.items()
            }
            if any(str(current[field] or "") != value for field, value in normalized_updates.items()):
                assignments = ", ".join(f"{field}=?" for field in normalized_updates)
                conn.execute(
                    f"UPDATE cards SET {assignments}, updated_at=? WHERE card_id=?",
                    [*normalized_updates.values(), utc_now_iso(), card_id],
                )
                changed = True
            migrated_ids.append(card_id)
        conn.commit()
    if migrated_ids:
        clear_legacy_ai_progress(progress_db_path, migrated_ids)
    return changed


def merge_progress(
    rows: list[dict[str, str]],
    progress: dict[str, dict[str, str]],
    question_stats: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    question_stats = question_stats or {}
    for row in rows:
        item = dict(row)
        item.setdefault("known_status", "")
        item.setdefault("last_reviewed", "")
        item.setdefault("review_count", "0")
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
    del csv_path  # Runtime card reads are SQLite-only.
    db_path = progress_db_for(None, progress_db_path)
    ensure_progress_db(db_path)
    sync_legacy_ai_progress_to_db(db_path)
    card_rows, fieldnames = read_card_content(db_path)
    if not card_rows:
        raise FileNotFoundError(f"Card content not found in SQLite: {db_path}")
    rows = merge_progress(card_rows, read_progress(db_path), read_question_attempt_stats(db_path))
    return rows, fieldnames





def update_card_content_fields(
    card_id: str,
    updates: dict[str, str],
    csv_path: Path = CSV_PATH,
    backup_dir: Path = BACKUP_DIR,
    progress_db_path: Path | None = None,
) -> tuple[dict[str, str], Path | None]:
    db_path = progress_db_for(None, progress_db_path)
    ensure_progress_db(db_path)
    sync_legacy_ai_progress_to_db(db_path)

    rows, _ = read_card_content(db_path)
    target = next((row for row in rows if row.get("id") == card_id), None)
    if target is None:
        raise KeyError(card_id)
    changed_updates: dict[str, str] = {}
    for field, value in updates.items():
        normalized = normalized_card_text(value, limit=AI_CARD_FIELD_LIMITS[field])
        if str(target.get(field) or "") != normalized:
            changed_updates[field] = normalized
    backup_path = backup_progress_db(db_path, backup_dir) if changed_updates else None
    if changed_updates:
        assignments = ", ".join(f"{field}=?" for field in changed_updates)
        with closing(connect_progress_db(db_path)) as conn:
            conn.execute(
                f"UPDATE cards SET {assignments}, updated_at=? WHERE card_id=?",
                [*changed_updates.values(), utc_now_iso(), card_id],
            )
            conn.commit()
        target.update(changed_updates)
    return dict(target), backup_path


def backup_progress_db(progress_db_path: Path = PROGRESS_DB_PATH, backup_dir: Path = BACKUP_DIR) -> Path | None:
    if not progress_db_path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = backup_dir / f"{progress_db_path.stem}_{stamp}{progress_db_path.suffix}"
    with closing(connect_progress_db(progress_db_path)) as source_conn, closing(sqlite3.connect(dest)) as dest_conn:
        source_conn.backup(dest_conn)
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
AI_CARD_FIELD_LIMITS = {
    **AI_REWRITE_FIELD_LIMITS,
    "concept_image_url": 4096,
    "concept_media_type": 32,
    "concept_media_payload": 200000,
}


def normalized_card_text(value: Any, *, limit: int) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return text[:limit]


def normalized_concept_media_type(value: Any) -> str:
    media_type = str(value or "").strip().lower()
    if media_type not in CONCEPT_MEDIA_TYPES:
        raise ValueError("지원하지 않는 개념 미디어 형식입니다.")
    return media_type


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


def request_codex_json_object(system_text: str, user_payload: dict[str, Any], *, parse_error_message: str) -> dict[str, Any]:
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
                        "text": system_text,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(user_payload, ensure_ascii=False),
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
        raise RuntimeError(parse_error_message) from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(parse_error_message)
    return parsed


def rewrite_card_with_codex(card: dict[str, str], instruction: str = "") -> dict[str, str]:
    parsed = request_codex_json_object(
        (
            "You rewrite Korean CS flashcard content. Return only one JSON object with the keys "
            "definition, detailed_explanation, exam_note, concept_image_alt. Keep facts grounded in the "
            "provided card. Do not invent source files, links, or citations. definition should be 1-2 "
            "sentences. detailed_explanation must stay in Korean and include both '의미:' and '활용:' "
            "sections. exam_note should be concise interview/exam guidance. concept_image_alt should be a "
            "short Korean alt text only, not a URL."
        ),
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
        parse_error_message="Codex 응답을 카드 초안 JSON으로 해석하지 못했습니다.",
    )
    rewritten: dict[str, str] = {}
    for field in CARD_AI_EDITABLE_FIELDS:
        rewritten[field] = normalized_card_text(
            parsed.get(field, card.get(field, "")),
            limit=AI_REWRITE_FIELD_LIMITS[field],
        )
    return rewritten


def rewrite_wiki_markdown_with_codex(source_path: str, content: str, instruction: str = "") -> str:
    title = extract_markdown_title(content, PurePosixPath(str(source_path or "wiki.md")).stem or "문서")
    parsed = request_codex_json_object(
        (
            "You rewrite Korean CS wiki markdown. Return only one JSON object with the key content. "
            "Keep markdown valid and preserve headings, checklists, tables, code fences, relative links, and "
            "file paths unless the instruction explicitly changes them. Keep facts grounded in the provided "
            "document. Do not invent citations, URLs, or source files."
        ),
        {
            "instruction": str(instruction or "").strip() or "현재 위키 문서를 더 명확하고 학습 친화적으로 다듬어 주세요. Markdown 구조와 링크는 유지해 주세요.",
            "page": {
                "source_path": str(source_path or "").strip(),
                "title": title,
                "content": content,
            },
        },
        parse_error_message="Codex 응답을 위키 초안 JSON으로 해석하지 못했습니다.",
    )
    rewritten = parsed.get("content")
    if not isinstance(rewritten, str):
        raise RuntimeError("Codex 응답에서 위키 Markdown 초안을 찾지 못했습니다.")
    return rewritten.replace("\r\n", "\n")[:2_000_000]


def update_card_ai_content(
    card_id: str,
    payload: CardAiApplyRequest,
    csv_path: Path = CSV_PATH,
    backup_dir: Path = BACKUP_DIR,
    progress_db_path: Path | None = None,
) -> tuple[dict[str, str], Path | None]:
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
    if not changed_updates:
        return target, None
    updated_row, backup_path = update_card_content_fields(card_id, changed_updates, csv_path, backup_dir, db_path)
    clear_legacy_ai_progress(db_path, [card_id])
    updated_rows, _ = read_cards(csv_path, db_path)
    for row in updated_rows:
        if row.get("id") == card_id:
            return row, backup_path
    return updated_row, backup_path


def update_card_concept_media(
    card_id: str,
    payload: CardConceptMediaRequest,
    csv_path: Path = CSV_PATH,
    backup_dir: Path = BACKUP_DIR,
    progress_db_path: Path | None = None,
) -> tuple[dict[str, str], Path | None]:
    media_type = normalized_concept_media_type(payload.concept_media_type)
    media_payload = normalized_card_text(payload.concept_media_payload, limit=AI_CARD_FIELD_LIMITS["concept_media_payload"])
    if media_type and not media_payload:
        raise ValueError("개념 미디어 내용을 함께 입력해야 합니다.")
    if media_payload and not media_type:
        raise ValueError("개념 미디어 형식을 먼저 선택해야 합니다.")
    updates: dict[str, str] = {
        "concept_media_type": media_type,
        "concept_media_payload": media_payload,
    }
    if payload.concept_image_alt is not None:
        updates["concept_image_alt"] = normalized_card_text(payload.concept_image_alt, limit=AI_REWRITE_FIELD_LIMITS["concept_image_alt"])
    if media_type in {"image", "gif"} and media_payload:
        updates["concept_image_url"] = media_payload
    updated_row, backup_path = update_card_content_fields(card_id, updates, csv_path, backup_dir, progress_db_path)
    refreshed_rows, _ = read_cards(csv_path, progress_db_for(csv_path, progress_db_path))
    for row in refreshed_rows:
        if row.get("id") == card_id:
            return row, backup_path
    return updated_row, backup_path

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
    updated_row, backup_path = update_card_content_fields(
        card_id,
        {"concept_image_url": next_url, "concept_image_alt": next_alt, "concept_media_type": "image", "concept_media_payload": next_url},
        csv_path,
        backup_dir,
        db_path,
    )
    clear_legacy_ai_progress(db_path, [card_id])
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
            return row, backup_path, next_url
    return updated_row, backup_path, next_url


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



def normalize_question_bank_text(value: Any, *, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]

def normalize_question_bank_markdown(value: Any, *, limit: int) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return text[:limit]



def normalize_question_bank_list(values: Any, *, item_limit: int = 255) -> list[str]:
    raw_items: list[Any]
    if isinstance(values, (list, tuple, set)):
        raw_items = list(values)
    elif values is None:
        raw_items = []
    else:
        raw_items = [part for part in re.split(r"[,;\n]+", str(values or ""))]
    seen: set[str] = set()
    normalized: list[str] = []
    for value in raw_items:
        text = normalize_question_bank_text(value, limit=item_limit)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized


def question_bank_json_text(values: Any, *, item_limit: int = 255) -> str:
    return json.dumps(normalize_question_bank_list(values, item_limit=item_limit), ensure_ascii=False)



def question_bank_json_list(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = []
    else:
        parsed = value
    return normalize_question_bank_list(parsed)


def question_bank_keywords_for_card(card: dict[str, Any]) -> list[str]:
    related = re.split(r"\[\[|\]\]|[,;/\n]", str(card.get("related_concepts") or ""))
    return normalize_question_bank_list([
        card.get("term") or "",
        card.get("english") or "",
        *related,
    ])

QUESTION_BANK_CATEGORIES = (
    "금융IT·신기술",
    "네트워크",
    "데이터베이스",
    "보안",
    "소프트웨어공학",
    "운영체제",
    "인공지능·데이터",
    "자료구조·알고리즘",
    "컴퓨터구조",
    "클라우드·분산시스템",
    "프로그래밍 언어",
)

QUESTION_BANK_CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "데이터베이스": ("데이터베이스", "db", "sql", "정규화", "트랜잭션", "스키마", "erd"),
    "운영체제": ("운영체제", "os", "프로세스", "스레드", "교착상태", "스케줄링", "페이지", "세마포어", "스래싱", "메모리 관리"),
    "네트워크": ("네트워크", "dns", "라우팅", "tcp", "udp", "ipv", "cdma", "브리지", "ftp", "http", "데이터 통신", "crc", "cyclic redundancy check"),
    "보안": ("보안", "정보보호", "암호", "전자서명", "pki", "xss", "csrf", "사회공학", "arp 공격", "접근통제", "사이버 침해", "사이버 테러", "ddos", "악성코드"),
    "소프트웨어공학": ("소프트웨어공학", "소프트웨어 공학", "mvc", "애자일", "agile", "테스트", "형상관리", "요구사항", "프로젝트"),
    "컴퓨터구조": ("컴퓨터구조", "컴퓨터 구조", "캐시", "raid", "파이프라인", "instruction", "clock frequency", "2진수", "1의 보수", "2의 보수", "overflow"),
    "자료구조·알고리즘": ("자료구조", "알고리즘", "정렬", "해시", "트리", "그래프", "kruskal", "mass", "markov"),
    "클라우드·분산시스템": ("클라우드", "분산", "iaas", "paas", "saas", "하이브리드 클라우드", "원격근무", "vdi", "블록체인", "soa", "web 2.0"),
    "인공지능·데이터": ("인공지능", "머신러닝", "머신 러닝", "ai", "통계", "텍스트 마이닝", "text mining", "데이터 웨어하우스"),
    "프로그래밍 언어": ("프로그래밍 언어", "java", "객체지향", "정규 표현식", "컴파일러"),
    "금융IT·신기술": ("금융it", "전자금융", "자산관리시스템", "신기술"),
}



def question_bank_categories_from_cards(csv_path: Path = CSV_PATH, progress_db_path: Path | None = None) -> list[str]:
    rows, _ = read_cards(csv_path, progress_db_path)
    seen: set[str] = set()
    categories: list[str] = []
    for category in QUESTION_BANK_CATEGORIES:
        normalized = normalize_question_bank_text(category, limit=128)
        if not normalized:
            continue
        seen.add(normalized.casefold())
        categories.append(normalized)
    for row in rows:
        category = normalize_question_bank_text(row.get("category"), limit=128)
        if not category:
            continue
        key = category.casefold()
        if key in seen:
            continue
        seen.add(key)
        categories.append(category)
    return categories



def infer_question_bank_category(
    raw_category: Any,
    *,
    card_category: Any = "",
    topic: Any = "",
    prompt: Any = "",
    body: Any = "",
    csv_path: Path = CSV_PATH,
    progress_db_path: Path | None = None,
) -> str:
    allowed_categories = question_bank_categories_from_cards(csv_path, progress_db_path)
    allowed_lookup = {item.casefold(): item for item in allowed_categories}
    for candidate in (raw_category, card_category):
        normalized = normalize_question_bank_text(candidate, limit=128)
        if normalized and normalized.casefold() in allowed_lookup:
            return allowed_lookup[normalized.casefold()]
    combined = " ".join(str(value or "") for value in (topic, prompt, body)).casefold()
    for category in allowed_categories:
        if category.casefold() in combined:
            return category
    for category, hints in QUESTION_BANK_CATEGORY_HINTS.items():
        if category.casefold() not in allowed_lookup:
            continue
        if any(str(hint).casefold() in combined for hint in hints):
            return allowed_lookup[category.casefold()]
    if raw_category:
        raise ValueError(f"Unsupported question bank category: {raw_category}")
    normalized_card_category = normalize_question_bank_text(card_category, limit=128)
    return allowed_lookup.get(normalized_card_category.casefold(), "")


def question_bank_fingerprint(entry: dict[str, Any]) -> str:
    canonical = {
        "card_id": entry["card_id"],
        "question_type": entry["question_type"],
        "prompt": entry["prompt"],
        "body": entry["body"],
        "answer": entry["answer"],
        "explanation": entry["explanation"],
        "rubric": entry["rubric"],
        "choices": entry["choices"],
        "answer_index": entry["answer_index"],
        "topic": entry["topic"],
        "field_name": entry["field_name"],
        "category": entry["category"],
        "keywords": entry["keywords"],
        "difficulty": entry["difficulty"],
        "issuer": entry["issuer"],
        "source_location": entry["source_location"],
        "section": entry["section"],
        "points": entry["points"],
        "expected_time_seconds": entry["expected_time_seconds"],
        "answer_guide": entry["answer_guide"],
        "session_mode": entry["session_mode"],
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_question_bank_entry(
    payload: QuestionBankEntryRequest | dict[str, Any],
    csv_path: Path = CSV_PATH,
    progress_db_path: Path | None = None,
) -> dict[str, Any]:
    raw = payload.model_dump() if isinstance(payload, BaseModel) else dict(payload or {})
    question_type = str(raw.get("question_type") or "").strip().lower()
    if question_type not in SUPPORTED_QUESTION_TYPES:
        raise ValueError(f"Unsupported question type: {raw.get('question_type')}")
    prompt = normalize_question_bank_markdown(raw.get("prompt"), limit=4000)
    if not prompt:
        raise ValueError("question prompt is required")
    card_id = normalize_question_bank_text(raw.get("card_id"), limit=255)
    card: dict[str, Any] = {}
    if card_id:
        _ensure_card_exists(card_id, csv_path, progress_db_path)
        rows, _ = read_cards(csv_path, progress_db_path)
        card = next((row for row in rows if str(row.get("id") or "").strip() == card_id), {})
    choices = normalize_question_bank_list(raw.get("choices"), item_limit=2000)
    answer_index = raw.get("answer_index")
    if answer_index is not None:
        answer_index = int(answer_index)
        if answer_index < 0 or answer_index > 100:
            raise ValueError(f"Invalid answer_index: {answer_index}")
    if question_type == "multiple_choice" and answer_index is not None and answer_index >= len(choices):
        raise ValueError("Multiple-choice answer_index must point to an existing choice")
    topic = normalize_question_bank_text(raw.get("topic"), limit=255)
    body = normalize_question_bank_markdown(raw.get("body"), limit=12000)
    normalized = {
        "question_bank_id": normalize_question_bank_text(raw.get("question_bank_id"), limit=255),
        "card_id": card_id,
        "question_type": question_type,
        "prompt": prompt,
        "body": body,
        "answer": normalize_question_bank_markdown(raw.get("answer"), limit=20000),
        "explanation": normalize_question_bank_markdown(raw.get("explanation"), limit=50000),
        "rubric": normalize_question_bank_list(raw.get("rubric"), item_limit=2000),
        "choices": choices,
        "answer_index": answer_index,
        "topic": topic,
        "field_name": normalize_question_bank_text(raw.get("field_name"), limit=255),
        "category": infer_question_bank_category(
            raw.get("category") or raw.get("card_category") or "",
            card_category=card.get("category") if isinstance(card, dict) else "",
            topic=topic,
            prompt=prompt,
            body=body,
            csv_path=csv_path,
            progress_db_path=progress_db_path,
        ),
        "keywords": normalize_question_bank_list(raw.get("keywords"), item_limit=255),
        "difficulty": normalize_question_bank_text(raw.get("difficulty"), limit=64),
        "issuer": normalize_question_bank_text(raw.get("issuer"), limit=255),
        "source_location": normalize_question_bank_text(raw.get("source_location"), limit=255),
        "section": normalize_question_bank_text(raw.get("section"), limit=64),
        "points": raw.get("points"),
        "expected_time_seconds": raw.get("expected_time_seconds"),
        "answer_guide": normalize_question_bank_markdown(raw.get("answer_guide"), limit=255),
        "session_mode": normalize_question_bank_text(raw.get("session_mode") or "practice", limit=32) or "practice",
    }
    if not normalized["category"]:
        raise ValueError("question category is required and must match an existing flashcard category")
    normalized["fingerprint"] = question_bank_fingerprint(normalized)
    normalized["question_bank_id"] = normalized["question_bank_id"] or f"qb-{normalized['fingerprint'][:24]}"
    return normalized


def question_bank_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "question_bank_id": row["id"],
        "card_id": row["card_id"] or "",
        "question_type": row["question_type"] or "",
        "prompt": row["prompt"] or "",
        "body": row["body"] or "",
        "answer": row["answer"] or "",
        "explanation": row["explanation"] or "",
        "rubric": question_bank_json_list(row["rubric_json"] if "rubric_json" in row.keys() else "[]"),
        "choices": question_bank_json_list(row["choices_json"] if "choices_json" in row.keys() else "[]"),
        "answer_index": row["answer_index"] if "answer_index" in row.keys() else None,
        "topic": row["topic"] if "topic" in row.keys() else "",
        "field_name": row["field_name"] if "field_name" in row.keys() else "",
        "category": row["category"] if "category" in row.keys() else "",
        "keywords": question_bank_json_list(row["keywords_json"] if "keywords_json" in row.keys() else "[]"),
        "difficulty": row["difficulty"] if "difficulty" in row.keys() else "",
        "issuer": row["issuer"] if "issuer" in row.keys() else "",
        "source_location": row["source_location"] if "source_location" in row.keys() else "",
        "section": row["section"] if "section" in row.keys() else "",
        "points": row["points"] if "points" in row.keys() else None,
        "expected_time_seconds": row["expected_time_seconds"] if "expected_time_seconds" in row.keys() else None,
        "answer_guide": row["answer_guide"] if "answer_guide" in row.keys() else "",
        "session_mode": row["session_mode"] if "session_mode" in row.keys() else "practice",
        "created_at": row["created_at"] if "created_at" in row.keys() else "",
        "updated_at": row["updated_at"] if "updated_at" in row.keys() else "",
    }


def upsert_question_bank_entries(
    entries: list[QuestionBankEntryRequest | dict[str, Any]],
    csv_path: Path = CSV_PATH,
    progress_db_path: Path | None = None,
) -> dict[str, Any]:
    normalized_entries = [normalize_question_bank_entry(entry, csv_path, progress_db_path) for entry in entries]
    db_path = progress_db_for(csv_path, progress_db_path)
    ensure_progress_db(db_path)
    saved_items: list[dict[str, Any]] = []
    with closing(connect_progress_db(db_path)) as conn:
        for entry in normalized_entries:
            existing = conn.execute(
                "SELECT id, created_at FROM question_bank WHERE fingerprint = ?",
                (entry["fingerprint"],),
            ).fetchone()
            now = utc_now_iso()
            if entry["card_id"]:
                conn.execute(
                    """
                    INSERT INTO card_progress (card_id, known_status, last_reviewed, review_count, bookmarked, memo, memo_updated_at, updated_at)
                    VALUES (?, '', '', 0, 0, '', '', ?)
                    ON CONFLICT(card_id) DO NOTHING
                    """,
                    (entry["card_id"], now),
                )
            conn.execute(
                """
                INSERT INTO question_bank (
                    id, fingerprint, card_id, question_type, prompt, body, answer, explanation,
                    rubric_json, choices_json, answer_index, topic, field_name, category, keywords_json,
                    difficulty, issuer, source_location, section, points, expected_time_seconds,
                    answer_guide, session_mode, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    card_id = excluded.card_id,
                    question_type = excluded.question_type,
                    prompt = excluded.prompt,
                    body = excluded.body,
                    answer = excluded.answer,
                    explanation = excluded.explanation,
                    rubric_json = excluded.rubric_json,
                    choices_json = excluded.choices_json,
                    answer_index = excluded.answer_index,
                    topic = excluded.topic,
                    field_name = excluded.field_name,
                    category = excluded.category,
                    keywords_json = excluded.keywords_json,
                    difficulty = excluded.difficulty,
                    issuer = excluded.issuer,
                    source_location = excluded.source_location,
                    section = excluded.section,
                    points = excluded.points,
                    expected_time_seconds = excluded.expected_time_seconds,
                    answer_guide = excluded.answer_guide,
                    session_mode = excluded.session_mode,
                    updated_at = excluded.updated_at
                """,
                (
                    entry["question_bank_id"],
                    entry["fingerprint"],
                    entry["card_id"] or None,
                    entry["question_type"],
                    entry["prompt"],
                    entry["body"],
                    entry["answer"],
                    entry["explanation"],
                    question_bank_json_text(entry["rubric"], item_limit=2000),
                    question_bank_json_text(entry["choices"], item_limit=2000),
                    entry["answer_index"],
                    entry["topic"],
                    entry["field_name"],
                    entry["category"],

                    question_bank_json_text(entry["keywords"], item_limit=255),
                    entry["difficulty"],
                    entry["issuer"],
                    entry["source_location"],
                    entry["section"],
                    entry["points"],
                    entry["expected_time_seconds"],
                    entry["answer_guide"],
                    entry["session_mode"],
                    existing["created_at"] if existing else now,
                    now,
                ),
            )
            saved = conn.execute(
                """
                SELECT id, card_id, question_type, prompt, body, answer, explanation,
                       rubric_json, choices_json, answer_index, topic, field_name, category, keywords_json,
                       difficulty, issuer, source_location, section, points, expected_time_seconds,
                       answer_guide, session_mode, created_at, updated_at
                FROM question_bank
                WHERE fingerprint = ?
                """,
                (entry["fingerprint"],),
            ).fetchone()
            saved_items.append(question_bank_row_to_dict(saved) or {})
        conn.commit()
    return {
        "items": saved_items,
        "count": len(saved_items),
    }


def seed_demo_question_bank_entries(
    csv_path: Path = CSV_PATH,
    progress_db_path: Path | None = None,
) -> None:
    db_path = progress_db_for(csv_path, progress_db_path)
    ensure_progress_db(db_path)
    with closing(connect_progress_db(db_path)) as conn:
        existing_count = int(conn.execute("SELECT COUNT(*) FROM question_bank").fetchone()[0] or 0)
    if existing_count:
        return
    rows, _ = read_cards(csv_path, db_path)
    if not rows:
        return
    sample = rows[0]
    upsert_question_bank_entries(
        [
            {
                "card_id": sample.get("id") or "",
                "question_type": "subjective",
                "prompt": "## 더미 문제\n**정규화(Normalization)** 의 목적을 설명하시오.",
                "body": "다음 요구를 모두 반영해 답하시오.\n\n- 데이터 중복 관점\n- 이상 현상 관점\n- 실무 설계 관점\n\n![예시 이미지](/static/favicon.svg)\n\n> 위 이미지는 마크다운 이미지 렌더링 예시입니다.",
                "answer": "정규화는 릴레이션을 분해하여 **데이터 중복을 줄이고**, 삽입/삭제/갱신 이상을 방지하며, 스키마를 더 일관되게 유지하기 위한 과정이다.",
                "explanation": "### 해설\n\n1. **중복 감소**: 같은 사실을 여러 행에 반복 저장하지 않게 한다.\n2. **이상 현상 방지**: 삽입 이상, 삭제 이상, 갱신 이상을 완화한다.\n3. **유지보수성 향상**: 제약조건과 의미가 더 분명해진다.\n\n![해설 이미지](/static/favicon.svg)",
                "rubric": ["중복 감소", "이상 현상 방지", "유지보수성 향상"],
                "topic": "데이터베이스",
                "field_name": "데모",
                "keywords": ["정규화", "이상 현상", "데이터베이스"],
                "difficulty": "중",
                "issuer": "샘플",
                "source_location": "더미 데이터 1번",
                "section": "연습문제",
                "points": 10,
                "expected_time_seconds": 300,
                "answer_guide": "정의 → 목적 → 이상 현상 순으로 3~5문장",
                "session_mode": "practice",
            }
        ],
        csv_path,
        db_path,
    )


def read_question_bank_entries(
    csv_path: Path = CSV_PATH,
    progress_db_path: Path | None = None,
    *,
    card_id: str = "",
    question_type: str = "",
    topic: str = "",
    field_name: str = "",
    category: str = "",
    issuer: str = "",
    difficulty: str = "",
    section: str = "",
    source_location: str = "",
    query: str = "",
    limit: int = 200,
) -> dict[str, Any]:
    db_path = progress_db_for(csv_path, progress_db_path)
    ensure_progress_db(db_path)
    seed_demo_question_bank_entries(csv_path, db_path)
    safe_limit = max(1, min(int(limit or 200), 500))
    filters = {
        "card_id": normalize_question_bank_text(card_id, limit=255),
        "question_type": normalize_question_bank_text(question_type, limit=64).lower(),
        "topic": normalize_question_bank_text(topic, limit=255),
        "field_name": normalize_question_bank_text(field_name, limit=255),
        "category": normalize_question_bank_text(category, limit=128),
        "issuer": normalize_question_bank_text(issuer, limit=255),
        "difficulty": normalize_question_bank_text(difficulty, limit=64),
        "section": normalize_question_bank_text(section, limit=64),
        "source_location": normalize_question_bank_text(source_location, limit=255),
        "query": normalize_question_bank_text(query, limit=255),
    }
    where_clauses: list[str] = []
    params: list[Any] = []
    for column in ("card_id", "topic", "field_name", "category", "issuer", "difficulty", "section", "source_location"):
        value = filters[column]
        if not value:
            continue
        where_clauses.append(f"LOWER({column}) LIKE ?")
        params.append(f"%{value.lower()}%")
    if filters["question_type"]:
        where_clauses.append("question_type = ?")
        params.append(filters["question_type"])
    if filters["query"]:
        where_clauses.append(
            "(" + " OR ".join([
                "LOWER(prompt) LIKE ?",
                "LOWER(body) LIKE ?",
                "LOWER(answer) LIKE ?",
                "LOWER(explanation) LIKE ?",
                "LOWER(topic) LIKE ?",
                "LOWER(field_name) LIKE ?",
                "LOWER(category) LIKE ?",
                "LOWER(issuer) LIKE ?",
                "LOWER(source_location) LIKE ?",
                "LOWER(keywords_json) LIKE ?",
            ]) + ")"
        )
        needle = f"%{filters['query'].lower()}%"
        params.extend([needle] * 10)
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    rows, _ = read_cards(csv_path, db_path)
    card_map = {str(row.get("id") or "").strip(): row for row in rows if str(row.get("id") or "").strip()}
    with closing(connect_progress_db(db_path)) as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) AS total_count FROM question_bank {where_sql}",
            tuple(params),
        ).fetchone()
        issuer_rows = conn.execute(
            "SELECT DISTINCT issuer FROM question_bank WHERE TRIM(issuer) <> '' ORDER BY issuer COLLATE NOCASE ASC"
        ).fetchall()
        category_rows = conn.execute(
            "SELECT DISTINCT category FROM question_bank WHERE TRIM(category) <> '' ORDER BY category COLLATE NOCASE ASC"
        ).fetchall()
        query_rows = conn.execute(
            f"""
            SELECT id, card_id, question_type, prompt, body, answer, explanation,
                   rubric_json, choices_json, answer_index, topic, field_name, category, keywords_json,
                   difficulty, issuer, source_location, section, points, expected_time_seconds,
                   answer_guide, session_mode, created_at, updated_at
            FROM question_bank
            {where_sql}
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            tuple(params + [safe_limit]),
        ).fetchall()
    items: list[dict[str, Any]] = []
    for row in query_rows:
        item = question_bank_row_to_dict(row) or {}
        card = card_map.get(item.get("card_id", ""), {})
        item["term"] = card.get("term") or card.get("english") or item.get("card_id") or ""
        item["english"] = card.get("english") or ""
        item["card_category"] = card.get("category") or ""
        item["card_url"] = flashcard_card_url(item.get("card_id") or "") if item.get("card_id") else ""
        items.append(item)
    return {
        "items": items,
        "summary": {
            "total": int(total_row["total_count"] or 0) if total_row else 0,
            "returned": len(items),
            "limit": safe_limit,
            "available_issuers": [str(row[0] or "").strip() for row in issuer_rows if str(row[0] or "").strip()],
            "available_categories": [str(row[0] or "").strip() for row in category_rows if str(row[0] or "").strip()],
            **filters,
        },
    }


def generated_question_bank_entry(question: dict[str, Any], card: dict[str, Any]) -> dict[str, Any]:
    return {
        "card_id": question.get("card_id") or card.get("id") or "",
        "question_type": question.get("type") or "",
        "prompt": question.get("prompt") or "",
        "body": question.get("body") or "",
        "answer": question.get("answer") or "",
        "explanation": question.get("explanation") or "",
        "rubric": question.get("rubric") or [],
        "choices": question.get("choices") or [],
        "answer_index": question.get("answer_index") if isinstance(question.get("answer_index"), int) else None,
        "topic": card.get("category") or "",
        "field_name": "",
        "category": question.get("category") or card.get("category") or "",
        "keywords": question_bank_keywords_for_card(card),
        "difficulty": card.get("difficulty") or "",
        "issuer": "카드 생성",
        "source_location": card.get("source_files") or card.get("id") or "",
        "section": question.get("section") or "",
        "points": question.get("points") if isinstance(question.get("points"), int) else None,
        "expected_time_seconds": question.get("expected_time_seconds") if isinstance(question.get("expected_time_seconds"), int) else None,
        "answer_guide": question.get("answer_guide") or "",
        "session_mode": question.get("session_mode") or "practice",
    }


def attach_generated_question_bank_ids(
    payload: dict[str, Any],
    rows: list[dict[str, Any]],
    csv_path: Path = CSV_PATH,
    progress_db_path: Path | None = None,
) -> dict[str, Any]:
    questions = list(payload.get("questions") or [])
    if not questions:
        return payload
    card_map = {str(row.get("id") or "").strip(): row for row in rows if str(row.get("id") or "").strip()}
    bank_payloads = [generated_question_bank_entry(question, card_map.get(str(question.get("card_id") or ""), {})) for question in questions]
    saved = upsert_question_bank_entries(bank_payloads, csv_path, progress_db_path)
    for question, stored in zip(questions, saved.get("items") or []):
        question["question_bank_id"] = stored.get("question_bank_id") or ""
        question["topic"] = stored.get("topic") or question.get("topic") or ""
        question["field_name"] = stored.get("field_name") or question.get("field_name") or ""
        question["keywords"] = stored.get("keywords") or question.get("keywords") or []
        question["difficulty"] = stored.get("difficulty") or question.get("difficulty") or ""
        question["issuer"] = stored.get("issuer") or question.get("issuer") or ""
        question["source_location"] = stored.get("source_location") or question.get("source_location") or ""
    payload["questions"] = questions
    payload["question_bank_saved"] = len(saved.get("items") or [])
    return payload

BOK_QUESTION_BANK_PAGE_GLOB = "05-14-[0-9][0-9]-*.md"
BOK_ANY_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
BOK_NUMBERED_HEADING_RE = re.compile(r"^(#{2,6})\s+(\d+)\.\s+(.+?)\s*$")
BOK_OPTION_LINE_RE = re.compile(r"^[A-E]\.\s+(.+?)\s*$")
BOK_TITLE_PREFIX_RE = re.compile(r"^\d{2}-\d{2}-\d{2}\.\s*")
BOK_YEAR_RE = re.compile(r"\b(20\d{2})\b")
BOK_SUBJECTIVE_POINTS = 10
BOK_ESSAY_POINTS = 20
BOK_SUBJECTIVE_EXPECTED_SECONDS = 12 * 60
BOK_ESSAY_EXPECTED_SECONDS = 54 * 60
BOK_SUBJECTIVE_ANSWER_GUIDE = "정의 → 원리 → 장단점/비교 → 예시 → 금융IT 적용 순으로 5~7문장"
BOK_ESSAY_ANSWER_GUIDE = "정의 → 원리 → 비교 → 사례 → 금융IT 적용 → 결론 순으로 12~15문장"
BOK_KEYWORD_SPLIT_RE = re.compile(r"\s*[:·,/]\s*")
BOK_KEYWORD_SUFFIX_RE = re.compile(r"\s*(?:참고 그림|구성도|헤더 구조|개요|그림)\s*$")
BOK_KEYWORD_NOISE_RE = re.compile(r"(?:^제시문\s*\d+$|^문제$|^유의사항$|^(?:i|ii|iii|iv|v|그리고|최근|현재|상기)$|다음(?:을|에)?|물음|답하시오|기술하시오|논술하시오|설명하시오|비교하시오|올바른|올바르게|어떻게|무엇|얼마|시나리오)")
BOK_KEYWORD_MATCHERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("PKI", ("pki",)),
    ("전자서명", ("전자서명",)),
    ("XSS", ("xss", "cross site scripting")),
    ("CSRF", ("csrf",)),
    ("사회공학", ("사회공학",)),
    ("ARP 공격", ("arp 공격",)),
    ("사이버 침해", ("사이버 침해",)),
    ("사이버 테러", ("사이버 테러",)),
    ("데이터베이스", ("데이터베이스", "database")),
    ("트랜잭션", ("트랜잭션", "transaction")),
    ("정규화", ("정규화",)),
    ("데이터 웨어하우스", ("데이터 웨어하우스", "data warehousing")),
    ("데이터 관리", ("데이터 관리",)),
    ("데이터 품질", ("데이터 품질",)),
    ("데이터 표준화", ("데이터 표현", "다르게 입력", "표준화")),
    ("표준화", ("표준화", "일원화")),
    ("JSON", ("json",)),
    ("XML", ("xml",)),
    ("공개소프트웨어", ("공개소프트웨어", "open source software", "오픈소스")),
    ("R", (" r(", " r(", " r ", "최근 비즈니스 및 학계로부터 각광을 받고 있는 공개소프트웨어(open source software)인 r")),
    ("SAS", ("sas",)),
    ("MATLAB", ("matlab",)),
    ("Stata", ("stata",)),
    ("EViews", ("eviews",)),
    ("Gauss", ("gauss",)),
    ("블록체인", ("블록체인", "blockchain", "비트코인")),
    ("자산관리시스템", ("자산관리시스템",)),
    ("원격근무", ("원격근무",)),
    ("재택근무", ("재택근무",)),
    ("VDI", ("vdi", "virtual desktop infrastructure")),
    ("클라우드", ("클라우드", "cloud")),
    ("IaaS", ("iaas",)),
    ("PaaS", ("paas",)),
    ("SaaS", ("saas",)),
    ("프라이빗 클라우드", ("프라이빗", "private cloud")),
    ("퍼블릭 클라우드", ("퍼블릭", "public cloud")),
    ("하이브리드 클라우드", ("하이브리드", "hybrid cloud")),
    ("유틸리티 컴퓨팅", ("유틸리티 컴퓨팅", "utility computing")),
    ("SOA", ("soa",)),
    ("웹 2.0", ("웹 2.0", "web 2.0")),
    ("프로세스", ("프로세스", "process")),
    ("세마포어", ("세마포어", "semaphore")),
    ("스케줄링", ("스케줄링", "scheduling")),
    ("SJF", ("sjf", "shortest job first")),
    ("교착상태", ("교착상태", "deadlock")),
    ("은행원 알고리즘", ("은행원 알고리즘", "banker's algorithm")),
    ("페이지 부재", ("페이지 부재", "page fault")),
    ("메모리 관리", ("메모리 관리",)),
    ("플래시 메모리", ("플래시 메모리",)),
    ("RAID", ("raid",)),
    ("캐시 메모리", ("캐시 메모리",)),
    ("파이프라인", ("파이프라인", "pipeline")),
    ("2진수", ("2진수",)),
    ("논리회로", ("논리회로",)),
    ("플립플롭", ("플립플롭", "flip-flop")),
    ("라우팅", ("라우팅",)),
    ("DNS", ("dns",)),
    ("TCP", ("tcp",)),
    ("FTP", ("ftp", "파일 전송 프로토콜")),
    ("IPv4", ("ipv4",)),
    ("주민등록번호", ("주민등록번호",)),
    ("데이터 통신", ("데이터 통신",)),
    ("브리지", ("브리지", "bridge")),
    ("CRC", ("crc", "cyclic redundancy check")),
    ("QoS", ("qos", "quality of service")),
    ("네트워크 보안", ("네트워크 보안",)),
    ("객체지향", ("객체지향",)),
    ("Java", ("java",)),
    ("정규 표현식", ("정규 표현식", "regular expression")),
    ("MVC", ("mvc",)),
    ("애자일", ("agile", "애자일")),
    ("소프트웨어 공학", ("소프트웨어 공학", "software crisis", "소프트웨어 위기")),
    ("프로젝트 관리", ("프로젝트 관리자", "프로젝트 관리", "프로젝트의 성공")),
    ("통계 분석", ("통계 분석",)),
    ("규모 산정", ("규모 산정",)),
    ("해시", ("해시", "hash")),
    ("허프만", ("허프만", "huffman")),
    ("이진검색트리", ("이진검색트리", "binary search tree")),
    ("후위표기식", ("후위표기식", "postfix expression")),
    ("스택", ("스택", "stack")),
    ("그래프 알고리즘", ("그래프 알고리즘",)),
    ("최소신장트리", ("최소신장트리",)),
    ("동적 계획법", ("동적 계획법",)),
    ("머신러닝", ("머신러닝", "머신 러닝", "machine learning")),
    ("인공지능", ("인공지능", "artificial intelligence")),
    ("텍스트 마이닝", ("텍스트 마이닝", "text mining")),
    ("인간 본성", ("인간 본성", "human nature")),
    ("성범죄", ("성범죄",)),
    ("DNA", ("dna",)),
    ("문화적 진화", ("문화적 진화",)),
)


def clean_bok_question_bank_title(value: str) -> str:
    return BOK_TITLE_PREFIX_RE.sub("", str(value or "").strip())



def bok_question_bank_field_name(page_title: str) -> str:
    title = str(page_title or "")
    if "일반논술" in title:
        return "일반논술"
    if "전산논술" in title or "논술 (IT·컴퓨터공학)" in title:
        return "전산논술"
    if "전산학술" in title:
        return "전산학술"
    if "컴퓨터공학 학술" in title:
        return "컴퓨터공학 학술"
    return "한국은행"



def bok_question_bank_source_pages(repo_dir: Path | None = None) -> list[Path]:
    repo = wiki_book_dir(repo_dir)
    pages = wiki_pages_dir(repo)
    return sorted(path for path in pages.glob(BOK_QUESTION_BANK_PAGE_GLOB) if path.is_file())



def bok_heading_stack_by_line(lines: list[str]) -> dict[int, list[tuple[int, str]]]:
    stack: list[tuple[int, str]] = []
    snapshots: dict[int, list[tuple[int, str]]] = {}
    for index, line in enumerate(lines):
        match = BOK_ANY_HEADING_RE.match(line)
        if not match:
            continue
        level = len(match.group(1))
        text = match.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, text))
        snapshots[index] = list(stack)
    return snapshots



def bok_fallback_topic(lines: list[str], page_title: str) -> str:
    problem_index = next((index for index, line in enumerate(lines) if line.strip() == "### 문제"), None)
    search_lines = lines[problem_index + 1 :] if problem_index is not None else lines
    for line in search_lines:
        heading_match = BOK_ANY_HEADING_RE.match(line)
        if heading_match and len(heading_match.group(1)) >= 4:
            return heading_match.group(2).strip()
        stripped = line.strip()
        if stripped.startswith("**") and stripped.endswith("**") and len(stripped) > 4:
            return stripped[2:-2].strip()
    for line in search_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ">", "!", "|", "-", "*")):
            continue
        if re.match(r"^\d+[.)]\s+", stripped):
            continue
        if any(keyword in stripped for keyword in ("하시오", "기술하시오", "논술하시오")):
            return stripped
    return page_title or "한국은행 문제"



def bok_fallback_body_start(lines: list[str]) -> int:
    first_h2 = next((index for index, line in enumerate(lines) if line.startswith("## ")), None)
    return 0 if first_h2 is None else first_h2 + 1



def bok_question_bank_choices(markdown_text: str) -> list[str]:
    choices = [match.group(1).strip() for line in str(markdown_text or "").splitlines() if (match := BOK_OPTION_LINE_RE.match(line.strip()))]
    return choices if len(choices) >= 2 else []



def infer_bok_question_type(page_title: str, prompt: str, body: str, context_headings: list[str]) -> str:
    title = str(page_title or "")
    combined_context = "\n".join([title, prompt, body, *context_headings])
    choices = bok_question_bank_choices(body)
    if "논술" in title or "### 문제" in body or ("### 유의사항" in body and ("논술하시오" in combined_context or "기술하시오" in combined_context)):
        return "essay"
    if choices:
        return "multiple_choice"
    return "subjective"



def bok_question_bank_section_name(field_name: str, question_type: str) -> str:
    if field_name == "일반논술":
        return "일반논술"
    if question_type == "essay" or field_name == "전산논술":
        return "전공논술"
    return "전공필기"



def bok_question_bank_points(question_type: str) -> int | None:
    if question_type == "essay":
        return BOK_ESSAY_POINTS
    if question_type == "subjective":
        return BOK_SUBJECTIVE_POINTS
    return None



def bok_question_bank_expected_seconds(question_type: str) -> int | None:
    if question_type == "essay":
        return BOK_ESSAY_EXPECTED_SECONDS
    if question_type == "subjective":
        return BOK_SUBJECTIVE_EXPECTED_SECONDS
    return None



def bok_question_bank_answer_guide(question_type: str) -> str:
    if question_type == "essay":
        return BOK_ESSAY_ANSWER_GUIDE
    if question_type == "subjective":
        return BOK_SUBJECTIVE_ANSWER_GUIDE
    return ""



def bok_normalize_keyword_fragment(value: Any) -> str:
    text = normalize_question_bank_text(value, limit=80)
    if not text:
        return ""
    text = BOK_KEYWORD_SUFFIX_RE.sub("", text).strip(" :-")
    text = re.sub(r"\s+", " ", text)
    return text



def bok_keyword_is_noise(value: str) -> bool:
    if not value:
        return True
    if BOK_KEYWORD_NOISE_RE.search(value):
        return True
    if len(value) > 28 and ("?" in value or any(token in value for token in ("하시오", "답하시오", "기술하시오", "설명하시오", "비교하시오", "논술하시오"))):
        return True
    return False



def bok_topic_keyword_candidates(topic: str) -> list[str]:
    normalized = normalize_question_bank_text(topic, limit=255)
    if not normalized or bok_keyword_is_noise(normalized):
        return []
    if not normalized:
        return []
    pieces = BOK_KEYWORD_SPLIT_RE.split(normalized) if BOK_KEYWORD_SPLIT_RE.search(normalized) else [normalized]
    candidates: list[str] = []
    for piece in pieces:
        cleaned = bok_normalize_keyword_fragment(piece)
        if not cleaned:
            continue
        parenthetical = [bok_normalize_keyword_fragment(item) for item in re.findall(r"\(([^)]+)\)", cleaned)]
        plain = bok_normalize_keyword_fragment(re.sub(r"\([^)]*\)", " ", cleaned))
        for candidate in ([plain] if plain else []) + parenthetical:
            if candidate and len(candidate) <= 28 and not bok_keyword_is_noise(candidate):
                candidates.append(candidate)
    if candidates:
        return candidates
    cleaned = bok_normalize_keyword_fragment(normalized)
    if cleaned and len(cleaned) <= 28 and not bok_keyword_is_noise(cleaned):
        return [cleaned]
    return []



def bok_detect_keyword_matches(*texts: str) -> list[str]:
    combined = "\n".join(str(text or "") for text in texts)
    lowered = combined.casefold()
    matches: list[str] = []
    for label, needles in BOK_KEYWORD_MATCHERS:
        if any(needle.casefold() in lowered for needle in needles):
            matches.append(label)
    return matches



def bok_question_bank_keywords(
    page_title: str,
    topic: str,
    *,
    prompt: str = "",
    body: str = "",
    category: str = "",
    question_type: str = "subjective",
) -> list[str]:
    candidates: list[str] = []
    candidates.extend(bok_topic_keyword_candidates(topic))
    candidates.extend(bok_detect_keyword_matches(topic, prompt, body))
    if question_type == "essay":
        candidates.extend(bok_detect_keyword_matches(clean_bok_question_bank_title(page_title), body))
    ordered: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        normalized = bok_normalize_keyword_fragment(item)
        key = normalized.casefold()
        if not normalized or key in seen or bok_keyword_is_noise(normalized):
            continue
        seen.add(key)
        ordered.append(normalized)
    normalized_category = bok_normalize_keyword_fragment(category)
    if normalized_category and normalized_category.casefold() not in seen and not ordered:
        ordered.append(normalized_category)
    return ordered[:6]



def parse_bok_question_bank_entries(
    repo_dir: Path | None = None,
    csv_path: Path = CSV_PATH,
    progress_db_path: Path | None = PROGRESS_DB_PATH,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for source_path in bok_question_bank_source_pages(repo_dir):
        text = source_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if not lines:
            continue
        page_title = clean_bok_question_bank_title(extract_markdown_title(text, source_path.stem))
        heading_snapshots = bok_heading_stack_by_line(lines)
        numbered_headings: list[tuple[int, int, int, str]] = []
        for index, line in enumerate(lines):
            match = BOK_NUMBERED_HEADING_RE.match(line)
            if not match:
                continue
            numbered_headings.append((index, len(match.group(1)), int(match.group(2)), match.group(3).strip()))
        if numbered_headings:
            major_level = min(level for _, level, _, _ in numbered_headings)
            major_sections = [item for item in numbered_headings if item[1] == major_level]
            for offset, (start_index, _level, question_no, topic) in enumerate(major_sections):
                end_index = major_sections[offset + 1][0] if offset + 1 < len(major_sections) else len(lines)
                prompt = lines[start_index].strip()
                body = "\n".join(lines[start_index + 1 : end_index]).strip()
                context_headings = [text for _, text in heading_snapshots.get(start_index, [])[:-1]]
                question_type = infer_bok_question_type(page_title, prompt, body, context_headings)
                field_name = bok_question_bank_field_name(page_title)
                category = infer_question_bank_category(
                    "",
                    topic=topic,
                    prompt=" ".join(part for part in (page_title, *context_headings, prompt) if part).strip(),
                    body="",
                    csv_path=csv_path,
                    progress_db_path=progress_db_path,
                )
                if not category:
                    category = infer_question_bank_category(
                        "",
                        topic=topic,
                        prompt=" ".join(part for part in (page_title, *context_headings, prompt) if part).strip(),
                        body=body,
                        csv_path=csv_path,
                        progress_db_path=progress_db_path,
                    )
                entries.append({
                    "question_type": question_type,
                    "prompt": prompt,
                    "body": body,
                    "answer": "",
                    "explanation": "",
                    "rubric": [],
                    "choices": bok_question_bank_choices(body) if question_type == "multiple_choice" else [],
                    "answer_index": None,
                    "topic": topic,
                    "field_name": field_name,
                    "category": category,
                    "keywords": bok_question_bank_keywords(
                        page_title,
                        topic,
                        prompt=prompt,
                        body=body,
                        category=category,
                        question_type=question_type,
                    ),
                    "difficulty": "",
                    "issuer": "한국은행",
                    "source_location": f"{page_title} · {question_no}. {topic}" if topic else f"{page_title} · {question_no}",
                    "section": bok_question_bank_section_name(field_name, question_type),
                    "points": bok_question_bank_points(question_type),
                    "expected_time_seconds": bok_question_bank_expected_seconds(question_type),
                    "answer_guide": bok_question_bank_answer_guide(question_type),
                    "session_mode": "bok",
                })
            continue
        fallback_topic = bok_fallback_topic(lines, page_title)
        body_start = bok_fallback_body_start(lines)
        body = "\n".join(lines[body_start:]).strip()
        question_type = infer_bok_question_type(page_title, f"### 1. {fallback_topic}", body, [])
        field_name = bok_question_bank_field_name(page_title)
        category = infer_question_bank_category(
            "",
            topic=fallback_topic,
            prompt=f"{page_title} ### 1. {fallback_topic}",
            body="",
            csv_path=csv_path,
            progress_db_path=progress_db_path,
        )
        if not category:
            category = infer_question_bank_category(
                "",
                topic=fallback_topic,
                prompt=f"{page_title} ### 1. {fallback_topic}",
                body=body,
                csv_path=csv_path,
                progress_db_path=progress_db_path,
            )
        entries.append({
            "question_type": question_type,
            "prompt": f"### 1. {fallback_topic}",
            "body": body,
            "answer": "",
            "explanation": "",
            "rubric": [],
            "choices": bok_question_bank_choices(body) if question_type == "multiple_choice" else [],
            "answer_index": None,
            "topic": fallback_topic,
            "field_name": field_name,
            "category": category,
            "keywords": bok_question_bank_keywords(
                page_title,
                fallback_topic,
                prompt=f"### 1. {fallback_topic}",
                body=body,
                category=category,
                question_type=question_type,
            ),
            "difficulty": "",
            "issuer": "한국은행",
            "source_location": f"{page_title} · 1. {fallback_topic}" if fallback_topic else f"{page_title} · 1",
            "section": bok_question_bank_section_name(field_name, question_type),
            "points": bok_question_bank_points(question_type),
            "expected_time_seconds": bok_question_bank_expected_seconds(question_type),
            "answer_guide": bok_question_bank_answer_guide(question_type),
            "session_mode": "bok",
        })
    return entries



def clear_bok_question_bank_entries(
    csv_path: Path = CSV_PATH,
    progress_db_path: Path | None = PROGRESS_DB_PATH,
) -> int:
    db_path = progress_db_for(csv_path, progress_db_path)
    ensure_progress_db(db_path)
    with closing(connect_progress_db(db_path)) as conn:
        count = int(conn.execute(
            "SELECT COUNT(*) FROM question_bank WHERE issuer = ? AND session_mode = ?",
            ("한국은행", "bok"),
        ).fetchone()[0] or 0)
        conn.execute(
            "DELETE FROM question_bank WHERE issuer = ? AND session_mode = ?",
            ("한국은행", "bok"),
        )
        conn.commit()
    return count


def sync_bok_question_bank_entries(
    repo_dir: Path | None = None,
    csv_path: Path = CSV_PATH,
    progress_db_path: Path | None = PROGRESS_DB_PATH,
) -> dict[str, Any]:
    entries = parse_bok_question_bank_entries(repo_dir, csv_path=csv_path, progress_db_path=progress_db_path)
    cleared = clear_bok_question_bank_entries(csv_path, progress_db_path)
    saved = upsert_question_bank_entries(entries, csv_path, progress_db_path)
    return {
        "pages": len(bok_question_bank_source_pages(repo_dir)),
        "cleared": cleared,
        "count": saved.get("count", 0),
        "items": saved.get("items", []),
    }


def question_attempt_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    raw_result = row["is_correct"]
    is_correct = None if raw_result is None else bool(int(raw_result))
    judgment = resolved_question_attempt_judgment(row["judgment"] if "judgment" in row.keys() else None, is_correct)
    return {
        "question_id": row["question_id"],
        "question_bank_id": row["question_bank_id"] if "question_bank_id" in row.keys() else "",
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
        "session_mode": row["session_mode"] if "session_mode" in row.keys() else "practice",
        "section": row["section"] if "section" in row.keys() else "",
        "points": row["points"] if "points" in row.keys() else None,
        "expected_time_seconds": row["expected_time_seconds"] if "expected_time_seconds" in row.keys() else None,
        "answer_guide": row["answer_guide"] if "answer_guide" in row.keys() else "",
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
SELECT question_id, question_bank_id, card_id, question_type, prompt, body, user_answer,
       selected_choice_index, is_correct, judgment, wrong_note, session_id,
       session_title, session_mode, section, points, expected_time_seconds,
       answer_guide, question_order, question_elapsed_seconds,
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
            ORDER BY updated_at DESC, answered_at DESC, question_order DESC, question_id DESC
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
    session_mode = str(payload.session_mode or "practice")[:32] or "practice"
    section = str(payload.section or "")[:64]
    answer_guide = str(payload.answer_guide or "")[:255]
    question_bank_id = str(payload.question_bank_id or "").strip()[:255]
    with closing(connect_progress_db(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO card_progress (card_id, known_status, last_reviewed, review_count, bookmarked, memo, memo_updated_at, updated_at)
            VALUES (?, '', '', 0, 0, '', '', ?)
            ON CONFLICT(card_id) DO NOTHING
            """,
            (payload.card_id, now),
        )
        if question_bank_id:
            linked = conn.execute("SELECT id FROM question_bank WHERE id = ?", (question_bank_id,)).fetchone()
            if linked is None:
                raise ValueError(f"Unknown question_bank_id: {question_bank_id}")
        existing = conn.execute(
            "SELECT created_at, question_started_at FROM question_attempts WHERE question_id = ?",
            (question_id,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO question_attempts (
                question_id, question_bank_id, card_id, question_type, prompt, body,
                user_answer, selected_choice_index, is_correct, judgment, wrong_note,
                session_id, session_title, session_mode, section, points,
                expected_time_seconds, answer_guide, question_order, question_elapsed_seconds,
                session_elapsed_seconds, time_limit_seconds, question_started_at,
                answered_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(question_id) DO UPDATE SET
                question_bank_id = excluded.question_bank_id,
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
                session_mode = excluded.session_mode,
                section = excluded.section,
                points = excluded.points,
                expected_time_seconds = excluded.expected_time_seconds,
                answer_guide = excluded.answer_guide,
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
                question_bank_id or None,
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
                session_mode,
                section,
                payload.points,
                payload.expected_time_seconds,
                answer_guide,
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
            SELECT question_id, question_bank_id, card_id, question_type, prompt, body, user_answer,
                   selected_choice_index, is_correct, judgment, wrong_note, session_id,
                   session_title, session_mode, section, points, expected_time_seconds,
                   answer_guide, question_order, question_elapsed_seconds,
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
        "content_db_path": str(PROGRESS_DB_PATH),
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

def markdown_list_indent(indent: str) -> int:
    return len(str(indent or "").replace("\t", "    "))



def render_markdown_list_block(
    entries: list[dict[str, Any]],
    index: int,
    indent: int,
    repo_dir: Path,
    current_source: Path,
    source_relative: str,
) -> tuple[str, int]:
    first = entries[index]
    tag = str(first.get("tag") or "ul")
    items: list[str] = []
    is_task_list = True

    while index < len(entries):
        entry = entries[index]
        entry_indent = int(entry.get("indent") or 0)
        if entry_indent < indent:
            break
        if entry_indent > indent:
            break
        if str(entry.get("tag") or "ul") != tag:
            break

        body = str(entry.get("body") or "")
        line_number = int(entry.get("line_number") or 0)
        task_item = parse_markdown_task_item(body)
        if task_item:
            item_checked, item_text = task_item
            checked_attr = " checked" if item_checked else ""
            item_class = ' class="wiki-task-item"'
            item_inner = (
                "<label>"
                f"<input type=\"checkbox\" data-wiki-task-checkbox=\"1\" data-wiki-task-source=\"{html.escape(source_relative, quote=True)}\" data-wiki-task-line=\"{line_number}\"{checked_attr} />"
                f"<span>{render_inline_markdown(item_text, repo_dir, current_source)}</span>"
                "</label>"
            )
        else:
            is_task_list = False
            item_class = ""
            item_inner = render_inline_markdown(body.strip(), repo_dir, current_source)

        index += 1
        nested_parts: list[str] = []
        while index < len(entries) and int(entries[index].get("indent") or 0) > indent:
            nested_html, index = render_markdown_list_block(
                entries,
                index,
                int(entries[index].get("indent") or 0),
                repo_dir,
                current_source,
                source_relative,
            )
            nested_parts.append(nested_html)
        items.append(f"<li{item_class}>{item_inner}{''.join(nested_parts)}</li>")

    class_attr = ' class="wiki-task-list"' if items and is_task_list else ""
    return f"<{tag}{class_attr}>" + "".join(items) + f"</{tag}>", index



def render_markdown_list(lines: list[str], line_numbers: list[int], repo_dir: Path, current_source: Path) -> str:
    source_relative = str(current_source.relative_to(repo_dir)).replace(os.sep, "/")
    entries: list[dict[str, Any]] = []
    for line, line_number in zip(lines, line_numbers):
        match = WIKI_LIST_RE.match(line)
        if not match:
            continue
        marker = match.group("marker")
        entries.append({
            "indent": markdown_list_indent(match.group("indent")),
            "tag": "ol" if marker.endswith(".") else "ul",
            "body": match.group("body"),
            "line_number": line_number,
        })
    rendered: list[str] = []
    index = 0
    while index < len(entries):
        block_html, index = render_markdown_list_block(
            entries,
            index,
            int(entries[index].get("indent") or 0),
            repo_dir,
            current_source,
            source_relative,
        )
        rendered.append(block_html)
    return "".join(rendered)


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


def resolve_wiki_markdown_source(source_path: str, repo_dir: Path | None = None) -> tuple[Path, Path, str, str]:
    repo = wiki_book_dir(repo_dir)
    target = safe_wiki_path(repo, source_path)
    if not target or not target.exists() or not target.is_file():
        raise FileNotFoundError(f"Wiki file not found: {source_path}")
    if target.suffix.lower() != ".md":
        raise ValueError(f"Wiki updates support Markdown files only: {source_path}")
    source_relative = str(target.relative_to(repo)).replace(os.sep, "/")
    return repo, target, source_relative, target.read_text(encoding="utf-8")


def synchronized_wiki_source_content(
    source_relative: str,
    local_content: str,
    *,
    mismatch_message: str,
) -> tuple[str, str, str | None]:
    sync_target = wiki_checklist_sync_target()
    current_content = local_content
    remote_sha: str | None = None
    if sync_target == "github":
        remote_content, remote_sha = github_fetch_wiki_source(source_relative)
        if remote_content != local_content:
            raise RuntimeError(mismatch_message)
        current_content = remote_content
    return sync_target, current_content, remote_sha


def update_wiki_checklist_item(
    source_path: str,
    line_number: int,
    checked: bool,
    repo_dir: Path | None = None,
) -> dict[str, Any]:
    repo, target, source_relative, local_content = resolve_wiki_markdown_source(source_path, repo_dir)
    sync_target, current_content, remote_sha = synchronized_wiki_source_content(
        source_relative,
        local_content,
        mismatch_message="GitHub 위키 원본과 현재 배포본이 달라 체크 동기화를 중단했습니다. 위키를 다시 배포한 뒤 재시도하세요.",
    )
    updated_content, task_meta = set_markdown_task_state(current_content, line_number, checked)
    if sync_target == "github" and task_meta["changed"] and remote_sha:
        github_update_wiki_source(
            source_relative,
            updated_content,
            remote_sha,
            f"Toggle wiki checklist: {source_relative}#L{line_number}",
        )
    if updated_content != local_content:
        target.write_text(updated_content, encoding="utf-8")
    return {
        "source_path": source_relative,
        "line_number": line_number,
        "page_slug": wiki_slug_for_source(repo, target),
        "sync_target": sync_target,
        **task_meta,
    }


def update_wiki_page_source(
    source_path: str,
    content: str,
    previous_content: str | None = None,
    repo_dir: Path | None = None,
) -> dict[str, Any]:
    repo, target, source_relative, local_content = resolve_wiki_markdown_source(source_path, repo_dir)
    sync_target, current_content, remote_sha = synchronized_wiki_source_content(
        source_relative,
        local_content,
        mismatch_message="GitHub 위키 원본과 현재 배포본이 달라 문서 저장을 중단했습니다. 위키를 다시 배포한 뒤 재시도하세요.",
    )
    if previous_content is not None and previous_content != current_content:
        raise RuntimeError("문서 원본이 다른 내용으로 바뀌어 저장을 중단했습니다. 문서를 새로고침한 뒤 다시 수정하세요.")
    changed = content != current_content
    if sync_target == "github" and changed and remote_sha:
        github_update_wiki_source(
            source_relative,
            content,
            remote_sha,
            f"Update wiki page: {source_relative}",
        )
    if content != local_content:
        target.write_text(content, encoding="utf-8")
    return {
        "source_path": source_relative,
        "page_slug": wiki_slug_for_source(repo, target),
        "sync_target": sync_target,
        "changed": changed,
        "title": extract_markdown_title(content, target.stem),
    }


def render_wiki_markdown_preview(
    source_path: str,
    content: str,
    repo_dir: Path | None = None,
) -> dict[str, Any]:
    repo, target, source_relative, _ = resolve_wiki_markdown_source(source_path, repo_dir)
    return {
        "source_path": source_relative,
        "page_slug": wiki_slug_for_source(repo, target),
        "title": extract_markdown_title(content, target.stem),
        "html": render_markdown_page(content, repo, target),
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
    linked_cards = linked_cards_for_wiki_page(slug, title, source_relative, csv_path=None, progress_db_path=PROGRESS_DB_PATH)

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


@app.get("/question-bank")
def question_bank_shell() -> FileResponse:
    return FileResponse(STATIC_DIR / "question-bank.html")


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


@app.post("/api/wiki/ai-rewrite/preview")
def api_wiki_ai_rewrite_preview(payload: WikiAiRewriteRequest) -> dict[str, Any]:
    try:
        repo, target, source_relative, _ = resolve_wiki_markdown_source(payload.source_path)
        proposal_content = rewrite_wiki_markdown_with_codex(source_relative, payload.content, payload.instruction)
        return {
            "source_path": source_relative,
            "page_slug": wiki_slug_for_source(repo, target),
            "title": extract_markdown_title(proposal_content, target.stem),
            "model": CODEX_MODEL,
            "proposal": {
                "content": proposal_content,
            },
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc



@app.post("/api/wiki/render-preview")
def api_wiki_render_preview(payload: WikiRenderPreviewRequest) -> dict[str, Any]:
    try:
        return render_wiki_markdown_preview(payload.source_path, payload.content)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.post("/api/wiki/page")
def api_wiki_page_save(payload: WikiPageUpdateRequest) -> dict[str, Any]:
    try:
        updated = update_wiki_page_source(payload.source_path, payload.content, payload.previous_content)
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
        rows, _ = read_cards(csv_path=None, progress_db_path=PROGRESS_DB_PATH)


    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"cards": rows, "summary": summarize(rows)}


@app.post("/api/cards/{card_id}/mark")
def api_mark(card_id: str, payload: MarkRequest) -> dict[str, Any]:
    try:
        card = mark_card(card_id, payload.known_status, csv_path=None, progress_db_path=PROGRESS_DB_PATH)
        rows, _ = read_cards(csv_path=None, progress_db_path=PROGRESS_DB_PATH)


    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"card": card, "summary": summarize(rows)}


@app.post("/api/cards/{card_id}/bookmark")
def api_bookmark(card_id: str, payload: BookmarkRequest) -> dict[str, Any]:
    try:
        card = set_bookmark(card_id, payload.bookmarked, csv_path=None, progress_db_path=PROGRESS_DB_PATH)
        rows, _ = read_cards(csv_path=None, progress_db_path=PROGRESS_DB_PATH)


    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"card": card, "summary": summarize(rows)}


@app.post("/api/cards/{card_id}/memo")
def api_memo(card_id: str, payload: MemoRequest) -> dict[str, Any]:
    try:
        card = save_memo(card_id, payload.memo, csv_path=None, progress_db_path=PROGRESS_DB_PATH)
        rows, _ = read_cards(csv_path=None, progress_db_path=PROGRESS_DB_PATH)


    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"card": card, "summary": summarize(rows)}
@app.post("/api/cards/{card_id}/ai-rewrite/preview")
def api_card_ai_rewrite_preview(card_id: str, payload: CardAiRewriteRequest) -> dict[str, Any]:
    try:
        rows, _ = read_cards(csv_path=None, progress_db_path=PROGRESS_DB_PATH)


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
        card, backup_path = update_card_ai_content(card_id, payload, csv_path=None, backup_dir=BACKUP_DIR, progress_db_path=PROGRESS_DB_PATH)
        rows, _ = read_cards(csv_path=None, progress_db_path=PROGRESS_DB_PATH)


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


@app.post("/api/cards/{card_id}/concept-media")
def api_card_concept_media(card_id: str, payload: CardConceptMediaRequest) -> dict[str, Any]:
    try:
        card, backup_path = update_card_concept_media(card_id, payload, csv_path=None, backup_dir=BACKUP_DIR, progress_db_path=PROGRESS_DB_PATH)
        rows, _ = read_cards(csv_path=None, progress_db_path=PROGRESS_DB_PATH)

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

@app.get("/api/concept-images/{image_name}")
def api_legacy_concept_image_file(image_name: str) -> FileResponse:
    return api_ai_image_file(image_name)


@app.post("/api/cards/{card_id}/ai-image/preview")
def api_card_ai_image_preview(card_id: str) -> dict[str, Any]:
    try:
        rows, _ = read_cards(csv_path=None, progress_db_path=PROGRESS_DB_PATH)


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
            csv_path=None,
            backup_dir=BACKUP_DIR,
            progress_db_path=PROGRESS_DB_PATH,
            image_dir=AI_IMAGE_DIR,
            preview_dir=AI_IMAGE_PREVIEW_DIR,
        )
        rows, _ = read_cards(csv_path=None, progress_db_path=PROGRESS_DB_PATH)


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
        rows, _ = read_cards(csv_path=None, progress_db_path=PROGRESS_DB_PATH)
        generated = generate_questions(
            rows,
            card_ids=payload.card_ids,
            types=payload.types,
            count=payload.count,
            seed=payload.seed,
        )
        return attach_generated_question_bank_ids(generated, rows, csv_path=None, progress_db_path=PROGRESS_DB_PATH)


    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/question-bank")
def api_question_bank_upsert(payload: QuestionBankUpsertRequest) -> dict[str, Any]:
    try:
        return upsert_question_bank_entries(payload.questions, csv_path=None, progress_db_path=PROGRESS_DB_PATH)


    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/question-bank")
def api_question_bank(request: Request) -> dict[str, Any]:
    raw_limit = str(request.query_params.get("limit") or "200").strip()
    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid limit: {raw_limit}") from exc
    try:
        return read_question_bank_entries(
            csv_path=None,
            progress_db_path=PROGRESS_DB_PATH,
            card_id=request.query_params.get("card_id", ""),
            question_type=request.query_params.get("question_type", ""),
            topic=request.query_params.get("topic", ""),
            field_name=request.query_params.get("field_name", request.query_params.get("field", "")),
            category=request.query_params.get("category", request.query_params.get("card_category", "")),
            issuer=request.query_params.get("issuer", ""),
            difficulty=request.query_params.get("difficulty", ""),
            section=request.query_params.get("section", ""),
            source_location=request.query_params.get("source_location", ""),
            query=request.query_params.get("q", request.query_params.get("query", "")),
            limit=limit,
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/questions/attempt")
def api_question_attempt(payload: QuestionAttemptRequest) -> dict[str, Any]:
    try:
        return save_question_attempt(payload, csv_path=None, progress_db_path=PROGRESS_DB_PATH)

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
            csv_path=None,
            progress_db_path=PROGRESS_DB_PATH,
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
        "content_db_path": str(PROGRESS_DB_PATH),
        "content_db_exists": PROGRESS_DB_PATH.exists(),
        "progress_db_path": str(PROGRESS_DB_PATH),
        "progress_db_exists": PROGRESS_DB_PATH.exists(),
        "legacy_bootstrap_csv_path": str(CSV_PATH),
        "legacy_bootstrap_csv_exists": CSV_PATH.exists(),
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
