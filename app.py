from __future__ import annotations

import base64
import csv
from contextlib import closing
import hmac
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DEFAULT_CSV_PATH = ROOT / "data" / "CS_encyclopedia_300plus.csv"
DEFAULT_PROGRESS_DB_PATH = ROOT / "state" / "progress.sqlite"
CSV_PATH = Path(os.environ.get("CS_FLASHCARD_CSV", DEFAULT_CSV_PATH)).expanduser().resolve()
PROGRESS_DB_PATH = Path(os.environ.get("CS_FLASHCARD_PROGRESS_DB", DEFAULT_PROGRESS_DB_PATH)).expanduser().resolve()
BACKUP_DIR = Path(os.environ.get("CS_FLASHCARD_BACKUP_DIR", ROOT / "backups")).expanduser().resolve()
STATIC_DIR = Path(__file__).resolve().parent / "static"
REVIEW_COLUMNS = ["known_status", "last_reviewed", "review_count"]
VALID_STATUSES = {"O", "X", ""}
PUBLIC_USERNAME = os.environ.get("CS_FLASHCARDS_USERNAME", "cs")
PUBLIC_PASSWORD = os.environ.get("CS_FLASHCARDS_PASSWORD", "")

app = FastAPI(title="CS Encyclopedia Flashcards", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class MarkRequest(BaseModel):
    known_status: str = Field(pattern="^(O|X|)$")


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
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_card_progress_status ON card_progress(known_status)")
        if not existed and seed_rows:
            now = utc_now_iso()
            conn.executemany(
                """
                INSERT OR REPLACE INTO card_progress
                    (card_id, known_status, last_reviewed, review_count, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["id"],
                        row.get("known_status") if row.get("known_status") in VALID_STATUSES else "",
                        row.get("last_reviewed") or "",
                        int(normalized_review_count(row.get("review_count"))),
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
            "SELECT card_id, known_status, last_reviewed, review_count FROM card_progress"
        ).fetchall()
    return {
        row["card_id"]: {
            "known_status": row["known_status"] if row["known_status"] in VALID_STATUSES else "",
            "last_reviewed": row["last_reviewed"] or "",
            "review_count": normalized_review_count(str(row["review_count"])),
        }
        for row in rows
    }


def merge_progress(rows: list[dict[str, str]], progress: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    for row in rows:
        item = dict(row)
        item.update(progress.get(row.get("id", ""), {}))
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
            INSERT INTO card_progress (card_id, known_status, last_reviewed, review_count, updated_at)
            VALUES (?, ?, ?, ?, ?)
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


def summarize(rows: list[dict[str, str]]) -> dict[str, Any]:
    total = len(rows)
    known = sum(1 for row in rows if row.get("known_status") == "O")
    unknown = sum(1 for row in rows if row.get("known_status") == "X")
    unreviewed = total - known - unknown
    categories = sorted({row.get("category", "") for row in rows if row.get("category")})
    return {
        "total": total,
        "known": known,
        "unknown": unknown,
        "unreviewed": unreviewed,
        "categories": categories,
        "csv_path": str(CSV_PATH),
        "progress_db_path": str(PROGRESS_DB_PATH),
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


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


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "csv_path": str(CSV_PATH),
        "csv_exists": CSV_PATH.exists(),
        "progress_db_path": str(PROGRESS_DB_PATH),
        "progress_db_exists": PROGRESS_DB_PATH.exists(),
    }
