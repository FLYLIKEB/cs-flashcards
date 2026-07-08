from __future__ import annotations

import base64
import csv
import hmac
import os
import shutil
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
CSV_PATH = Path(os.environ.get("CS_FLASHCARD_CSV", DEFAULT_CSV_PATH)).expanduser().resolve()
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


def read_cards(csv_path: Path = CSV_PATH) -> tuple[list[dict[str, str]], list[str]]:
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
            if not normalized.get("review_count"):
                normalized["review_count"] = "0"
            rows.append(normalized)
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


def mark_card(card_id: str, status: str, csv_path: Path = CSV_PATH, backup_dir: Path = BACKUP_DIR) -> dict[str, str]:
    if status not in VALID_STATUSES:
        raise ValueError("known_status must be O, X, or empty")
    rows, fieldnames = read_cards(csv_path)
    target: dict[str, str] | None = None
    for row in rows:
        if row.get("id") == card_id:
            target = row
            break
    if target is None:
        raise KeyError(card_id)

    target["known_status"] = status
    if status:
        target["last_reviewed"] = utc_now_iso()
        try:
            count = int(target.get("review_count") or "0")
        except ValueError:
            count = 0
        target["review_count"] = str(count + 1)
    else:
        target["last_reviewed"] = ""

    backup_csv(csv_path, backup_dir)
    write_cards(rows, fieldnames, csv_path)
    return target


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
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/cards")
def api_cards() -> dict[str, Any]:
    try:
        rows, _ = read_cards(CSV_PATH)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"cards": rows, "summary": summarize(rows)}


@app.post("/api/cards/{card_id}/mark")
def api_mark(card_id: str, payload: MarkRequest) -> dict[str, Any]:
    try:
        card = mark_card(card_id, payload.known_status, CSV_PATH, BACKUP_DIR)
        rows, _ = read_cards(CSV_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"card": card, "summary": summarize(rows)}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "csv_path": str(CSV_PATH), "csv_exists": CSV_PATH.exists()}
