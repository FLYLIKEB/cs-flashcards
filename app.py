from __future__ import annotations

import base64
import html
import hashlib
import io
import json
import math
import threading
import xml.etree.ElementTree as ET

from contextlib import closing
import hmac
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo
from uuid import uuid4

from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request as UrlRequest, urlopen
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import flashcards_backend

SUPPORTED_QUESTION_TYPES = ("short", "subjective", "multiple_choice", "essay")

_QUESTION_GENERATOR_MODULE: Any | None = None
_PIL_MODULES: tuple[Any, Any, Any] | None = None


def _question_generator_module():
    global _QUESTION_GENERATOR_MODULE
    if _QUESTION_GENERATOR_MODULE is None:
        import question_generator as module

        _QUESTION_GENERATOR_MODULE = module
    return _QUESTION_GENERATOR_MODULE


def generate_questions(*args, **kwargs):
    return _question_generator_module().generate_questions(*args, **kwargs)


def normalize_card_ids(card_ids):
    return _question_generator_module().normalize_card_ids(card_ids)


def _pil_modules() -> tuple[Any, Any, Any]:
    global _PIL_MODULES
    if _PIL_MODULES is None:
        from PIL import Image as image_module
        from PIL import ImageDraw as image_draw_module
        from PIL import ImageFont as image_font_module

        _PIL_MODULES = (image_module, image_draw_module, image_font_module)
    return _PIL_MODULES

ROOT = Path(__file__).resolve().parent
DEFAULT_PROGRESS_DB_PATH = ROOT / "state" / "progress.sqlite"
PROGRESS_DB_PATH = Path(os.environ.get("CS_FLASHCARD_PROGRESS_DB", DEFAULT_PROGRESS_DB_PATH)).expanduser().resolve()
PROGRESS_DB_MUST_EXIST_ENV = "CS_FLASHCARD_PROGRESS_DB_MUST_EXIST"
BACKUP_DIR = Path(os.environ.get("CS_FLASHCARD_BACKUP_DIR", ROOT / "backups")).expanduser().resolve()

STATIC_DIR = Path(__file__).resolve().parent / "static"
PUBLIC_WIKI_ASSET_DIR = STATIC_DIR / "wiki-assets"
PUBLIC_AUTH_BYPASS_PREFIXES = (
    "/public/wiki-assets",
)
DEFAULT_WIKI_BOOK_DIR = ROOT / "wiki_book"
LEGACY_WIKI_BOOK_DIR = ROOT.parent / "wikidocs-ebook"
WIKI_BOOK_DIR = Path(os.environ.get("CS_FLASHCARDS_WIKI_BOOK_DIR", DEFAULT_WIKI_BOOK_DIR)).expanduser().resolve()
WIKI_PAGES_DIRNAME = "pages"
WIKI_TOC_NAME = "TOC.md"
WIKI_BOOK_README_NAME = "README.md"
WIKI_BOOK_HOME_SLUG = "_book"
WIKI_DISPLAY_TIMEZONE = ZoneInfo("Asia/Seoul")

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
QUESTION_BANK_ATTEMPT_FILTER_VALUES = {"", "unseen", "wrong", "correct"}
QUESTION_BANK_ATTEMPT_FILTER_LABELS = {
    "unseen": "안푼",
    "wrong": "틀린",
    "correct": "맞은",
}


PUBLIC_USERNAME = os.environ.get("CS_FLASHCARDS_USERNAME", "cs")
PUBLIC_PASSWORD = os.environ.get("CS_FLASHCARDS_PASSWORD", "")
AUTH_COOKIE_NAME = "cs_flashcards_auth"

def is_public_auth_bypass_path(path: str | None) -> bool:
    raw = str(path or "").strip()
    if not raw:
        return False
    return any(raw == prefix or raw.startswith(f"{prefix}/") for prefix in PUBLIC_AUTH_BYPASS_PREFIXES)
WIKI_GITHUB_REPO = str(os.environ.get("CS_FLASHCARDS_WIKI_GITHUB_REPO", "")).strip()
WIKI_GITHUB_BRANCH = str(os.environ.get("CS_FLASHCARDS_WIKI_GITHUB_BRANCH", "main")).strip() or "main"
WIKI_GITHUB_TOKEN = str(os.environ.get("CS_FLASHCARDS_WIKI_GITHUB_TOKEN", "")).strip()
WIKI_GITHUB_PATH_PREFIX = str(os.environ.get("CS_FLASHCARDS_WIKI_GITHUB_PATH_PREFIX", "")).strip().strip("/")
WIKI_GITHUB_API_BASE = str(os.environ.get("CS_FLASHCARDS_WIKI_GITHUB_API_BASE", "https://api.github.com")).rstrip("/")

CARD_AI_EDITABLE_FIELDS = ("definition", "detailed_explanation", "exam_note", "concept_image_alt")
CONCEPT_MEDIA_TYPES = {"", "image", "gif", "video", "mermaid", "html"}


OPENAI_API_KEY = str(os.environ.get("OPENAI_API_KEY") or os.environ.get("CS_FLASHCARDS_OPENAI_API_KEY") or "").strip()
OPENAI_API_BASE = str(os.environ.get("CS_FLASHCARDS_OPENAI_API_BASE", "https://api.openai.com/v1")).rstrip("/")
CODEX_MODEL = str(os.environ.get("CS_FLASHCARDS_CODEX_MODEL", "codex-mini-latest")).strip() or "codex-mini-latest"
IMAGE_MODEL = str(os.environ.get("CS_FLASHCARDS_IMAGE_MODEL", "gpt-image-2")).strip() or "gpt-image-2"
IMAGE_SIZE = str(os.environ.get("CS_FLASHCARDS_IMAGE_SIZE", "1024x1024")).strip() or "1024x1024"
IMAGE_QUALITY = str(os.environ.get("CS_FLASHCARDS_IMAGE_QUALITY", "low")).strip() or "low"
AI_IMAGE_DIR = Path(os.environ.get("CS_FLASHCARDS_AI_IMAGE_DIR", ROOT / "state" / "ai_images")).expanduser().resolve()
AI_IMAGE_PREVIEW_DIR = Path(os.environ.get("CS_FLASHCARDS_AI_IMAGE_PREVIEW_DIR", ROOT / "state" / "ai_image_previews")).expanduser().resolve()
AI_IMAGE_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{3,254}$")
AI_IMAGE_ARTIFACT_RE = re.compile(
    r"^(?P<card_id>.+)-(?P<stamp>\d{8}-\d{6})-(?P<token>[0-9a-f]{8})\.(?P<ext>png|jpg|jpeg|webp|gif)$",
    re.IGNORECASE,
)
AI_IMAGE_RECOVERY_FIELDS = frozenset({"concept_image_url", "concept_media_type", "concept_media_payload"})
_AI_IMAGE_RECOVERY_GATE_LOCK = threading.Lock()
_AI_IMAGE_RECOVERY_GATE: dict[tuple[str, str], dict[str, Any]] = {}
WIKI_IMAGE_FORMATS = {"png", "svg", "gif"}
WIKI_GENERATED_ASSET_DIR = PurePosixPath("assets/generated-wiki-ai")
WIKI_MARKDOWN_IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<href>[^)\n]+)\)")
WIKI_AI_JOB_STATUS_VALUES = {"queued", "running", "completed", "failed"}
WIKI_AI_JOB_TARGET_VALUES = {"single_image", "single_section", "page_batch"}
WIKI_AI_JOB_LOCK = threading.Lock()
WIKI_AI_JOB_EVENT = threading.Event()
WIKI_AI_WORKER_THREAD: threading.Thread | None = None
WIKI_AI_WORKER_RECOVERY_DONE = False

DEFAULT_RECRUITMENT_SCHEDULE_PATH = ROOT / "data" / "recruitment_schedule_2026.json"
RECRUITMENT_SCHEDULE_PATH = Path(
    os.environ.get("CS_FLASHCARDS_RECRUITMENT_SCHEDULE", DEFAULT_RECRUITMENT_SCHEDULE_PATH)
).expanduser().resolve()
RECRUITMENT_CALENDAR_PATH = "/calendar"
RECRUITMENT_CALENDAR_API_PATH = "/api/calendar/recruitment"
RECRUITMENT_CALENDAR_ICS_PATH = "/api/calendar/recruitment.ics"
RECRUITMENT_SCHEDULE_PAGE_SLUG = "02-01-기본-전제와-일정"
RECRUITMENT_EVENT_TYPE_LABELS = {
    "announcement": "발표",
    "apply": "접수",
    "coding": "코딩시험",
    "exam": "필기",
    "interview": "면접",
    "onboarding": "임용",
    "plan": "계획",
    "result": "발표",
}
RECRUITMENT_EVENT_STATUS_LABELS = {
    "open": "진행 중",
    "planned": "예정",
    "scheduled": "확정",
}


def parse_iso_date(value: str, *, field_name: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Recruitment schedule {field_name} is required")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Invalid recruitment schedule {field_name}: {text}") from exc



def date_to_compact(value: date) -> str:
    return value.strftime("%Y%m%d")



def absolute_url(base_url: str, value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", text):
        return text
    base = str(base_url or "").rstrip("/")
    if not base:
        return text
    return f"{base}{text if text.startswith('/') else '/' + text}"



def google_calendar_template_url(
    *,
    title: str,
    details: str,
    start: date,
    end: date,
    start_time: str = "",
    end_time: str = "",
    timezone_name: str = "Asia/Seoul",
) -> str:
    start_time_text = str(start_time or "").strip()
    end_time_text = str(end_time or "").strip()
    params = {
        "action": "TEMPLATE",
        "text": title,
        "details": details,
    }
    if start_time_text and end_time_text:
        start_dt = combine_event_datetime(start, start_time_text, timezone_name)
        end_dt = combine_event_datetime(end, end_time_text, timezone_name)
        params["dates"] = f"{datetime_to_compact(start_dt)}/{datetime_to_compact(end_dt)}"
        params["ctz"] = timezone_name
    else:
        end_exclusive = end + timedelta(days=1)
        params["dates"] = f"{date_to_compact(start)}/{date_to_compact(end_exclusive)}"
    return f"https://calendar.google.com/calendar/render?{urlencode(params)}"



def ics_escape(text: str) -> str:
    value = str(text or "")
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")



def fold_ics_line(line: str, limit: int = 75) -> list[str]:
    encoded = line.encode("utf-8")
    if len(encoded) <= limit:
        return [line]
    parts: list[str] = []
    current = ""
    for char in line:
        candidate = current + char
        prefix = " " if parts else ""
        if len((prefix + candidate).encode("utf-8")) > limit and current:
            parts.append((" " if parts else "") + current)
            current = char
        else:
            current = candidate
    parts.append((" " if parts else "") + current)
    return parts


def combine_event_datetime(day: date, time_text: str, timezone_name: str) -> datetime:
    clock = datetime.strptime(str(time_text or "").strip(), "%H:%M").time()
    return datetime.combine(day, clock, tzinfo=ZoneInfo(timezone_name))


def datetime_to_compact(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


def datetime_to_ics_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")



def format_markdown_links(links: list[dict[str, Any]]) -> str:
    items: list[str] = []
    for raw in links:
        label = str(raw.get("label") or "").strip()
        url = str(raw.get("url") or "").strip()
        if label and url:
            items.append(f"[{label}]({url})")
    return ", ".join(items)



def format_recruitment_event_date(event: dict[str, Any]) -> str:
    start = parse_iso_date(event.get("start_date", ""), field_name=f"{event.get('id', 'event')} start_date")
    end = parse_iso_date(event.get("end_date", ""), field_name=f"{event.get('id', 'event')} end_date")
    if end < start:
        raise ValueError(f"Recruitment schedule end_date precedes start_date: {event.get('id', '')}")
    precision = str(event.get("date_precision") or "day").strip() or "day"
    start_text = f"{start.month:02d}.{start.day:02d}"
    end_text = f"{end.month:02d}.{end.day:02d}"
    if precision == "month":
        return f"{start.month:02d}월 예정"
    if precision == "window":
        return f"{start.month:02d}~{end.month:02d}월 예정"
    if precision == "approximate_day":
        return f"{start.month:02d}.{start.day:02d} 전후"
    if precision == "range":
        base = f"{start_text} ~ {end_text}"
    else:
        base = start_text
    start_time = str(event.get("start_time") or "").strip()
    end_time = str(event.get("end_time") or "").strip()
    if start_time and end_time:
        if precision == "range":
            return f"{base} ({start_time} ~ {end_time})"
        return f"{base} {start_time} ~ {end_time}"
    return base



def load_recruitment_schedule(path: Path | None = None) -> dict[str, Any]:
    target = Path(path or RECRUITMENT_SCHEDULE_PATH).expanduser().resolve()
    payload = json.loads(target.read_text(encoding="utf-8"))
    if int(payload.get("schema_version") or 0) != 1:
        raise ValueError(f"Unsupported recruitment schedule schema version: {payload.get('schema_version')}")

    institutions: list[dict[str, Any]] = []
    institutions_by_id: dict[str, dict[str, Any]] = {}
    for raw in payload.get("institutions") or []:
        item = {
            "id": str(raw.get("id") or "").strip(),
            "name": str(raw.get("name") or "").strip(),
            "short_name": str(raw.get("short_name") or raw.get("name") or "").strip(),
            "color": str(raw.get("color") or "#334155").strip() or "#334155",
        }
        if not item["id"] or not item["name"]:
            raise ValueError("Recruitment schedule institutions require id and name")
        institutions.append(item)
        institutions_by_id[item["id"]] = item

    def normalize_entry(raw: dict[str, Any]) -> dict[str, Any]:
        institution_id = str(raw.get("institution_id") or "").strip()
        institution = institutions_by_id.get(institution_id)
        if not institution:
            raise ValueError(f"Unknown recruitment schedule institution_id: {institution_id}")
        return {
            **raw,
            "institution_id": institution_id,
            "institution_name": institution["name"],
            "institution_short_name": institution["short_name"],
            "institution_color": institution["color"],
        }

    timeline = [dict(item) for item in payload.get("timeline") or []]
    dashboard_open = [normalize_entry(dict(item)) for item in payload.get("dashboard_open") or []]
    dashboard_watch = [normalize_entry(dict(item)) for item in payload.get("dashboard_watch") or []]

    priorities: list[dict[str, Any]] = []
    for raw in payload.get("priorities") or []:
        item = dict(raw)
        institution_id = str(item.get("institution_id") or "").strip()
        if institution_id:
            institution = institutions_by_id.get(institution_id)
            if not institution:
                raise ValueError(f"Unknown recruitment schedule priority institution_id: {institution_id}")
            item["institution_name"] = institution["name"]
        priorities.append(item)

    events: list[dict[str, Any]] = []
    for raw in payload.get("events") or []:
        event = normalize_entry(dict(raw))
        start = parse_iso_date(event.get("start_date", ""), field_name=f"{event.get('id', 'event')} start_date")
        end = parse_iso_date(event.get("end_date", ""), field_name=f"{event.get('id', 'event')} end_date")
        if end < start:
            raise ValueError(f"Recruitment schedule end_date precedes start_date: {event.get('id', '')}")
        event["start_date"] = start.isoformat()
        event["end_date"] = end.isoformat()
        event["date_display"] = format_recruitment_event_date(event)
        event["event_type_label"] = RECRUITMENT_EVENT_TYPE_LABELS.get(str(event.get("event_type") or "").strip(), "일정")
        event["status_label"] = RECRUITMENT_EVENT_STATUS_LABELS.get(str(event.get("status") or "").strip(), "확인 필요")
        event["date_precision"] = str(event.get("date_precision") or "day").strip() or "day"
        event["display_label"] = str(event.get("display_label") or event["event_type_label"]).strip() or event["event_type_label"]
        events.append(event)
    events.sort(key=lambda item: (item["start_date"], item["end_date"], str(item.get("title") or "")))

    return {
        "schema_version": 1,
        "title": str(payload.get("title") or "2026 금융공기업 IT 채용 캘린더").strip(),
        "timezone": str(payload.get("timezone") or "Asia/Seoul").strip() or "Asia/Seoul",
        "last_updated": str(payload.get("last_updated") or "").strip(),
        "description": str(payload.get("description") or "").strip(),
        "calendar_intro": str(payload.get("calendar_intro") or "").strip(),
        "calendar_notes": [str(item).strip() for item in payload.get("calendar_notes") or [] if str(item).strip()],
        "institutions": institutions,
        "timeline": timeline,
        "dashboard_open": dashboard_open,
        "dashboard_watch": dashboard_watch,
        "priorities": priorities,
        "events": events,
    }



def recruitment_event_details(event: dict[str, Any], *, base_url: str = "") -> str:
    details = [
        f"기관: {event['institution_name']}",
        f"일정: {event['date_display']}",
        f"유형: {event['event_type_label']}",
        f"상태: {event['status_label']}",
    ]
    summary = str(event.get("summary") or "").strip()
    if summary:
        details.append(f"공고: {summary}")
    description = str(event.get("description") or "").strip()
    if description:
        details.append(description)
    url = absolute_url(base_url, str(event.get("url") or "").strip())
    if url:
        details.append(f"공고 링크: {url}")
    ics_url = absolute_url(base_url, RECRUITMENT_CALENDAR_ICS_PATH)
    if ics_url:
        details.append(f"전체 ICS 피드: {ics_url}")
    return "\n".join(details)



def build_recruitment_calendar_payload(*, base_url: str = "") -> dict[str, Any]:
    schedule = load_recruitment_schedule()
    open_count = 0
    exact_count = 0
    planned_count = 0
    timezone_name = schedule["timezone"]
    events: list[dict[str, Any]] = []
    for event in schedule["events"]:
        start = parse_iso_date(event["start_date"], field_name=f"{event['id']} start_date")
        end = parse_iso_date(event["end_date"], field_name=f"{event['id']} end_date")
        start_time = str(event.get("start_time") or "").strip()
        end_time = str(event.get("end_time") or "").strip()
        has_time = bool(start_time and end_time)
        if has_time:
            start_value = combine_event_datetime(start, start_time, timezone_name).isoformat()
            end_value = combine_event_datetime(end, end_time, timezone_name).isoformat()
        else:
            start_value = start.isoformat()
            end_value = (end + timedelta(days=1)).isoformat()
        if event["status"] == "open":
            open_count += 1
        if event["status"] == "planned":
            planned_count += 1
        if event["date_precision"] in {"day", "range"}:
            exact_count += 1
        details = recruitment_event_details(event, base_url=base_url)
        calendar_title = f"{event['institution_name']} · {event['display_label']}"
        events.append(
            {
                "id": event["id"],
                "title": calendar_title,
                "list_title": str(event.get("title") or calendar_title),
                "summary": str(event.get("summary") or "").strip(),
                "display_label": str(event.get("display_label") or event["event_type_label"]),
                "event_type": event["event_type"],
                "event_type_label": event["event_type_label"],
                "status": event["status"],
                "status_label": event["status_label"],
                "date_precision": event["date_precision"],
                "date_display": event["date_display"],
                "start": start_value,
                "end": end_value,
                "start_inclusive": start.isoformat(),
                "end_inclusive": end.isoformat(),
                "start_time": start_time,
                "end_time": end_time,
                "allDay": not has_time,
                "description": str(event.get("description") or "").strip(),
                "details": details,
                "url": absolute_url(base_url, str(event.get("url") or "").strip()),
                "source_label": str(event.get("source_label") or "").strip(),
                "is_approximate": event["date_precision"] in {"approximate_day", "month", "window"},
                "google_calendar_url": google_calendar_template_url(
                    title=calendar_title,
                    details=details,
                    start=start,
                    end=end,
                    start_time=start_time,
                    end_time=end_time,
                    timezone_name=timezone_name,
                ),
                "institution": {
                    "id": event["institution_id"],
                    "name": event["institution_name"],
                    "short_name": event["institution_short_name"],
                    "color": event["institution_color"],
                },
                "backgroundColor": event["institution_color"],
                "borderColor": event["institution_color"],
                "textColor": "#0f172a",
                "extendedProps": {
                    "status": event["status"],
                    "status_label": event["status_label"],
                    "date_precision": event["date_precision"],
                    "event_type": event["event_type"],
                    "event_type_label": event["event_type_label"],
                    "institution_id": event["institution_id"],
                    "institution_name": event["institution_name"],
                    "institution_short_name": event["institution_short_name"],
                    "start_time": start_time,
                    "end_time": end_time,
                    "url": absolute_url(base_url, str(event.get("url") or "").strip()),
                    "details": details,
                },
            }
        )

    def normalize_dashboard(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for raw in items:
            normalized.append(
                {
                    "institution": {
                        "id": raw["institution_id"],
                        "name": raw["institution_name"],
                        "short_name": raw["institution_short_name"],
                        "color": raw["institution_color"],
                    },
                    "status": str(raw.get("status") or "").strip(),
                    "schedule_summary": str(raw.get("schedule_summary") or "").strip(),
                    "links": [
                        {"label": str(link.get("label") or "").strip(), "url": absolute_url(base_url, str(link.get("url") or "").strip())}
                        for link in raw.get("links") or []
                        if str(link.get("label") or "").strip() and str(link.get("url") or "").strip()
                    ],
                    "note": str(raw.get("note") or "").strip(),
                }
            )
        return normalized

    return {
        "calendar": {
            "title": schedule["title"],
            "description": schedule["description"],
            "last_updated": schedule["last_updated"],
            "timezone": schedule["timezone"],
            "calendar_path": RECRUITMENT_CALENDAR_PATH,
            "api_path": RECRUITMENT_CALENDAR_API_PATH,
            "ics_path": RECRUITMENT_CALENDAR_ICS_PATH,
            "ics_url": absolute_url(base_url, RECRUITMENT_CALENDAR_ICS_PATH),
            "calendar_url": absolute_url(base_url, RECRUITMENT_CALENDAR_PATH),
            "notes": schedule["calendar_notes"],
            "intro": schedule["calendar_intro"],
        },
        "counts": {
            "total_events": len(events),
            "open_events": open_count,
            "exact_events": exact_count,
            "planned_events": planned_count,
            "watch_only_institutions": len(schedule["dashboard_watch"]),
        },
        "institutions": schedule["institutions"],
        "timeline": schedule["timeline"],
        "dashboard": {
            "open": normalize_dashboard(schedule["dashboard_open"]),
            "watch": normalize_dashboard(schedule["dashboard_watch"]),
            "priorities": schedule["priorities"],
        },
        "events": events,
    }



def build_recruitment_calendar_ics(*, base_url: str = "") -> str:
    schedule = load_recruitment_schedule()
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    timezone_name = schedule["timezone"]
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CS Flashcards//Recruitment Calendar//KO",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{ics_escape(schedule['title'])}",
        f"X-WR-CALDESC:{ics_escape(schedule['description'])}",
    ]
    for event in schedule["events"]:
        start = parse_iso_date(event["start_date"], field_name=f"{event['id']} start_date")
        end = parse_iso_date(event["end_date"], field_name=f"{event['id']} end_date")
        start_time = str(event.get("start_time") or "").strip()
        end_time = str(event.get("end_time") or "").strip()
        details = recruitment_event_details(event, base_url=base_url)
        body = [
            "BEGIN:VEVENT",
            f"UID:{ics_escape(event['id'])}@cs-flashcards",
            f"DTSTAMP:{now}",
        ]
        if start_time and end_time:
            body.extend(
                [
                    f"DTSTART:{datetime_to_ics_utc(combine_event_datetime(start, start_time, timezone_name))}",
                    f"DTEND:{datetime_to_ics_utc(combine_event_datetime(end, end_time, timezone_name))}",
                ]
            )
        else:
            body.extend(
                [
                    f"DTSTART;VALUE=DATE:{date_to_compact(start)}",
                    f"DTEND;VALUE=DATE:{date_to_compact(end + timedelta(days=1))}",
                ]
            )
        body.extend(
            [
                f"SUMMARY:{ics_escape(event['institution_name'] + ' · ' + str(event.get('display_label') or event['event_type_label']))}",
                f"DESCRIPTION:{ics_escape(details)}",
                f"STATUS:{'TENTATIVE' if event['status'] == 'planned' or event['date_precision'] in {'approximate_day', 'month', 'window'} else 'CONFIRMED'}",
            ]
        )
        url = absolute_url(base_url, str(event.get("url") or "").strip())
        if url:
            body.append(f"URL:{ics_escape(url)}")
        body.append("END:VEVENT")
        for line in body:
            lines.extend(fold_ics_line(line))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"



def render_recruitment_schedule_section_two(schedule: dict[str, Any]) -> str:
    lines = [
        "## 2. 현재 기준 일정",
        "",
        f"> [채용 캘린더 보기]({RECRUITMENT_CALENDAR_PATH}) · [ICS 피드]({RECRUITMENT_CALENDAR_ICS_PATH}) · Google Calendar는 ICS URL을 \"URL로 추가\"해서 구독",
        "",
        "| 시기 | 현재 확정/공개 상태 | 준비 초점 |",
        "|---|---|---|",
    ]
    for item in schedule["timeline"]:
        lines.append(f"| {item['period']} | {item['headline']} | {item['focus']} |")
    return "\n".join(lines)



def render_recruitment_schedule_section_five(schedule: dict[str, Any]) -> str:
    lines = [
        "## 5. 기관별 채용 일정 대시보드",
        "",
        f"> 마지막 업데이트: {schedule['last_updated']}. 현재 살아 있는 2026년 기준 공고·예비공고·채용계획·공식 채용페이지만 남겼다.",
        "",
        "### 5-1. 현재 열려 있거나 일정이 공개된 공고",
        "",
        "| 기관 | 현재 상태 | 2026 일정 | 공고 링크 | 비고 |",
        "|---|---|---|---|---|",
    ]
    for item in schedule["dashboard_open"]:
        lines.append(
            f"| **{item['institution_name']}** | **{item.get('status', '')}** | {item.get('schedule_summary', '')} | {format_markdown_links(item.get('links') or [])} | {item.get('note', '')} |"
        )
    lines.extend(
        [
            "",
            "### 5-2. 2026 하반기 신입공고 아직 미확인인 기관",
            "",
            f"| 기관 | {schedule['last_updated'].replace('-', '.')} 현재 상태 | 확인 링크 | 메모 |",
            "|---|---|---|---|",
        ]
    )
    for item in schedule["dashboard_watch"]:
        lines.append(
            f"| **{item['institution_name']}** | {item.get('status', '')} | {format_markdown_links(item.get('links') or [])} | {item.get('note', '')} |"
        )
    lines.extend(
        [
            "",
            "### 5-3. 지금 우선순위 한눈에 보기",
            "",
            "| 우선순위 | 기관 | 이유 |",
            "|---:|---|---|",
        ]
    )
    for item in schedule["priorities"]:
        label = str(item.get("institution_name") or item.get("institution_group") or "").strip()
        lines.append(f"| {int(item.get('rank') or 0)} | **{label}** | {item.get('reason', '')} |")
    lines.extend(
        [
            "",
            "### 5-4. 캘린더/구독 링크",
            "",
            f"- [앱 내부 채용 캘린더 열기]({RECRUITMENT_CALENDAR_PATH})",
            f"- [ICS 피드 열기]({RECRUITMENT_CALENDAR_ICS_PATH})",
            "- Google Calendar에서는 `다른 캘린더 추가 → URL로 추가`에 ICS 링크를 넣어 구독하면 된다.",
        ]
    )
    return "\n".join(lines)



def replace_markdown_section(markdown_text: str, start_heading: str, next_heading: str, replacement: str) -> str:
    pattern = re.compile(rf"{re.escape(start_heading)}\n.*?(?=\n{re.escape(next_heading)}\n)", re.S)
    updated, count = pattern.subn(replacement.rstrip(), str(markdown_text or ""), count=1)
    if count != 1:
        raise ValueError(f"Failed to replace markdown section: {start_heading}")
    return updated



def render_recruitment_schedule_wiki_page(markdown_text: str) -> str:
    schedule = load_recruitment_schedule()
    updated = replace_markdown_section(
        markdown_text,
        "## 2. 현재 기준 일정",
        "## 3. 전체 시간 배분",
        render_recruitment_schedule_section_two(schedule),
    )
    updated = replace_markdown_section(
        updated,
        "## 5. 기관별 채용 일정 대시보드",
        "## 약어 풀이",
        render_recruitment_schedule_section_five(schedule),
    )
    return updated





app = FastAPI(title="CS Encyclopedia Flashcards", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR, check_dir=False), name="static")
app.mount("/public/wiki-assets", StaticFiles(directory=PUBLIC_WIKI_ASSET_DIR, check_dir=False), name="public-wiki-assets")


@app.on_event("startup")
def startup_background_workers() -> None:
    ensure_wiki_ai_worker_started()


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
    card_id: str = Field(default="", max_length=255)
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


class QuestionBankAttemptQueryRequest(BaseModel):
    question_bank_ids: list[str] | None = Field(default=None, max_length=500)
    result: str = Field(default="all", max_length=32)
    limit: int = Field(default=200, ge=1, le=500)

class WikiChecklistRequest(BaseModel):
    source_path: str = Field(min_length=1, max_length=4096)
    line_number: int = Field(ge=1, le=200000)
    checked: bool
    previous_content: str | None = Field(default=None, max_length=2_000_000)



class WikiGithubArchiveRequest(BaseModel):
    source_path: str | None = Field(default=None, max_length=4096)

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


class WikiImageRegenerateRequest(BaseModel):
    source_path: str = Field(min_length=1, max_length=4096)
    image_index: int = Field(ge=0, le=20000)
    format: str = Field(default="png", max_length=16)
    prompt_override: str = Field(default="", max_length=20000)


class WikiSectionImageGenerateRequest(BaseModel):
    source_path: str = Field(min_length=1, max_length=4096)
    section_index: int = Field(ge=0, le=20000)
    format: str = Field(default="png", max_length=16)
    prompt_override: str = Field(default="", max_length=20000)


class WikiAiJobCreateRequest(BaseModel):
    source_paths: list[str] = Field(min_length=1, max_length=200)
    format: str = Field(default="png", max_length=16)
    prompt_template: str = Field(default="", max_length=20000)
    include_existing_images: bool = True
    include_sections: bool = True
    target: str = Field(default="page_batch", max_length=32)
    image_index: int | None = Field(default=None, ge=0, le=20000)
    section_index: int | None = Field(default=None, ge=0, le=20000)


class CardAiRewriteRequest(BaseModel):
    instruction: str = Field(default="", max_length=4000)


class CardAiApplyRequest(BaseModel):
    definition: str | None = Field(default=None, max_length=12000)
    detailed_explanation: str | None = Field(default=None, max_length=50000)
    exam_note: str | None = Field(default=None, max_length=20000)
    concept_image_alt: str | None = Field(default=None, max_length=4000)


class QuestionBankAiRefineRequest(BaseModel):
    instruction: str = Field(default="", max_length=4000)


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
    if is_public_auth_bypass_path(request.url.path):
        return await call_next(request)
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


def wiki_last_modified_metadata(path: Path) -> tuple[str, str]:
    updated = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone(WIKI_DISPLAY_TIMEZONE)
    return updated.isoformat(timespec="seconds"), updated.strftime("%Y-%m-%d %H:%M")



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


def progress_db_for(progress_db_path: Path | None = None) -> Path:
    if progress_db_path is not None:
        return progress_db_path.expanduser().resolve()
    return PROGRESS_DB_PATH





def progress_row_is_meaningful(row: dict[str, str]) -> bool:
    return bool(
        row.get("known_status") in {"O", "X"}
        or (row.get("last_reviewed") or "").strip()
        or int(normalized_review_count(row.get("review_count"))) > 0
        or normalized_bookmarked(row.get("bookmarked")) == "1"
        or (row.get("memo") or "").strip()
    )

def normalized_runtime_media_url(value: Any) -> str:
    return str(value or "").strip()
def normalized_concept_media_type(value: Any) -> str:
    media_type = str(value or "").strip().lower()
    if media_type not in CONCEPT_MEDIA_TYPES:
        raise ValueError("지원하지 않는 개념 미디어 형식입니다.")
    return media_type


def progress_db_must_exist() -> bool:
    return str(os.environ.get(PROGRESS_DB_MUST_EXIST_ENV, "")).strip() == "1"


def progress_db_not_found_error(progress_db_path: Path) -> FileNotFoundError:
    return FileNotFoundError(f"Progress DB not found: {progress_db_path}")


def connect_progress_db(progress_db_path: Path, *, must_exist: bool = False) -> sqlite3.Connection:
    return flashcards_backend.connect_progress_db(
        progress_db_path,
        must_exist=(must_exist or progress_db_must_exist()),
        not_found_error_factory=progress_db_not_found_error,
    )



def _ensure_question_attempts_nullable_card_id(conn: sqlite3.Connection) -> None:
    columns = conn.execute("PRAGMA table_info(question_attempts)").fetchall()
    card_id_column = next((row for row in columns if row["name"] == "card_id"), None)
    if card_id_column is None or not int(card_id_column["notnull"] or 0):
        return
    conn.commit()
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute(
            """
            CREATE TABLE question_attempts__migrated (
                question_id TEXT PRIMARY KEY,
                question_bank_id TEXT,
                card_id TEXT,
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
        conn.execute(
            """
            INSERT INTO question_attempts__migrated (
                question_id, question_bank_id, card_id, question_type, prompt, body,
                user_answer, selected_choice_index, is_correct, judgment, wrong_note,
                session_id, session_title, session_mode, section, points,
                expected_time_seconds, answer_guide, question_order,
                question_elapsed_seconds, session_elapsed_seconds, time_limit_seconds,
                question_started_at, answered_at, created_at, updated_at
            )
            SELECT
                question_id,
                question_bank_id,
                NULLIF(TRIM(COALESCE(card_id, '')), ''),
                question_type,
                prompt,
                body,
                user_answer,
                selected_choice_index,
                is_correct,
                judgment,
                wrong_note,
                session_id,
                session_title,
                session_mode,
                section,
                points,
                expected_time_seconds,
                answer_guide,
                question_order,
                question_elapsed_seconds,
                session_elapsed_seconds,
                time_limit_seconds,
                question_started_at,
                answered_at,
                created_at,
                updated_at
            FROM question_attempts
            """
        )
        conn.execute("DROP TABLE question_attempts")
        conn.execute("ALTER TABLE question_attempts__migrated RENAME TO question_attempts")
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def _drop_empty_card_progress_sentinel(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        DELETE FROM card_progress
        WHERE card_id = ''
          AND COALESCE(known_status, '') = ''
          AND COALESCE(last_reviewed, '') = ''
          AND COALESCE(review_count, 0) = 0
          AND COALESCE(bookmarked, 0) = 0
          AND COALESCE(memo, '') = ''
          AND COALESCE(memo_updated_at, '') = ''
        """
    )



def ensure_progress_db(
    progress_db_path: Path,
    seed_rows: list[dict[str, Any]] | None = None,
    *,
    must_exist: bool = False,
) -> None:
    with closing(connect_progress_db(progress_db_path, must_exist=must_exist)) as conn:
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
                missing_card_keywords_json TEXT NOT NULL DEFAULT '[]',
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
            "missing_card_keywords_json": "TEXT NOT NULL DEFAULT '[]'",
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
        backfill_question_bank_difficulty_rows(conn)


        summary_table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'question_attempt_card_summary'"
        ).fetchone() is not None
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS question_attempts (
                question_id TEXT PRIMARY KEY,
                question_bank_id TEXT,
                card_id TEXT,
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
        _ensure_question_attempts_nullable_card_id(conn)
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
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_question_attempts_bank_latest
            ON question_attempts(question_bank_id, updated_at DESC, created_at DESC, question_id DESC)
            WHERE TRIM(COALESCE(question_bank_id, '')) <> ''
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_question_attempts_result ON question_attempts(is_correct)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_question_attempts_session_id ON question_attempts(session_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS question_attempt_card_summary (
                card_id TEXT PRIMARY KEY,
                question_attempt_count INTEGER NOT NULL DEFAULT 0,
                question_correct_count INTEGER NOT NULL DEFAULT 0,
                question_wrong_count INTEGER NOT NULL DEFAULT 0,
                latest_wrong_note TEXT NOT NULL DEFAULT '',
                latest_wrong_note_updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        if not summary_table_exists:
            _rebuild_question_attempt_card_summary_cache(conn)
        _drop_empty_card_progress_sentinel(conn)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS wiki_ai_jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed')),
                target TEXT NOT NULL DEFAULT 'page_batch' CHECK (target IN ('single_image', 'single_section', 'page_batch')),
                source_paths_json TEXT NOT NULL DEFAULT '[]',
                format TEXT NOT NULL DEFAULT 'png',
                prompt_template TEXT NOT NULL DEFAULT '',
                include_existing_images INTEGER NOT NULL DEFAULT 0 CHECK (include_existing_images IN (0, 1)),
                include_sections INTEGER NOT NULL DEFAULT 0 CHECK (include_sections IN (0, 1)),
                image_index INTEGER,
                section_index INTEGER,
                queued_targets INTEGER NOT NULL DEFAULT 0 CHECK (queued_targets >= 0),
                processed_targets INTEGER NOT NULL DEFAULT 0 CHECK (processed_targets >= 0),
                requested_at TEXT NOT NULL,
                started_at TEXT NOT NULL DEFAULT '',
                completed_at TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wiki_ai_jobs_status_requested ON wiki_ai_jobs(status, requested_at)")

        initial_rows = seed_rows or []

        if initial_rows:
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
                        int(row.get("sort_order") if row.get("sort_order") is not None else index),
                        now,
                    )
                    for index, row in enumerate(initial_rows)
                    if row.get("id")
                ],
            )
        if initial_rows:
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
                    for row in initial_rows
                    if row.get("id") and progress_row_is_meaningful(row)
                ],
            )

        conn.commit()



def progress_db_runtime_summary(progress_db_path: Path | None = None) -> dict[str, Any]:
    db_path = progress_db_for(progress_db_path)
    summary = {
        "path": str(db_path),
        "exists": db_path.exists(),
        "readable": False,
        "content_card_count": 0,
        "question_bank_count": 0,
        "question_attempt_count": 0,
        "wiki_ai_job_queue_count": 0,
        "wiki_ai_job_running_count": 0,
        "wiki_ai_job_failed_count": 0,
        "error": "",
    }
    if not summary["exists"]:
        summary["error"] = str(progress_db_not_found_error(db_path))
        summary["ok"] = False
        return summary
    try:
        ensure_progress_db(db_path, must_exist=True)
        with closing(connect_progress_db(db_path, must_exist=True)) as conn:
            table_names = {
                str(row["name"])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
            if "cards" in table_names:
                summary["content_card_count"] = int(conn.execute("SELECT COUNT(*) AS count FROM cards").fetchone()["count"] or 0)
            if "question_bank" in table_names:
                summary["question_bank_count"] = int(conn.execute("SELECT COUNT(*) AS count FROM question_bank").fetchone()["count"] or 0)
            if "question_attempts" in table_names:
                summary["question_attempt_count"] = int(conn.execute("SELECT COUNT(*) AS count FROM question_attempts").fetchone()["count"] or 0)
            if "wiki_ai_jobs" in table_names:
                job_counts = conn.execute(
                    """
                    SELECT
                        SUM(CASE WHEN status = 'queued' THEN 1 ELSE 0 END) AS queued_count,
                        SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running_count,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count
                    FROM wiki_ai_jobs
                    """
                ).fetchone()
                summary["wiki_ai_job_queue_count"] = int(job_counts["queued_count"] or 0) if job_counts else 0
                summary["wiki_ai_job_running_count"] = int(job_counts["running_count"] or 0) if job_counts else 0
                summary["wiki_ai_job_failed_count"] = int(job_counts["failed_count"] or 0) if job_counts else 0
        summary["readable"] = True
    except (FileNotFoundError, sqlite3.Error) as exc:
        summary["error"] = str(exc)
    summary["ok"] = bool(summary["exists"] and summary["readable"] and summary["content_card_count"] > 0)
    return summary



def read_progress(progress_db_path: Path) -> dict[str, dict[str, str]]:
    ensure_progress_db(progress_db_path, must_exist=True)
    select_fields = ["card_id", "known_status", "last_reviewed", "review_count", "bookmarked", "memo", "memo_updated_at"]
    with closing(connect_progress_db(progress_db_path, must_exist=True)) as conn:
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
    ensure_progress_db(progress_db_path, must_exist=True)
    select_fields = ["card_id", *CARD_CONTENT_DB_COLUMNS]
    with closing(connect_progress_db(progress_db_path, must_exist=True)) as conn:
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



def read_cards(progress_db_path: Path | None = None) -> tuple[list[dict[str, str]], list[str]]:
    db_path = progress_db_for(progress_db_path)
    ensure_progress_db(db_path, must_exist=True)
    sync_ai_image_files_to_db(db_path)
    card_rows, fieldnames = read_card_content(db_path)
    if not card_rows:
        raise FileNotFoundError(f"Card content not found in SQLite: {db_path}")
    rows = merge_progress(card_rows, read_progress(db_path), read_question_attempt_stats(db_path))
    return rows, fieldnames

def read_card(progress_db_path: Path | None, card_id: Any) -> dict[str, Any]:
    normalized_card_id = normalize_question_bank_text(card_id, limit=255)
    if not normalized_card_id:
        raise KeyError(card_id)
    db_path = progress_db_for(progress_db_path)
    ensure_progress_db(db_path, must_exist=True)
    sync_ai_image_files_to_db(db_path)
    select_fields = ["card_id", *CARD_CONTENT_DB_COLUMNS]
    with closing(connect_progress_db(db_path, must_exist=True)) as conn:
        row = conn.execute(
            f"SELECT {', '.join(select_fields)} FROM cards WHERE card_id = ?",
            (normalized_card_id,),
        ).fetchone()
        if row is None:
            raise KeyError(normalized_card_id)
        item = {"id": row["card_id"] or ""}
        for field in CARD_CONTENT_DB_COLUMNS:
            item[field] = row[field] or ""
        item["concept_image_url"] = normalized_runtime_media_url(item.get("concept_image_url"))
        media_type = normalized_concept_media_type(item.get("concept_media_type")) if item.get("concept_media_type") else ""
        if media_type in {"image", "gif", "video"}:
            item["concept_media_payload"] = normalized_runtime_media_url(item.get("concept_media_payload"))
        progress_row = conn.execute(
            """
            SELECT known_status, last_reviewed, review_count, bookmarked, memo, memo_updated_at
            FROM card_progress
            WHERE card_id = ?
            """,
            (normalized_card_id,),
        ).fetchone()
        if progress_row is not None:
            item.update({
                "known_status": progress_row["known_status"] if progress_row["known_status"] in VALID_STATUSES else "",
                "last_reviewed": progress_row["last_reviewed"] or "",
                "review_count": normalized_review_count(str(progress_row["review_count"])),
                "bookmarked": normalized_bookmarked(progress_row["bookmarked"]),
                "memo": progress_row["memo"] or "",
                "memo_updated_at": progress_row["memo_updated_at"] or "",
            })
        summary = _question_attempt_summary_dict(
            conn.execute(
                """
                SELECT
                    question_attempt_count,
                    question_correct_count,
                    question_wrong_count,
                    latest_wrong_note,
                    latest_wrong_note_updated_at
                FROM question_attempt_card_summary
                WHERE card_id = ?
                """,
                (normalized_card_id,),
            ).fetchone()
        )
    item["known_status"] = item.get("known_status") or ""
    item["last_reviewed"] = item.get("last_reviewed") or ""
    item["review_count"] = normalized_review_count(item.get("review_count"))
    item["bookmarked"] = normalized_bookmarked(item.get("bookmarked"))
    item["memo"] = item.get("memo") or ""
    item["memo_updated_at"] = item.get("memo_updated_at") or ""
    item.update(summary)

    return item

def read_card_attempt_context(progress_db_path: Path | None, card_ids: list[str] | None) -> dict[str, dict[str, str]]:
    normalized_ids = sorted(normalize_card_ids(card_ids) or [])
    if not normalized_ids:
        return {}
    db_path = progress_db_for(progress_db_path)
    ensure_progress_db(db_path, must_exist=True)
    placeholders = ", ".join(["?"] * len(normalized_ids))
    with closing(connect_progress_db(db_path, must_exist=True)) as conn:
        rows = conn.execute(
            f"""
            SELECT card_id, term, english, category
            FROM cards
            WHERE card_id IN ({placeholders})
            """,
            tuple(normalized_ids),
        ).fetchall()
    return {
        str(row["card_id"] or "").strip(): {
            "id": str(row["card_id"] or "").strip(),
            "term": row["term"] or "",
            "english": row["english"] or "",
            "category": row["category"] or "",
        }
        for row in rows
        if str(row["card_id"] or "").strip()
    }




def _ai_image_recovery_root(image_dir: Path | None = None) -> Path:
    return (image_dir or AI_IMAGE_DIR).expanduser().resolve()


def _ai_image_recovery_dir_stamp(image_dir: Path | None = None) -> tuple[bool, int]:
    root = _ai_image_recovery_root(image_dir)
    if not root.exists() or not root.is_dir():
        return False, 0
    return True, root.stat().st_mtime_ns


def mark_ai_image_recovery_dirty(progress_db_path: Path, image_dir: Path | None = None) -> None:
    key = (str(progress_db_for(progress_db_path)), str(_ai_image_recovery_root(image_dir)))
    with _AI_IMAGE_RECOVERY_GATE_LOCK:
        state = _AI_IMAGE_RECOVERY_GATE.get(key)
        if state is None:
            _AI_IMAGE_RECOVERY_GATE[key] = {"dirty": True, "generation": 1}
            return
        state["dirty"] = True
        state["generation"] = int(state.get("generation") or 0) + 1


def _should_sync_ai_image_files_to_db(progress_db_path: Path, image_dir: Path | None = None) -> tuple[bool, tuple[bool, int], Path, int]:
    root = _ai_image_recovery_root(image_dir)
    dir_stamp = _ai_image_recovery_dir_stamp(root)
    key = (str(progress_db_for(progress_db_path)), str(root))
    with _AI_IMAGE_RECOVERY_GATE_LOCK:
        state = _AI_IMAGE_RECOVERY_GATE.get(key)
        generation = int(state.get("generation") or 0) if state else 0
        if state and not state.get("dirty") and state.get("dir_stamp") == dir_stamp:
            return False, dir_stamp, root, generation
    return True, dir_stamp, root, generation


def _mark_ai_image_recovery_clean(
    progress_db_path: Path,
    dir_stamp: tuple[bool, int],
    scan_generation: int,
    image_dir: Path | None = None,
) -> None:
    key = (str(progress_db_for(progress_db_path)), str(_ai_image_recovery_root(image_dir)))
    with _AI_IMAGE_RECOVERY_GATE_LOCK:
        state = _AI_IMAGE_RECOVERY_GATE.get(key)
        if state is None:
            _AI_IMAGE_RECOVERY_GATE[key] = {"dirty": False, "dir_stamp": dir_stamp, "generation": scan_generation}
            return
        if int(state.get("generation") or 0) != scan_generation:
            return
        state["dirty"] = False
        state["dir_stamp"] = dir_stamp


def runtime_ai_image_url(name: str) -> str:
    return f"/api/ai-images/{validated_ai_image_name(name)}"


def latest_ai_image_urls_by_card_id(image_dir: Path | None = None) -> dict[str, str]:
    root = _ai_image_recovery_root(image_dir)
    if not root.exists() or not root.is_dir():
        return {}
    latest: dict[str, tuple[str, str]] = {}
    for path in root.iterdir():
        if not path.is_file():
            continue
        match = AI_IMAGE_ARTIFACT_RE.fullmatch(path.name)
        if not match:
            continue
        card_id = str(match.group("card_id") or "").strip()
        stamp = str(match.group("stamp") or "")
        previous = latest.get(card_id)
        if previous is None or (stamp, path.name) > previous:
            latest[card_id] = (stamp, path.name)
    return {
        card_id: runtime_ai_image_url(name)
        for card_id, (_stamp, name) in latest.items()
    }


def sync_ai_image_files_to_db(progress_db_path: Path, image_dir: Path | None = None) -> bool:
    should_scan, dir_stamp, root, scan_generation = _should_sync_ai_image_files_to_db(progress_db_path, image_dir)
    if not should_scan:
        return False
    recovered_urls = latest_ai_image_urls_by_card_id(root)
    if not recovered_urls:
        _mark_ai_image_recovery_clean(progress_db_path, dir_stamp, scan_generation, root)
        return False
    ensure_progress_db(progress_db_path)
    changed = False
    with closing(connect_progress_db(progress_db_path)) as conn:
        rows = conn.execute(
            "SELECT card_id, concept_image_url, concept_media_type, concept_media_payload FROM cards"
        ).fetchall()
        for row in rows:
            card_id = str(row["card_id"] or "").strip()
            recovered_url = recovered_urls.get(card_id)
            if not recovered_url:
                continue
            media_type = normalized_concept_media_type(row["concept_media_type"]) if row["concept_media_type"] else ""
            if media_type in {"gif", "video", "mermaid", "html"}:
                continue
            current_url = normalized_runtime_media_url(row["concept_image_url"])
            current_payload = str(row["concept_media_payload"] or "")
            if media_type in {"image", "gif", "video"}:
                current_payload = normalized_runtime_media_url(current_payload)
            if current_url == recovered_url and media_type == "image" and current_payload == recovered_url:
                continue
            conn.execute(
                "UPDATE cards SET concept_image_url=?, concept_media_type='image', concept_media_payload=?, updated_at=? WHERE card_id=?",
                (recovered_url, recovered_url, utc_now_iso(), card_id),
            )
            changed = True
        conn.commit()
    _mark_ai_image_recovery_clean(progress_db_path, _ai_image_recovery_dir_stamp(root), scan_generation, root)
    return changed


def update_card_content_fields(
    card_id: str,
    updates: dict[str, str],
    backup_dir: Path = BACKUP_DIR,
    progress_db_path: Path | None = None,
) -> tuple[dict[str, str], Path | None]:
    db_path = progress_db_for(progress_db_path)
    ensure_progress_db(db_path)
    sync_ai_image_files_to_db(db_path)

    target = read_card(db_path, card_id)
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
        if AI_IMAGE_RECOVERY_FIELDS.intersection(changed_updates):
            mark_ai_image_recovery_dirty(db_path)
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
    backup_dir: Path = BACKUP_DIR,
    progress_db_path: Path | None = None,
) -> dict[str, str]:
    del backup_dir
    if status not in VALID_STATUSES:
        raise ValueError("known_status must be O, X, or empty")

    card = read_card(progress_db_path, card_id)
    normalized_card_id = str(card.get("id") or card_id)
    db_path = progress_db_for(progress_db_path)
    ensure_progress_db(db_path)
    with closing(connect_progress_db(db_path)) as conn:
        existing = conn.execute(
            "SELECT review_count FROM card_progress WHERE card_id = ?",
            (normalized_card_id,),
        ).fetchone()
        try:
            count = int(existing["review_count"] if existing else 0)
        except (TypeError, ValueError):
            count = 0
        last_reviewed = ""
        if status:
            count += 1
            last_reviewed = utc_now_iso()
        now = utc_now_iso()
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
            (normalized_card_id, status, last_reviewed, max(0, count), now),
        )
        conn.commit()
    return read_card(db_path, normalized_card_id)


def _ensure_card_exists(card_id: str, progress_db_path: Path | None = None) -> dict[str, Any]:
    return read_card(progress_db_path, card_id)


def set_bookmark(
    card_id: str,
    bookmarked: bool,
    progress_db_path: Path | None = None,
) -> dict[str, str]:
    card = _ensure_card_exists(card_id, progress_db_path)
    normalized_card_id = str(card.get("id") or card_id)
    db_path = progress_db_for(progress_db_path)
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
            (normalized_card_id, 1 if bookmarked else 0, utc_now_iso()),
        )
        conn.commit()
    return read_card(db_path, normalized_card_id)


def save_memo(
    card_id: str,
    memo: str,
    progress_db_path: Path | None = None,
) -> dict[str, str]:
    card = _ensure_card_exists(card_id, progress_db_path)
    normalized_card_id = str(card.get("id") or card_id)
    normalized_memo = str(memo or "")[:20000]
    memo_updated_at = utc_now_iso() if normalized_memo.strip() else ""
    db_path = progress_db_for(progress_db_path)
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
            (normalized_card_id, normalized_memo, memo_updated_at, utc_now_iso()),
        )
        conn.commit()
    return read_card(db_path, normalized_card_id)


def read_card_mutation_summary(progress_db_path: Path | None = None) -> dict[str, Any]:
    db_path = progress_db_for(progress_db_path)
    ensure_progress_db(db_path, must_exist=True)
    with closing(connect_progress_db(db_path, must_exist=True)) as conn:
        summary_row = conn.execute(
            """
            SELECT
                COUNT(cards.card_id) AS total_count,
                SUM(CASE WHEN card_progress.known_status = 'O' THEN 1 ELSE 0 END) AS known_count,
                SUM(CASE WHEN card_progress.known_status = 'X' THEN 1 ELSE 0 END) AS unknown_count,
                SUM(CASE WHEN COALESCE(card_progress.bookmarked, 0) = 1 THEN 1 ELSE 0 END) AS bookmarked_count,
                SUM(CASE WHEN TRIM(COALESCE(card_progress.memo, '')) <> '' THEN 1 ELSE 0 END) AS memo_count
            FROM cards
            LEFT JOIN card_progress ON card_progress.card_id = cards.card_id
            """
        ).fetchone()
        category_rows = conn.execute(
            """
            SELECT DISTINCT category
            FROM cards
            WHERE TRIM(COALESCE(category, '')) <> ''
            ORDER BY category COLLATE NOCASE
            """
        ).fetchall()
    total = int(summary_row["total_count"] or 0) if summary_row else 0
    known = int(summary_row["known_count"] or 0) if summary_row else 0
    unknown = int(summary_row["unknown_count"] or 0) if summary_row else 0
    return {
        "total": total,
        "known": known,
        "unknown": unknown,
        "unreviewed": max(0, total - known - unknown),
        "bookmarked": int(summary_row["bookmarked_count"] or 0) if summary_row else 0,
        "memo_count": int(summary_row["memo_count"] or 0) if summary_row else 0,
        "categories": [row["category"] for row in category_rows if str(row["category"] or "").strip()],
        "content_db_path": str(PROGRESS_DB_PATH),
        "progress_db_path": str(PROGRESS_DB_PATH),
    }


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


def rewrite_question_bank_answer_with_codex(
    entry: dict[str, Any],
    card: dict[str, Any] | None = None,
    instruction: str = "",
) -> dict[str, Any]:
    linked_card = card or {}
    parsed = request_codex_json_object(
        (
            "You refine Korean CS question-bank answer content. Return only one JSON object with the keys "
            "answer, explanation, rubric, answer_guide. Keep facts grounded in the provided question, existing "
            "answer, and linked flashcard context. Do not invent citations, URLs, or nonexistent standards. For "
            "multiple_choice questions, keep answer as the final correct choice only or an equivalently short final "
            "answer, and put the detail in explanation. For short, subjective, and essay questions, make the answer "
            "more concrete, study-friendly, and usable as a model answer in Korean. explanation should clarify the "
            "reasoning, likely pitfalls, and what should be mentioned for scoring. rubric should be a concise Korean "
            "list of scoring points. answer_guide should be a short Korean writing guide."
        ),
        {
            "instruction": str(instruction or "").strip() or "현재 문항의 모범답안과 해설을 더 구체적이고 학습 친화적으로 보강해 주세요.",
            "question": {
                "question_bank_id": entry.get("question_bank_id", ""),
                "card_id": entry.get("card_id", ""),
                "question_type": entry.get("question_type", ""),
                "prompt": entry.get("prompt", ""),
                "body": entry.get("body", ""),
                "answer": entry.get("answer", ""),
                "explanation": entry.get("explanation", ""),
                "rubric": entry.get("rubric", []),
                "choices": entry.get("choices", []),
                "answer_index": entry.get("answer_index"),
                "topic": entry.get("topic", ""),
                "field_name": entry.get("field_name", ""),
                "category": entry.get("category", ""),
                "keywords": entry.get("keywords", []),
                "difficulty": entry.get("difficulty", ""),
                "issuer": entry.get("issuer", ""),
                "source_location": entry.get("source_location", ""),
                "section": entry.get("section", ""),
                "points": entry.get("points"),
                "expected_time_seconds": entry.get("expected_time_seconds"),
                "answer_guide": entry.get("answer_guide", ""),
                "session_mode": entry.get("session_mode", "practice"),
            },
            "linked_card": {
                "id": linked_card.get("id", ""),
                "term": linked_card.get("term", ""),
                "english": linked_card.get("english", ""),
                "category": linked_card.get("category", ""),
                "definition": linked_card.get("definition", ""),
                "detailed_explanation": linked_card.get("detailed_explanation", ""),
                "exam_note": linked_card.get("exam_note", ""),
                "related_concepts": linked_card.get("related_concepts", ""),
                "difficulty": linked_card.get("difficulty", ""),
                "importance": linked_card.get("importance", ""),
            },
        },
        parse_error_message="Codex 응답을 문제은행 답안 보강 JSON으로 해석하지 못했습니다.",
    )
    return {
        "answer": normalize_question_bank_markdown(parsed.get("answer", entry.get("answer", "")), limit=20000),
        "explanation": normalize_question_bank_markdown(parsed.get("explanation", entry.get("explanation", "")), limit=50000),
        "rubric": normalize_question_bank_list(parsed.get("rubric", entry.get("rubric", [])), item_limit=2000),
        "answer_guide": normalize_question_bank_markdown(parsed.get("answer_guide", entry.get("answer_guide", "")), limit=255),
    }



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
    backup_dir: Path = BACKUP_DIR,
    progress_db_path: Path | None = None,
) -> tuple[dict[str, str], Path | None]:
    db_path = progress_db_for(progress_db_path)
    target = read_card(db_path, card_id)
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
    _, backup_path = update_card_content_fields(card_id, changed_updates, backup_dir, db_path)
    return read_card(db_path, card_id), backup_path


def update_card_concept_media(
    card_id: str,
    payload: CardConceptMediaRequest,
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
    _, backup_path = update_card_content_fields(card_id, updates, backup_dir, progress_db_path)
    return read_card(progress_db_for(progress_db_path), card_id), backup_path



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


def request_openai_generated_image_bytes(prompt: str) -> bytes:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않아 AI 이미지 초안을 만들 수 없습니다.")
    payload = {
        "model": IMAGE_MODEL,
        "prompt": str(prompt or "").strip(),
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
    return image_generation_result_bytes(parsed)


def generate_ai_concept_image_preview(
    card: dict[str, str],
    *,
    preview_dir: Path = AI_IMAGE_PREVIEW_DIR,
) -> dict[str, str]:
    image_bytes = request_openai_generated_image_bytes(concept_image_prompt(card))
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
    backup_dir: Path = BACKUP_DIR,
    progress_db_path: Path | None = None,
    image_dir: Path = AI_IMAGE_DIR,
    preview_dir: Path = AI_IMAGE_PREVIEW_DIR,
) -> tuple[dict[str, str], Path | None, str]:
    db_path = progress_db_for(progress_db_path)
    target = read_card(db_path, card_id)
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
    _, backup_path = update_card_content_fields(
        card_id,
        {"concept_image_url": next_url, "concept_image_alt": next_alt, "concept_media_type": "image", "concept_media_payload": next_url},
        backup_dir,
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
    return read_card(db_path, card_id), backup_path, next_url


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

def resolved_question_bank_attempt_status(value: str | None, is_correct: bool | None) -> str:
    judgment = resolved_question_attempt_judgment(value, is_correct)
    if judgment == "correct":
        return "correct"
    if judgment in {"ambiguous", "wrong", "unknown"}:
        return "wrong"
    return "unseen"


def resolved_question_attempt_judgment_sql(*, judgment_column: str = "judgment", is_correct_column: str = "is_correct") -> str:
    return (
        f"CASE WHEN TRIM(COALESCE({judgment_column}, '')) <> '' THEN LOWER(TRIM({judgment_column})) "
        f"WHEN {is_correct_column} = 1 THEN 'correct' WHEN {is_correct_column} = 0 THEN 'wrong' ELSE 'pending' END"
    )


def _question_attempt_summary_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    return {
        "question_attempt_count": int(row["question_attempt_count"] or 0) if row else 0,
        "question_correct_count": int(row["question_correct_count"] or 0) if row else 0,
        "question_wrong_count": int(row["question_wrong_count"] or 0) if row else 0,
        "latest_wrong_note": row["latest_wrong_note"] or "" if row else "",
        "latest_wrong_note_updated_at": row["latest_wrong_note_updated_at"] or "" if row else "",
    }


def _rebuild_question_attempt_card_summary_cache(conn: sqlite3.Connection) -> None:
    judgment_sql = resolved_question_attempt_judgment_sql(
        judgment_column="qa.judgment",
        is_correct_column="qa.is_correct",
    )
    conn.execute("DELETE FROM question_attempt_card_summary")
    conn.execute(
        f"""
        INSERT INTO question_attempt_card_summary (
            card_id,
            question_attempt_count,
            question_correct_count,
            question_wrong_count,
            latest_wrong_note,
            latest_wrong_note_updated_at
        )
        WITH attempt_counts AS (
            SELECT
                qa.card_id,
                COUNT(*) AS question_attempt_count,
                SUM(CASE WHEN {judgment_sql} = 'correct' THEN 1 ELSE 0 END) AS question_correct_count,
                SUM(CASE WHEN {judgment_sql} IN ('ambiguous', 'wrong', 'unknown') THEN 1 ELSE 0 END) AS question_wrong_count
            FROM question_attempts AS qa
            WHERE TRIM(COALESCE(qa.card_id, '')) <> ''
            GROUP BY qa.card_id
        ),
        latest_wrong_notes AS (
            SELECT card_id, wrong_note, updated_at
            FROM (
                SELECT
                    qa.card_id,
                    qa.wrong_note,
                    qa.updated_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY qa.card_id
                        ORDER BY qa.updated_at DESC, qa.answered_at DESC, qa.question_order DESC, qa.question_id DESC
                    ) AS row_number
                FROM question_attempts AS qa
                WHERE TRIM(COALESCE(qa.card_id, '')) <> ''
                  AND {judgment_sql} IN ('ambiguous', 'wrong', 'unknown')
                  AND TRIM(COALESCE(qa.wrong_note, '')) <> ''
            )
            WHERE row_number = 1
        )
        SELECT
            attempt_counts.card_id,
            attempt_counts.question_attempt_count,
            attempt_counts.question_correct_count,
            attempt_counts.question_wrong_count,
            COALESCE(latest_wrong_notes.wrong_note, '') AS latest_wrong_note,
            COALESCE(latest_wrong_notes.updated_at, '') AS latest_wrong_note_updated_at
        FROM attempt_counts
        LEFT JOIN latest_wrong_notes ON latest_wrong_notes.card_id = attempt_counts.card_id
        """
    )


def _refresh_question_attempt_card_summary_cache(conn: sqlite3.Connection, card_ids: list[str] | None) -> None:
    normalized_ids = sorted(normalize_card_ids(card_ids) or [])
    if not normalized_ids:
        return
    judgment_sql = resolved_question_attempt_judgment_sql(
        judgment_column="qa.judgment",
        is_correct_column="qa.is_correct",
    )
    for card_id in normalized_ids:
        row = conn.execute(
            f"""
            WITH latest_wrong_note AS (
                SELECT qa.wrong_note, qa.updated_at
                FROM question_attempts AS qa
                WHERE qa.card_id = ?
                  AND {judgment_sql} IN ('ambiguous', 'wrong', 'unknown')
                  AND TRIM(COALESCE(qa.wrong_note, '')) <> ''
                ORDER BY qa.updated_at DESC, qa.answered_at DESC, qa.question_order DESC, qa.question_id DESC
                LIMIT 1
            )
            SELECT
                COUNT(*) AS question_attempt_count,
                SUM(CASE WHEN {judgment_sql} = 'correct' THEN 1 ELSE 0 END) AS question_correct_count,
                SUM(CASE WHEN {judgment_sql} IN ('ambiguous', 'wrong', 'unknown') THEN 1 ELSE 0 END) AS question_wrong_count,
                COALESCE((SELECT wrong_note FROM latest_wrong_note), '') AS latest_wrong_note,
                COALESCE((SELECT updated_at FROM latest_wrong_note), '') AS latest_wrong_note_updated_at
            FROM question_attempts AS qa
            WHERE qa.card_id = ?
            """,
            (card_id, card_id),
        ).fetchone()
        summary = _question_attempt_summary_dict(row)
        if summary["question_attempt_count"] <= 0:
            conn.execute("DELETE FROM question_attempt_card_summary WHERE card_id = ?", (card_id,))
            continue
        conn.execute(
            """
            INSERT INTO question_attempt_card_summary (
                card_id,
                question_attempt_count,
                question_correct_count,
                question_wrong_count,
                latest_wrong_note,
                latest_wrong_note_updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(card_id) DO UPDATE SET
                question_attempt_count = excluded.question_attempt_count,
                question_correct_count = excluded.question_correct_count,
                question_wrong_count = excluded.question_wrong_count,
                latest_wrong_note = excluded.latest_wrong_note,
                latest_wrong_note_updated_at = excluded.latest_wrong_note_updated_at
            """,
            (
                card_id,
                summary["question_attempt_count"],
                summary["question_correct_count"],
                summary["question_wrong_count"],
                summary["latest_wrong_note"],
                summary["latest_wrong_note_updated_at"],
            ),
        )



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


def normalize_question_bank_attempt_status(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "": "",
        "all": "",
        "unseen": "unseen",
        "pending": "unseen",
        "unanswered": "unseen",
        "안푼": "unseen",
        "미풀이": "unseen",
        "correct": "correct",
        "right": "correct",
        "맞음": "correct",
        "맞은": "correct",
        "정답": "correct",
        "wrong": "wrong",
        "incorrect": "wrong",
        "틀림": "wrong",
        "틀린": "wrong",
        "오답": "wrong",
    }
    normalized = aliases.get(raw)
    if normalized is None or normalized not in QUESTION_BANK_ATTEMPT_FILTER_VALUES:
        raise ValueError(f"Unsupported question bank attempt status: {value}")
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


def normalize_question_bank_ids(values: Any, *, item_limit: int = 255) -> list[str]:
    return normalize_question_bank_list(values, item_limit=item_limit)


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


def _ensure_card_exists(
    card_id: Any,
    progress_db_path: Path | None = None,
    *,
    card_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_card_id = normalize_question_bank_text(card_id, limit=255)
    if not normalized_card_id:
        raise KeyError(card_id)
    if card_map is None:
        card_map, _ = load_question_bank_card_context(progress_db_path, card_ids=[normalized_card_id])
    card = card_map.get(normalized_card_id)
    if not isinstance(card, dict) or not card:
        raise KeyError(normalized_card_id)
    return card


def question_bank_keywords_for_card(card: dict[str, Any]) -> list[str]:
    related = re.split(r"\[\[|\]\]|[,;/\n]", str(card.get("related_concepts") or ""))
    return normalize_question_bank_list([
        card.get("term") or "",
        card.get("english") or "",
        *related,
    ])


def question_bank_keywords_for_linked_card(card: dict[str, Any] | None) -> list[str]:
    if not isinstance(card, dict) or not card:
        return []
    return question_bank_keywords_for_card(card)


def question_bank_missing_card_keywords(values: Any, *, linked_keywords: Any = None) -> list[str]:
    linked = {item.casefold() for item in normalize_question_bank_list(linked_keywords, item_limit=255)}
    return [
        keyword
        for keyword in normalize_question_bank_list(values, item_limit=255)
        if keyword.casefold() not in linked
    ]


def question_bank_card_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        normalize_question_bank_text(row.get("id") or row.get("card_id"), limit=255): row
        for row in rows
        if normalize_question_bank_text(row.get("id") or row.get("card_id"), limit=255)
    }


def load_question_bank_card_context(
    progress_db_path: Path | None = None,
    *,
    card_ids: list[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    db_path = progress_db_for(progress_db_path)
    ensure_progress_db(db_path, must_exist=True)
    normalized_ids = [
        card_id
        for card_id in (
            normalize_question_bank_text(value, limit=255)
            for value in (card_ids or [])
        )
        if card_id
    ]
    card_map: dict[str, dict[str, Any]] = {}
    categories: list[str] = []
    seen: set[str] = set()
    with closing(connect_progress_db(db_path, must_exist=True)) as conn:
        category_rows = conn.execute(
            """
            SELECT category, MIN(sort_order) AS sort_order
            FROM cards
            WHERE TRIM(COALESCE(category, '')) <> ''
            GROUP BY category
            ORDER BY sort_order ASC, category COLLATE NOCASE ASC
            """
        ).fetchall()
        for row in category_rows:
            category = normalize_question_bank_text(row["category"], limit=128)
            if not category or category.casefold() in seen:
                continue
            seen.add(category.casefold())
            categories.append(category)
        if normalized_ids:
            qmarks = ", ".join("?" for _ in normalized_ids)
            card_rows = conn.execute(
                f"SELECT card_id, term, english, category, related_concepts, source_files, difficulty FROM cards WHERE card_id IN ({qmarks})",
                tuple(normalized_ids),
            ).fetchall()
            card_map = {
                str(row["card_id"] or "").strip(): {
                    "id": row["card_id"] or "",
                    "term": row["term"] or "",
                    "english": row["english"] or "",
                    "category": row["category"] or "",
                    "related_concepts": row["related_concepts"] or "",
                    "source_files": row["source_files"] or "",
                    "difficulty": row["difficulty"] or "",
                }
                for row in card_rows
                if str(row["card_id"] or "").strip()
            }
    return card_map, question_bank_categories_from_cards(rows=[{"category": category} for category in categories])


def question_bank_missing_card_rows(
    rows: list[dict[str, Any]],
    *,
    card_keyword_to_card_id: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    keyword_counts: dict[str, int] = {}
    keyword_labels: dict[str, str] = {}
    for row in rows:
        for keyword in question_bank_json_list(row.get("missing_card_keywords_json") or []):
            key = keyword.casefold()
            if key in keyword_counts:
                keyword_counts[key] += 1
                continue
            keyword_counts[key] = 1
            keyword_labels[key] = keyword
    lookup = card_keyword_to_card_id or {}
    items: list[dict[str, Any]] = []
    for key, count in sorted(keyword_counts.items(), key=lambda item: (-item[1], 0 if str(lookup.get(item[0]) or "").strip() else 1, keyword_labels[item[0]].casefold())):
        card_id = str(lookup.get(key) or "").strip()
        items.append({
            "keyword": keyword_labels[key],
            "question_count": count,
            "card_created": bool(card_id),
            "card_id": card_id,
        })
    return items


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


def question_bank_categories_from_cards(
    progress_db_path: Path | None = None,
    *,
    rows: list[dict[str, Any]] | None = None,
) -> list[str]:
    if rows is None:
        _, categories = load_question_bank_card_context(progress_db_path)
        return categories
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
    progress_db_path: Path | None = None,
    allowed_categories: list[str] | None = None,
) -> str:
    if allowed_categories is None:
        allowed_categories = question_bank_categories_from_cards(progress_db_path)
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
        "missing_card_keywords": entry.get("missing_card_keywords", []),
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
    progress_db_path: Path | None = None,
    *,
    card_map: dict[str, dict[str, Any]] | None = None,
    allowed_categories: list[str] | None = None,
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
        card = _ensure_card_exists(card_id, progress_db_path, card_map=card_map)
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
    answer = normalize_question_bank_markdown(raw.get("answer"), limit=20000)
    explanation = normalize_question_bank_markdown(raw.get("explanation"), limit=50000)
    linked_keywords = question_bank_keywords_for_linked_card(card)
    missing_card_keywords = question_bank_missing_card_keywords(raw.get("keywords"), linked_keywords=linked_keywords)
    difficulty = normalized_question_bank_difficulty(raw.get("difficulty")) or infer_question_bank_difficulty(
        question_type,
        prompt,
        body,
        answer,
        explanation,
        card=card,
    )
    normalized = {
        "question_bank_id": normalize_question_bank_text(raw.get("question_bank_id"), limit=255),
        "card_id": card_id,
        "question_type": question_type,
        "prompt": prompt,
        "body": body,
        "answer": answer,
        "explanation": explanation,
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
            progress_db_path=progress_db_path,
            allowed_categories=allowed_categories,
        ),
        "keywords": linked_keywords,
        "missing_card_keywords": missing_card_keywords,
        "difficulty": difficulty,
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
    question_type = row["question_type"] if "question_type" in row.keys() else ""
    prompt = row["prompt"] if "prompt" in row.keys() else ""
    body = row["body"] if "body" in row.keys() else ""
    answer = row["answer"] if "answer" in row.keys() else ""
    explanation = row["explanation"] if "explanation" in row.keys() else ""
    difficulty = normalized_question_bank_difficulty(row["difficulty"] if "difficulty" in row.keys() else "")
    if not difficulty:
        difficulty = infer_question_bank_difficulty(question_type, prompt, body, answer, explanation)

    return {
        "question_bank_id": row["id"],
        "card_id": row["card_id"] or "",
        "question_type": question_type or "",
        "prompt": prompt or "",
        "body": body or "",
        "answer": answer or "",
        "explanation": explanation or "",
        "rubric": question_bank_json_list(row["rubric_json"] if "rubric_json" in row.keys() else "[]"),
        "choices": question_bank_json_list(row["choices_json"] if "choices_json" in row.keys() else "[]"),
        "answer_index": row["answer_index"] if "answer_index" in row.keys() else None,
        "topic": row["topic"] if "topic" in row.keys() else "",
        "field_name": row["field_name"] if "field_name" in row.keys() else "",
        "category": row["category"] if "category" in row.keys() else "",
        "keywords": question_bank_json_list(row["keywords_json"] if "keywords_json" in row.keys() else "[]"),
        "missing_card_keywords": question_bank_json_list(row["missing_card_keywords_json"] if "missing_card_keywords_json" in row.keys() else "[]"),
        "difficulty": difficulty,
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








def update_question_bank_entry(
    question_bank_id: str,
    payload: QuestionBankEntryRequest | dict[str, Any],
    progress_db_path: Path | None = None,
) -> dict[str, Any]:
    db_path = progress_db_for(progress_db_path)
    ensure_progress_db(db_path)
    raw = payload.model_dump() if isinstance(payload, BaseModel) else dict(payload or {})
    normalized = normalize_question_bank_entry({**raw, "question_bank_id": question_bank_id}, progress_db_path)
    with closing(connect_progress_db(db_path)) as conn:
        existing = conn.execute("SELECT id FROM question_bank WHERE id = ?", (question_bank_id,)).fetchone()
        if existing is None:
            raise KeyError(question_bank_id)
        duplicate = conn.execute(
            "SELECT id FROM question_bank WHERE fingerprint = ? AND id <> ?",
            (normalized["fingerprint"], question_bank_id),
        ).fetchone()
        if duplicate is not None:
            raise ValueError("수정 결과가 기존 문제은행 문항과 중복되어 저장할 수 없습니다.")
        now = utc_now_iso()
        conn.execute(
            """
            UPDATE question_bank
            SET fingerprint = ?,
                card_id = ?,
                question_type = ?,
                prompt = ?,
                body = ?,
                answer = ?,
                explanation = ?,
                rubric_json = ?,
                choices_json = ?,
                answer_index = ?,
                topic = ?,
                field_name = ?,
                category = ?,
                keywords_json = ?,
                missing_card_keywords_json = ?,
                difficulty = ?,
                issuer = ?,
                source_location = ?,
                section = ?,
                points = ?,
                expected_time_seconds = ?,
                answer_guide = ?,
                session_mode = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                normalized["fingerprint"],
                normalized["card_id"] or None,
                normalized["question_type"],
                normalized["prompt"],
                normalized["body"],
                normalized["answer"],
                normalized["explanation"],
                question_bank_json_text(normalized["rubric"], item_limit=2000),
                question_bank_json_text(normalized["choices"], item_limit=2000),
                normalized["answer_index"],
                normalized["topic"],
                normalized["field_name"],
                normalized["category"],
                question_bank_json_text(normalized["keywords"], item_limit=255),
                question_bank_json_text(normalized.get("missing_card_keywords", []), item_limit=255),
                normalized["difficulty"],
                normalized["issuer"],
                normalized["source_location"],
                normalized["section"],
                normalized["points"],
                normalized["expected_time_seconds"],
                normalized["answer_guide"],
                normalized["session_mode"],
                now,
                question_bank_id,
            ),
        )
        saved = conn.execute(
            """
            SELECT id, card_id, question_type, prompt, body, answer, explanation,
                   rubric_json, choices_json, answer_index, topic, field_name, category, keywords_json,
                   missing_card_keywords_json, difficulty, issuer, source_location, section, points, expected_time_seconds,
                   answer_guide, session_mode, created_at, updated_at
            FROM question_bank
            WHERE id = ?
            """,
            (question_bank_id,),
        ).fetchone()
        conn.commit()
    return question_bank_row_to_dict(saved) or normalized


def update_question_bank_ai_content(
    question_bank_id: str,
    payload: QuestionBankAiRefineRequest,
    progress_db_path: Path | None = None,
) -> dict[str, Any]:
    db_path = progress_db_for(progress_db_path)
    ensure_progress_db(db_path)
    with closing(connect_progress_db(db_path)) as conn:
        row = conn.execute(
            """
            SELECT id, card_id, question_type, prompt, body, answer, explanation,
                   rubric_json, choices_json, answer_index, topic, field_name, category, keywords_json,
                   missing_card_keywords_json, difficulty, issuer, source_location, section, points, expected_time_seconds,
                   answer_guide, session_mode, created_at, updated_at
            FROM question_bank
            WHERE id = ?
            """,
            (question_bank_id,),
        ).fetchone()
        if row is None:
            raise KeyError(question_bank_id)
        current = question_bank_row_to_dict(row) or {}
        linked_card: dict[str, Any] = {}
        if current.get("card_id"):
            try:
                linked_card = read_card(db_path, current.get("card_id"))
            except KeyError:
                linked_card = {}

        proposal = rewrite_question_bank_answer_with_codex(current, linked_card, payload.instruction)
        next_entry = {**current, **proposal}
        changed = any(next_entry.get(field) != current.get(field) for field in ("answer", "explanation", "rubric", "answer_guide"))
        if not changed:
            return current
        next_fingerprint = question_bank_fingerprint(next_entry)
        duplicate = conn.execute(
            "SELECT id FROM question_bank WHERE fingerprint = ? AND id <> ?",
            (next_fingerprint, question_bank_id),
        ).fetchone()
        if duplicate is not None:
            raise ValueError("AI 보강 결과가 기존 문제은행 문항과 중복되어 저장할 수 없습니다.")
        now = utc_now_iso()
        conn.execute(
            """
            UPDATE question_bank
            SET answer = ?,
                explanation = ?,
                rubric_json = ?,
                answer_guide = ?,
                fingerprint = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                next_entry["answer"],
                next_entry["explanation"],
                question_bank_json_text(next_entry["rubric"], item_limit=2000),
                next_entry["answer_guide"],
                next_fingerprint,
                now,
                question_bank_id,
            ),
        )
        saved = conn.execute(
            """
            SELECT id, card_id, question_type, prompt, body, answer, explanation,
                   rubric_json, choices_json, answer_index, topic, field_name, category, keywords_json,
                   missing_card_keywords_json, difficulty, issuer, source_location, section, points, expected_time_seconds,
                   answer_guide, session_mode, created_at, updated_at
            FROM question_bank
            WHERE id = ?
            """,
            (question_bank_id,),
        ).fetchone()
        conn.commit()
    return question_bank_row_to_dict(saved) or next_entry

def seed_demo_question_bank_entries(
    progress_db_path: Path | None = None,
) -> None:
    db_path = progress_db_for(progress_db_path)
    if progress_db_path is not None and db_path != PROGRESS_DB_PATH:
        return
    ensure_progress_db(db_path)
    with closing(connect_progress_db(db_path)) as conn:
        existing_count = int(conn.execute("SELECT COUNT(*) FROM question_bank").fetchone()[0] or 0)
    if existing_count:
        return
    rows, _ = read_cards(db_path)
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
        db_path,
    )



def upsert_question_bank_entries(
    entries: list[QuestionBankEntryRequest | dict[str, Any]],
    progress_db_path: Path | None = None,
    *,
    card_map: dict[str, dict[str, Any]] | None = None,
    allowed_categories: list[str] | None = None,
) -> dict[str, Any]:
    if card_map is None or allowed_categories is None:
        card_ids = []
        if entries:
            card_ids = [
                normalize_question_bank_text(
                    (entry.model_dump() if isinstance(entry, BaseModel) else dict(entry or {})).get("card_id"),
                    limit=255,
                )
                for entry in entries
            ]
        loaded_card_map, loaded_categories = load_question_bank_card_context(progress_db_path, card_ids=card_ids)
        if card_map is None:
            card_map = loaded_card_map
        if allowed_categories is None:
            allowed_categories = loaded_categories
    normalized_entries = [
        normalize_question_bank_entry(
            entry,
            progress_db_path,
            card_map=card_map,
            allowed_categories=allowed_categories,
        )
        for entry in entries
    ]
    db_path = progress_db_for(progress_db_path)
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
                    missing_card_keywords_json, difficulty, issuer, source_location, section, points, expected_time_seconds,
                    answer_guide, session_mode, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    missing_card_keywords_json = excluded.missing_card_keywords_json,
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
                    question_bank_json_text(entry.get("missing_card_keywords", []), item_limit=255),
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
                       missing_card_keywords_json, difficulty, issuer, source_location, section, points, expected_time_seconds,
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



def _read_question_bank_card_context(
    conn: sqlite3.Connection,
    *,
    linked_card_ids: set[str],
    missing_card_keywords: set[str],
) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    normalized_card_ids = {
        normalize_question_bank_text(value, limit=255)
        for value in linked_card_ids
        if normalize_question_bank_text(value, limit=255)
    }
    normalized_keywords = {
        normalize_question_bank_text(value, limit=255).casefold()
        for value in missing_card_keywords
        if normalize_question_bank_text(value, limit=255)
    }
    if not normalized_card_ids and not normalized_keywords:
        return {}, {}

    where_clauses: list[str] = []
    params: list[Any] = []
    if normalized_card_ids:
        placeholders = ", ".join("?" for _ in normalized_card_ids)
        where_clauses.append(f"TRIM(COALESCE(card_id, '')) IN ({placeholders})")
        params.extend(sorted(normalized_card_ids))
    if normalized_keywords:
        keyword_predicates: list[str] = []
        keyword_placeholders = ", ".join("?" for _ in normalized_keywords)
        keyword_predicates.append(f"LOWER(TRIM(COALESCE(term, ''))) IN ({keyword_placeholders})")
        params.extend(sorted(normalized_keywords))
        keyword_predicates.append(f"LOWER(TRIM(COALESCE(english, ''))) IN ({keyword_placeholders})")
        params.extend(sorted(normalized_keywords))
        related_predicates: list[str] = []
        for keyword in sorted(normalized_keywords):
            related_predicates.append("LOWER(COALESCE(related_concepts, '')) LIKE ?")
            params.append(f"%{keyword}%")
        keyword_predicates.append("(" + " OR ".join(related_predicates) + ")")
        where_clauses.append("(" + " OR ".join(keyword_predicates) + ")")

    rows = conn.execute(
        f"""
        SELECT card_id, term, english, category, related_concepts
        FROM cards
        WHERE {' OR '.join(where_clauses)}
        ORDER BY sort_order ASC, card_id ASC
        """,
        tuple(params),
    ).fetchall()
    card_map: dict[str, dict[str, str]] = {}
    card_keyword_to_card_id: dict[str, str] = {}
    for row in rows:
        card_id_value = str(row["card_id"] or "").strip()
        if not card_id_value:
            continue
        card = {
            "id": card_id_value,
            "term": str(row["term"] or ""),
            "english": str(row["english"] or ""),
            "category": str(row["category"] or ""),
            "related_concepts": str(row["related_concepts"] or ""),
        }
        if card_id_value in normalized_card_ids:
            card_map[card_id_value] = card
        for keyword in question_bank_keywords_for_card(card):
            card_keyword_to_card_id.setdefault(keyword.casefold(), card_id_value)
    return card_map, card_keyword_to_card_id


def read_question_bank_entries(
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
    attempt_status: str = "",
    include_missing_cards: bool = False,
    limit: int = 200,
) -> dict[str, Any]:
    db_path = progress_db_for(progress_db_path)
    ensure_progress_db(db_path, must_exist=True)
    seed_demo_question_bank_entries(db_path)
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
        "attempt_status": normalize_question_bank_attempt_status(attempt_status),
    }
    where_clauses: list[str] = []
    params: list[Any] = []
    for column in ("card_id", "topic", "field_name", "category", "issuer", "difficulty", "section", "source_location"):
        value = filters[column]
        if not value:
            continue
        where_clauses.append(f"LOWER(question_bank.{column}) LIKE ?")
        params.append(f"%{value.lower()}%")
    if filters["question_type"]:
        where_clauses.append("question_bank.question_type = ?")
        params.append(filters["question_type"])
    if filters["query"]:
        where_clauses.append(
            "(" + " OR ".join([
                "LOWER(question_bank.prompt) LIKE ?",
                "LOWER(question_bank.body) LIKE ?",
                "LOWER(question_bank.answer) LIKE ?",
                "LOWER(question_bank.explanation) LIKE ?",
                "LOWER(question_bank.topic) LIKE ?",
                "LOWER(question_bank.field_name) LIKE ?",
                "LOWER(question_bank.category) LIKE ?",
                "LOWER(question_bank.issuer) LIKE ?",
                "LOWER(question_bank.source_location) LIKE ?",
                "LOWER(question_bank.keywords_json) LIKE ?",
                "LOWER(question_bank.missing_card_keywords_json) LIKE ?",
            ]) + ")"
        )
        needle = f"%{filters['query'].lower()}%"
        params.extend([needle] * 11)
    latest_attempt_judgment_sql = resolved_question_attempt_judgment_sql(
        judgment_column="latest_attempt.judgment",
        is_correct_column="latest_attempt.is_correct",
    )
    if filters["attempt_status"] == "unseen":
        where_clauses.append(f"(latest_attempt.question_bank_id IS NULL OR {latest_attempt_judgment_sql} = 'pending')")
    elif filters["attempt_status"] == "correct":
        where_clauses.append(f"{latest_attempt_judgment_sql} = 'correct'")
    elif filters["attempt_status"] == "wrong":
        where_clauses.append(f"{latest_attempt_judgment_sql} IN ('ambiguous', 'wrong', 'unknown')")
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    latest_attempt_join_sql = """
        LEFT JOIN (
            SELECT question_bank_id, judgment, is_correct
            FROM (
                SELECT
                    question_bank_id,
                    judgment,
                    is_correct,
                    ROW_NUMBER() OVER (
                        PARTITION BY question_bank_id
                        ORDER BY updated_at DESC, created_at DESC, question_id DESC
                    ) AS rn
                FROM question_attempts
                WHERE TRIM(COALESCE(question_bank_id, '')) <> ''
            )
            WHERE rn = 1
        ) AS latest_attempt
        ON latest_attempt.question_bank_id = question_bank.id
    """
    with closing(connect_progress_db(db_path)) as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) AS total_count FROM question_bank {latest_attempt_join_sql} {where_sql}",
            tuple(params),
        ).fetchone()
        total_count = int(total_row["total_count"] or 0) if total_row else 0
        issuer_rows = conn.execute(
            "SELECT DISTINCT issuer FROM question_bank WHERE TRIM(issuer) <> '' ORDER BY issuer COLLATE NOCASE ASC"
        ).fetchall()
        category_rows = conn.execute(
            "SELECT DISTINCT category FROM question_bank WHERE TRIM(category) <> '' ORDER BY category COLLATE NOCASE ASC"
        ).fetchall()
        topic_rows = conn.execute(
            "SELECT DISTINCT topic FROM question_bank WHERE TRIM(topic) <> '' ORDER BY topic COLLATE NOCASE ASC"
        ).fetchall()
        field_name_rows = conn.execute(
            "SELECT DISTINCT field_name FROM question_bank WHERE TRIM(field_name) <> '' ORDER BY field_name COLLATE NOCASE ASC"
        ).fetchall()
        category_breakdown_rows = conn.execute(
            f"""
            SELECT
                COALESCE(NULLIF(TRIM(question_bank.category), ''), '미분류') AS category,
                COUNT(*) AS total,
                SUM(CASE WHEN question_bank.question_type = 'multiple_choice' THEN 1 ELSE 0 END) AS multiple_choice_count,
                SUM(CASE WHEN question_bank.question_type = 'short' THEN 1 ELSE 0 END) AS short_count,
                SUM(CASE WHEN question_bank.question_type = 'subjective' THEN 1 ELSE 0 END) AS subjective_count,
                SUM(CASE WHEN question_bank.question_type = 'essay' THEN 1 ELSE 0 END) AS essay_count,
                SUM(CASE WHEN question_bank.difficulty = '상' THEN 1 ELSE 0 END) AS high_difficulty_count,
                SUM(CASE WHEN question_bank.difficulty = '중' THEN 1 ELSE 0 END) AS medium_difficulty_count,
                SUM(CASE WHEN question_bank.difficulty = '하' THEN 1 ELSE 0 END) AS low_difficulty_count,
                SUM(CASE WHEN latest_attempt.question_bank_id IS NULL OR {latest_attempt_judgment_sql} = 'pending' THEN 1 ELSE 0 END) AS unseen_count,
                SUM(CASE WHEN {latest_attempt_judgment_sql} = 'correct' THEN 1 ELSE 0 END) AS correct_count,
                SUM(CASE WHEN {latest_attempt_judgment_sql} IN ('ambiguous', 'wrong', 'unknown') THEN 1 ELSE 0 END) AS wrong_count
            FROM question_bank
            {latest_attempt_join_sql}
            {where_sql}
            GROUP BY 1
            ORDER BY total DESC, category COLLATE NOCASE ASC
            """,
            tuple(params),
        ).fetchall()

        query_rows = conn.execute(
            f"""
            SELECT question_bank.id, question_bank.card_id, question_bank.question_type, question_bank.prompt, question_bank.body,
                   question_bank.answer, question_bank.explanation, question_bank.rubric_json, question_bank.choices_json,
                   question_bank.answer_index, question_bank.topic, question_bank.field_name, question_bank.category,
                   question_bank.keywords_json, question_bank.missing_card_keywords_json, question_bank.difficulty, question_bank.issuer, question_bank.source_location,
                   question_bank.section, question_bank.points, question_bank.expected_time_seconds, question_bank.answer_guide,
                   question_bank.session_mode, question_bank.created_at, question_bank.updated_at,
                   latest_attempt.judgment AS latest_attempt_judgment,
                   latest_attempt.is_correct AS latest_attempt_is_correct
            FROM question_bank
            {latest_attempt_join_sql}
            {where_sql}
            ORDER BY question_bank.updated_at DESC, question_bank.created_at DESC, question_bank.id DESC
            LIMIT ?
            """,
            tuple(params + [safe_limit]),
        ).fetchall()
        linked_card_ids = {
            normalize_question_bank_text(row["card_id"] if "card_id" in row.keys() else "", limit=255)
            for row in query_rows
            if normalize_question_bank_text(row["card_id"] if "card_id" in row.keys() else "", limit=255)
        }
        card_map: dict[str, dict[str, str]]
        card_keyword_to_card_id: dict[str, str] = {}
        if include_missing_cards:
            if total_count <= len(query_rows):
                missing_card_summary_rows = [dict(row) for row in query_rows]
            else:
                missing_card_summary_rows = [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT question_bank.missing_card_keywords_json
                        FROM question_bank
                        {latest_attempt_join_sql}
                        {where_sql}
                        """,
                        tuple(params),
                    ).fetchall()
                ]
            missing_card_keywords: set[str] = set()
            for row in missing_card_summary_rows:
                missing_card_keywords.update(question_bank_json_list(row["missing_card_keywords_json"] if "missing_card_keywords_json" in row.keys() else []))
            card_map, card_keyword_to_card_id = _read_question_bank_card_context(
                conn,
                linked_card_ids=linked_card_ids,
                missing_card_keywords=missing_card_keywords,
            )
        else:
            card_map, _ = _read_question_bank_card_context(
                conn,
                linked_card_ids=linked_card_ids,
                missing_card_keywords=set(),
            )
    items: list[dict[str, Any]] = []
    for row in query_rows:
        item = question_bank_row_to_dict(row) or {}
        card = card_map.get(item.get("card_id", ""), {})
        latest_is_correct = None if row["latest_attempt_is_correct"] is None else bool(int(row["latest_attempt_is_correct"]))
        latest_judgment = resolved_question_attempt_judgment(row["latest_attempt_judgment"], latest_is_correct)
        item["question_attempt_status"] = resolved_question_bank_attempt_status(row["latest_attempt_judgment"], latest_is_correct)
        item["question_attempt_judgment"] = latest_judgment or "pending"
        item["question_attempt_status_label"] = QUESTION_BANK_ATTEMPT_FILTER_LABELS.get(item["question_attempt_status"], "안푼")
        item["term"] = card.get("term") or card.get("english") or item.get("card_id") or ""
        item["english"] = card.get("english") or ""
        item["keywords"] = question_bank_keywords_for_linked_card(card)
        item["missing_card_keywords"] = question_bank_json_list(row["missing_card_keywords_json"] if "missing_card_keywords_json" in row.keys() else [])
        item["card_category"] = card.get("category") or ""
        item["card_url"] = flashcard_card_url(item.get("card_id") or "") if item.get("card_id") else ""
        items.append(item)
    return {
        "items": items,
        "summary": {
            "total": total_count,
            "returned": len(items),
            "limit": safe_limit,
            "available_issuers": [str(row[0] or "").strip() for row in issuer_rows if str(row[0] or "").strip()],
            "available_categories": [str(row[0] or "").strip() for row in category_rows if str(row[0] or "").strip()],
            "available_topics": [str(row[0] or "").strip() for row in topic_rows if str(row[0] or "").strip()],
            "available_field_names": [str(row[0] or "").strip() for row in field_name_rows if str(row[0] or "").strip()],
            "missing_cards": question_bank_missing_card_rows(
                missing_card_summary_rows,
                card_keyword_to_card_id=card_keyword_to_card_id,
            ) if include_missing_cards else [],
            "category_breakdown": [
                {
                    "category": str(row["category"] or "").strip() or "미분류",
                    "total": int(row["total"] or 0),
                    "multiple_choice_count": int(row["multiple_choice_count"] or 0),
                    "short_count": int(row["short_count"] or 0),
                    "subjective_count": int(row["subjective_count"] or 0),
                    "essay_count": int(row["essay_count"] or 0),
                    "high_difficulty_count": int(row["high_difficulty_count"] or 0),
                    "medium_difficulty_count": int(row["medium_difficulty_count"] or 0),
                    "low_difficulty_count": int(row["low_difficulty_count"] or 0),
                    "unseen_count": int(row["unseen_count"] or 0),
                    "correct_count": int(row["correct_count"] or 0),
                    "wrong_count": int(row["wrong_count"] or 0),
                }
                for row in category_breakdown_rows
            ],
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
        "missing_card_keywords": [],
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
    progress_db_path: Path | None = None,
) -> dict[str, Any]:
    questions = list(payload.get("questions") or [])
    if not questions:
        return payload
    card_map = question_bank_card_map(rows)
    bank_payloads = [generated_question_bank_entry(question, card_map.get(str(question.get("card_id") or ""), {})) for question in questions]
    saved = upsert_question_bank_entries(
        bank_payloads,
        progress_db_path,
        card_map=card_map,
        allowed_categories=question_bank_categories_from_cards(rows=rows),
    )
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

FIN_CORP_QUESTION_BANK_PAGE_GLOB = "05-0[1-8]-*.md"
FIN_CORP_QUESTION_HEADING_RE = re.compile(r"^###\s+(\d+)\.\s+(.+?)\s*$", re.MULTILINE)
FIN_CORP_TITLE_PREFIX_RE = re.compile(r"^\d{2}-\d{2}\.\s*")
FIN_CORP_CHOICE_LINE_RE = re.compile(r"^\s*(\d+|[A-Ea-e])\.\s*(.+?)\s*$")
FIN_CORP_INLINE_CHOICE_RE = re.compile(r"(?:^|\s)(\d+)\.\s*([^.\n].*?)(?=(?:\s+\d+\.\s*)|$)")
FIN_CORP_ANSWER_LINE_PATTERNS = (
    re.compile(r"^(?P<prefix>.*?)(?P<marker>\*\*답(?:\(AI답변\))?:?\*{0,2}\s*:?\s*)(?P<answer>.+?)\s*$"),
    re.compile(r"^(?P<prefix>.*?)(?P<marker>정\*\*답(?:\(AI답변\))?:?\*{0,2}\s*:?\s*)(?P<answer>.+?)\s*$"),
    re.compile(r"^(?P<prefix>(?:[-*]\s*)?)(?P<marker>(?:정답|답)(?:\(AI답변\))?\s*:\s*)(?P<answer>.+?)\s*$"),
)


def fin_corp_question_bank_answer_match(line: str) -> re.Match[str] | None:
    stripped = str(line or "").strip()
    for pattern in FIN_CORP_ANSWER_LINE_PATTERNS:
        match = pattern.match(stripped)
        if match:
            return match
    return None
FIN_CORP_FIELD_NAME = "금융공기업 IT 필기 239제"
FIN_CORP_SECTION = "전공필기"
FIN_CORP_SESSION_MODE = "practice"
FIN_CORP_MULTIPLE_CHOICE_POINTS = 4
FIN_CORP_SHORT_POINTS = 6
FIN_CORP_SUBJECTIVE_POINTS = 10
FIN_CORP_ESSAY_POINTS = 20
FIN_CORP_MULTIPLE_CHOICE_EXPECTED_SECONDS = 90
FIN_CORP_SHORT_EXPECTED_SECONDS = 4 * 60
FIN_CORP_SUBJECTIVE_EXPECTED_SECONDS = 8 * 60
FIN_CORP_ESSAY_EXPECTED_SECONDS = 20 * 60
FIN_CORP_MULTIPLE_CHOICE_ANSWER_GUIDE = "정답 선지 근거 1문장 + 오답 선지와 구분 포인트 1문장"
FIN_CORP_SHORT_ANSWER_GUIDE = "핵심 용어/정답 1문장 + 필요한 경우 근거 1문장"
FIN_CORP_SUBJECTIVE_ANSWER_GUIDE = "정의 → 핵심 원리 → 비교/주의점 → 금융IT 예시 순으로 3~5문장"
FIN_CORP_ESSAY_ANSWER_GUIDE = "문제 배경 → 핵심 원리 → 비교/원인 분석 → 개선안/적용 순으로 8~12문장"
FIN_CORP_SHORT_HINTS = (
    "뜻",
    "무엇",
    "단어",
    "용어",
    "크기는",
    "의미",
    "약어",
)
FIN_CORP_TITLE_CONTINUATION_SUFFIXES = (
    "에",
    "에서",
    "에게",
    "의",
    "를",
    "을",
    "는",
    "은",
    "이",
    "가",
    "와",
    "과",
    "및",
    "읽는",
    "달라지는",
)
FIN_CORP_CATEGORY_OVERRIDE_HINTS: dict[str, tuple[str, ...]] = {
    "데이터베이스": ("sql문", "sql ddl", "sql dml", "sql dcl", "sql tcl", "dense rank", "2pl", "2단계 잠금", "릴레이션", "후보키", "정규화", "트랜잭션", "group by", "having", "select "),
    "컴퓨터구조": ("gpu", "petabyte", "flip-flop", "플립플롭", "daisy chain", "alu", "raid", "rom", "ram", "파이프라인"),
    "자료구조·알고리즘": ("동적 계획법", "dynamic programming", "행렬", "역행렬", "연결리스트", "b-tree", "b+tree", "dfs", "bfs", "피보나치", "정렬 시간 복잡도", "시간복잡도", "정렬"),
    "클라우드·분산시스템": ("분산처리 시스템", "서버 가상화", "server virtualization", "virtualization", "하이브리드 클라우드", "커뮤니티 클라우드"),
    "프로그래밍 언어": ("python", "파이썬", "java", "c 언어", "c언어", "jvm", "바인딩", "오버로딩", "instance of", "재귀함수"),
    "금융IT·신기술": ("퍼블릭 블록체인", "public blockchain"),
    "운영체제": ("round robin", "sjf", "fcfs", "cpu 스케줄링", "페이지 교체", "lru"),
    "네트워크": ("osi", "pdu", "transport 계층", "https", "packet", "frame"),
    "인공지능·데이터": ("튜링테스트", "튜링 테스트"),
}
FIN_CORP_FALLBACK_CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "금융IT·신기술": ("오픈마켓", "ott", "메타버스", "디지털트윈", "크라우드 펀딩", "프롭테크", "알트코인", "핀테크", "블록체인", "퍼블릭 블록체인", "public blockchain", "약인공지능"),
    "네트워크": ("http", "https", "ssl", "tls", "vpn", "ssh", "x.25", "nic", "tcp", "udp", "라우팅", "lan", "wan", "dns", "osi", "pdu", "packet", "frame"),
    "데이터베이스": ("dba", "procedure", "dense rank", "grant", "revoke", "2pl", "schema", "트랜잭션", "정규화", "group by", "having", "select "),
    "보안": ("xss", "sql injection", "공인인증서", "다크웹", "랜섬웨어", "ddos", "중간자 공격", "rsa", "전자서명", "syn flood", "권한"),
    "소프트웨어공학": ("man month", "cocomo", "형상관리", "애자일", "스크럼", "인수테스트", "베타테스트", "결합도", "응집도", "fp기능점수", "cpm"),
    "운영체제": ("hrn", "페이지 폴트", "redo", "undo", "tlb", "페이징", "세그먼트", "동기화", "프로세서", "시분할시스템", "round robin", "sjf", "fcfs", "cpu 스케줄링", "lru"),
    "인공지능·데이터": ("빅데이터", "튜링테스트", "튜링 테스트", "드릴다운", "정형데이터", "gpu", "머신러닝", "하둡"),
    "자료구조·알고리즘": ("quick sort", "정렬", "시간 복잡도", "하노이탑", "bst", "heap", "b-tree", "b+tree", "dfs", "bfs", "피보나치", "연결리스트", "인접행렬", "동적 계획법", "플립플롭"),
    "컴퓨터구조": ("petabyte", "raid", "rom", "ram", "gpu", "flip-flop", "플립플롭", "daisy chain", "alu", "캐시", "가상화", "server virtualization"),
    "클라우드·분산시스템": ("분산처리 시스템", "서버 가상화", "하이브리드 클라우드", "커뮤니티 클라우드", "클라우드", "virtualization"),
    "프로그래밍 언어": ("python", "파이썬", "java", "c 언어", "c언어", "jvm", "바인딩", "오버로딩", "재귀함수", "instance of"),
}
FIN_CORP_HIGH_DIFFICULTY_HINTS = (
    "계산",
    "코드",
    "sql",
    "tlb",
    "서브넷",
    "트랜잭션",
    "정규화",
    "동시성",
    "b-tree",
    "b+tree",
    "dfs",
    "bfs",
    "행렬",
    "역행렬",
    "rsa",
    "dynamic programming",
    "동적 계획법",
)
FIN_CORP_MID_DIFFICULTY_HINTS = (
    "특징",
    "비교",
    "장단점",
    "설명",
    "권한",
    "라우팅",
    "raid",
    "테스트",
    "클라우드",
    "보안",
)
QUESTION_BANK_DIFFICULTY_LEVELS = {"상", "중", "하"}
QUESTION_BANK_DEFAULT_DIFFICULTY = "중"


FIN_CORP_CONCEPT_CONVERSION_MARKERS = (
    "계산문제",
    "출력결과",
    "트리그리기",
    "손코딩",
    "코드 문제",
    "코드 출력",
    "코드 주면서",
    "빈칸 채우기",
    "관련 서술식",
    "관련 문제",
    "보여주고",
    "객관식",
    "주관식",
    "전송순서",
    "약술",
    "뜻",
    "구하기",
)
FIN_CORP_FORCE_CONCEPT_TITLES = {
    "다음 중 스크립트 언어로 올바은 것은?",
    "다음중 DDL에 해당하지 않은 것은?",
    "딥웹, 다크웹에 대한 설명으로 옳지 않은 것은?",
    "블록체인 합의 알고리즘에 대해서 옳지 않은 것은?",
    "핀테크에 관한 설명 중 옳지 않은 것은?",
    "JAVA 상속코드 주면서 출력결과 쓰라는 문제",
    "인공지능에 대한 설명으로 적절한 것은?",
    "보기와 연관지을 수 있는 IT기술 용어는 무엇인가?",
    "버퍼오버플로우 관련 문제",
    "리눅스 권한 명령어 관련 문제(u(user), g(group), o(others)",
    "단일 프로세서 동기화 문제 유무, 발생한다면 어떤 경우인가?(서술)",
    "Redo, undo 관련 트랜잭션문제",
    "SSH Handshake 전송순서",
    "FP기능점수 계산",
    "CPM최단경로 구하기",
    "스머프어택 뜻",
    "AOE 유형 중 옳지 않은 것은?",
    "C코드의 결과값(전역변수, static 변수) (약술)",
    "터널링, vpn 약술",
    "JVM설명 약술",
    "DFS와 BFS와 그래프 경로&개념",
    "SQL문 약술",
    "C언어 파일입출력 틀린 개수 고르기",
}
FIN_CORP_SUBJECT_OVERRIDES = {
    "다음 중 스크립트 언어로 올바은 것은?": "스크립트 언어",
    "다음중 DDL에 해당하지 않은 것은?": "DDL과 DML",
    "딥웹, 다크웹에 대한 설명으로 옳지 않은 것은?": "딥웹과 다크웹",
    "블록체인 합의 알고리즘에 대해서 옳지 않은 것은?": "블록체인 합의 알고리즘",
    "핀테크에 관한 설명 중 옳지 않은 것은?": "핀테크",
    "인공지능에 대한 설명으로 적절한 것은?": "인공지능",
    "보기와 연관지을 수 있는 IT기술 용어는 무엇인가?": "IT 기술 용어",
    "빅데이터 3V 중에 아닌 것은?": "빅데이터 3V",
    "정렬 알고리즘 별 시간복잡도": "정렬 알고리즘 시간 복잡도",
    "다음 중 에러가 발생하지 않는 것은?": "SQL 문법 오류",
    "행렬계산. 다음 행렬 A와 B에 대해 A×B의 결과로 옳은 것은?": "행렬 곱셈",
    "역행렬계산. 다음 행렬 A와 B에 대해 A×B의 결과로 옳은 것은?": "역행렬",
    "다음 중 올바르게 연결된 것은?": "OSI 7계층 PDU",
    "어떤 값보다 큰 가장 작은 정수를 구하는 C언어 함수는?": "ceil 함수",
    "다음 중 정렬알고리즘이 최악인 것을 고르시오": "정렬 알고리즘 시간 복잡도",
    "다음 정렬알고리즘 중 평균이 다른 것을 고르시오": "평균 시간 복잡도",
    "순수 관계 연산자에서 릴레이션의 일부 속성만 추출하여 중복되는 튜플은 제거한 후 새로운 릴레이션을 생성하는 연산자는 무엇인가?": "PROJECT 연산",
    "리눅스 권한 명령어 관련 문제(u(user), g(group), o(others)": "리눅스 권한 명령어",
    "Redo, undo 관련 트랜잭션문제": "Redo와 Undo",
    "SSH Handshake 전송순서": "SSH Handshake",
    "FP기능점수 계산": "기능 점수",
    "CPM최단경로 구하기": "CPM 최단 경로",
    "스머프어택 뜻": "스머프 공격",
    "AOE 유형 중 옳지 않은 것은?": "AOE",
    "C코드의 결과값(전역변수, static 변수) (약술)": "C 언어의 전역 변수와 static 변수",
    "터널링, vpn 약술": "터널링과 VPN",
    "JVM설명 약술": "JVM",
    "DFS와 BFS와 그래프 경로&개념": "DFS와 BFS와 그래프 경로 탐색",
    "SQL문 약술": "SQL",
    "C언어 파일입출력 틀린 개수 고르기": "C 언어 파일 입출력",
    "(주관식)SQL 문제 약술 - REVOKE, GRANT": "REVOKE와 GRANT",
    "-rwsr-xr-x, s의 의미는?": "setuid 비트",
    "단일 프로세서 동기화 문제 유무, 발생한다면 어떤 경우인가?": "단일 프로세서 환경의 동기화",
}
FIN_CORP_CONVERTED_PROMPT_OVERRIDES = {
    "스크립트 언어": "스크립트 언어의 개념과 대표 예시를 설명하시오.",
    "DDL과 DML": "DDL과 DML의 차이를 설명하시오.",
    "REVOKE와 GRANT": "REVOKE와 GRANT의 역할을 설명하시오.",
    "DFS와 BFS와 그래프 경로 탐색": "DFS와 BFS의 개념과 그래프 경로 탐색 방법을 설명하시오.",
    "Redo와 Undo": "Redo와 Undo의 역할과 차이를 설명하시오.",
    "setuid 비트": "리눅스 setuid 비트의 의미를 설명하시오.",
    "기능 점수": "기능 점수(Function Point)의 개념과 계산 기준을 설명하시오.",
    "C 언어의 전역 변수와 static 변수": "C 언어의 전역 변수와 static 변수의 동작 차이를 설명하시오.",
    "터널링과 VPN": "터널링과 VPN의 개념과 차이를 설명하시오.",
    "C 언어 파일 입출력": "C 언어 파일 입출력의 핵심 개념과 주의점을 설명하시오.",
    "단일 프로세서 환경의 동기화": "단일 프로세서 환경에서도 동기화 문제가 발생하는 이유를 설명하시오.",
}
FIN_CORP_LIMITED_SOURCE_ANSWER = "문제의 선지/도표가 원문에 충분히 남아 있지 않아 단정형 정답은 제한적이다. 해당 주제의 핵심 개념과 대표 공식·특징을 기준으로 풀이해야 한다."
FIN_CORP_KEYWORD_DROP_TOKENS = (
    "문제",
    "객관식",
    "주관식",
    "설명하시오",
    "기술하시오",
    "작성하시오",
    "답하시오",
    "구하시오",
    "옳지 않은 것은",
    "옳은 것은",
    "적절한 것은",
    "알맞은 것은",
    "바른 설명은",
    "해당하는 용어",
    "관련 설명",
    "아래 지문에",
    "IT 기술 용어",
)


def clean_fin_corp_question_bank_title(value: str) -> str:
    return FIN_CORP_TITLE_PREFIX_RE.sub("", str(value or "").strip())



def fin_corp_question_bank_issuer(page_title: str) -> str:
    title = clean_fin_corp_question_bank_title(page_title)
    title = re.sub(r"\s+IT\s+기출$", "", title)
    title = re.sub(r"\s+기출$", "", title)
    return title.strip()



def fin_corp_question_bank_source_pages(repo_dir: Path | None = None) -> list[Path]:
    repo = wiki_book_dir(repo_dir)
    pages = wiki_pages_dir(repo)
    return sorted(path for path in pages.glob(FIN_CORP_QUESTION_BANK_PAGE_GLOB) if path.is_file())



def normalize_question_bank_match_text(value: Any) -> str:
    normalized = normalized_lookup_text(value).replace("c++", "cplusplus").replace("c#", "csharp")
    return re.sub(r"[^0-9a-z가-힣]+", "", normalized)



def fin_corp_question_bank_title_needs_continuation(title: str) -> bool:
    stripped = str(title or "").strip()
    if not stripped:
        return False
    if re.search(r"[?!.!…]$|[)）\]】]$|[\"'”]$", stripped):
        return False
    if stripped.count("(") > stripped.count(")"):
        return True
    if stripped.count("“") > stripped.count("”"):
        return True
    return any(stripped.endswith(suffix) for suffix in FIN_CORP_TITLE_CONTINUATION_SUFFIXES)



def fin_corp_question_bank_is_structural_line(line: str) -> bool:
    stripped = str(line or "").strip()
    if not stripped:
        return False
    if stripped == "보기":
        return True
    if stripped.startswith(("```", "|", "- ", "* ")):
        return True
    if fin_corp_question_bank_answer_match(stripped):
        return True
    if len(FIN_CORP_INLINE_CHOICE_RE.findall(stripped)) >= 2:
        return True
    return bool(FIN_CORP_CHOICE_LINE_RE.match(stripped))



def fin_corp_question_bank_promote_title_continuation(title: str, markdown_text: str) -> tuple[str, str]:
    content = str(markdown_text or "")
    if not fin_corp_question_bank_title_needs_continuation(title):
        return title.strip(), content.strip()
    lines = content.splitlines()
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start >= len(lines) or fin_corp_question_bank_is_structural_line(lines[start]):
        return title.strip(), content.strip()
    continuation: list[str] = []
    index = start
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            if continuation:
                index += 1
                break
            index += 1
            continue
        if continuation and fin_corp_question_bank_is_structural_line(stripped):
            break
        if fin_corp_question_bank_is_structural_line(stripped):
            break
        continuation.append(stripped)
        index += 1
    if not continuation:
        return title.strip(), content.strip()
    merged_title = f"{title.rstrip()} {' '.join(continuation)}".strip()
    remainder = "\n".join(lines[index:]).strip()
    return merged_title, remainder



def fin_corp_question_bank_inline_choices(line: str) -> list[str]:
    matches = [(number.strip(), text.strip()) for number, text in FIN_CORP_INLINE_CHOICE_RE.findall(str(line or "").strip())]
    if len(matches) < 2:
        return []
    return [f"{number}. {text}" for number, text in matches if text]



def fin_corp_question_bank_merge_code_fences(markdown_text: str) -> str:
    lines = str(markdown_text or "").splitlines()
    if not lines:
        return ""
    blocks: list[tuple[str, Any, Any]] = []
    index = 0
    while index < len(lines):
        if lines[index].strip().startswith("```"):
            fence = lines[index].strip() or "```"
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index].rstrip())
                index += 1
            if index < len(lines) and lines[index].strip().startswith("```"):
                index += 1
            blocks.append(("code", fence, code_lines))
            continue
        prose_lines: list[str] = []
        while index < len(lines) and not lines[index].strip().startswith("```"):
            prose_lines.append(lines[index].rstrip())
            index += 1
        blocks.append(("prose", prose_lines, None))
    merged_blocks: list[tuple[str, Any, Any]] = []
    index = 0
    while index < len(blocks):
        kind, first, second = blocks[index]
        if kind != "code":
            merged_blocks.append(blocks[index])
            index += 1
            continue
        fence = str(first)
        code_lines = list(second or [])
        next_index = index + 1
        while (
            next_index + 1 < len(blocks)
            and blocks[next_index][0] == "prose"
            and all(not str(line).strip() for line in (blocks[next_index][1] or []))
            and blocks[next_index + 1][0] == "code"
        ):
            if code_lines and code_lines[-1] != "":
                code_lines.append("")
            code_lines.extend(list(blocks[next_index + 1][2] or []))
            next_index += 2
        merged_blocks.append(("code", fence, code_lines))
        index = next_index
    rendered: list[str] = []
    for kind, first, second in merged_blocks:
        if kind == "prose":
            rendered.extend(list(first or []))
            continue
        rendered.append(str(first))
        rendered.extend(list(second or []))
        rendered.append("```")
    return "\n".join(rendered).strip()



def fin_corp_question_bank_choices(markdown_text: str) -> list[str]:
    choices: list[str] = []
    for line in str(markdown_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        inline_choices = fin_corp_question_bank_inline_choices(stripped)
        if inline_choices:
            choices.extend(item.split(". ", 1)[1] for item in inline_choices)
            continue
        if match := FIN_CORP_CHOICE_LINE_RE.match(stripped):
            choices.append(match.group(2).strip())
    return normalize_question_bank_list(choices, item_limit=2000)



def fin_corp_question_bank_answer_parts(markdown_text: str) -> tuple[str, str, str]:
    body_lines: list[str] = []
    trailing_lines: list[str] = []
    direct_answers: list[str] = []
    ai_answers: list[str] = []
    seen_answer = False
    for raw_line in str(markdown_text or "").splitlines():
        stripped = raw_line.strip()
        answer_match = fin_corp_question_bank_answer_match(stripped)
        if answer_match:
            seen_answer = True
            prefix = answer_match.group("prefix").strip()
            if prefix and prefix not in {"-", "*"}:
                body_lines.append(prefix)
            answer_text = normalize_question_bank_markdown(answer_match.group("answer"), limit=20000)
            if "AI답변" in answer_match.group("marker"):
                ai_answers.append(answer_text)
            else:
                direct_answers.append(answer_text)
            continue
        if seen_answer:
            trailing_lines.append(raw_line.rstrip())
        else:
            body_lines.append(raw_line.rstrip())
    body = "\n".join(body_lines).strip()
    answer = direct_answers[0] if direct_answers else (ai_answers[0] if ai_answers else "")
    explanation_parts: list[str] = []
    if ai_answers:
        explanation_parts.append("\n".join(ai_answers).strip())
    trailing = "\n".join(trailing_lines).strip()
    if trailing:
        explanation_parts.append(trailing)
    explanation = "\n\n".join(part for part in explanation_parts if part)
    if not explanation and answer:
        explanation = answer
    return body, answer, explanation



def fin_corp_question_bank_has_ai_only_answer(markdown_text: str) -> bool:
    saw_ai = False
    saw_direct = False
    for raw_line in str(markdown_text or "").splitlines():
        answer_match = fin_corp_question_bank_answer_match(raw_line.strip())
        if not answer_match:
            continue
        if "AI답변" in answer_match.group("marker"):
            saw_ai = True
        else:
            saw_direct = True
    return saw_ai and not saw_direct



def fin_corp_question_bank_normalize_body(markdown_text: str) -> str:
    normalized_lines: list[str] = []
    in_code = False
    choice_count = 0
    for raw_line in str(markdown_text or "").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            normalized_lines.append(raw_line.rstrip())
            continue
        if in_code:
            normalized_lines.append(raw_line.rstrip())
            continue
        inline_choices = fin_corp_question_bank_inline_choices(stripped)
        if inline_choices:
            normalized_lines.extend(inline_choices)
            choice_count += len(inline_choices)
            continue
        if FIN_CORP_CHOICE_LINE_RE.match(stripped):
            normalized_lines.append(raw_line.rstrip())
            choice_count += 1
            continue
        if choice_count and stripped.startswith(("-", "*")) and any(token in stripped for token in ("모두 옳", "모든 선지", "모든 지문")):
            special_choice = stripped.lstrip("-* ").strip()
            normalized_lines.append(f"{choice_count + 1}. {special_choice}")
            choice_count += 1
            continue
        normalized_lines.append(raw_line.rstrip())
    return fin_corp_question_bank_merge_code_fences("\n".join(normalized_lines).strip())


def fin_corp_question_bank_strip_duplicate_choices(markdown_text: str, *, question_type: str = "") -> str:
    body = str(markdown_text or "").strip()
    if question_type != "multiple_choice" or not body:
        return body
    sanitized_lines: list[str] = []
    in_code = False
    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            sanitized_lines.append(raw_line.rstrip())
            continue
        if in_code:
            sanitized_lines.append(raw_line.rstrip())
            continue
        if FIN_CORP_CHOICE_LINE_RE.match(stripped):
            continue
        sanitized_lines.append(raw_line.rstrip())
    sanitized = "\n".join(sanitized_lines)
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
    if sanitized in {"보기", "보기:", "보기 :"}:
        return ""
    return sanitized

def fin_corp_question_bank_all_true_choice_index(choices: list[str]) -> int | None:
    for index, choice in enumerate(choices):
        if any(token in str(choice or "") for token in ("모두 옳", "모든 선지", "모든 지문")):
            return index
    return None


def fin_corp_question_bank_is_all_true_answer(text: str) -> bool:
    normalized = normalize_question_bank_markdown(text, limit=20000)
    return any(token in normalized for token in ("모든선지", "모든 선지", "모든 지문", "모두 옳은", "모두 옳음", "전부 옳"))



def fin_corp_question_bank_all_true_choice(text: str) -> str:
    return normalize_question_bank_markdown(text, limit=20000)



def fin_corp_question_bank_topic(title: str) -> str:
    topic = re.sub(r"\s*\((?:약술|서술|논술|주관식)\)\s*$", "", str(title or "").strip(), flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", topic).strip()



def fin_corp_question_bank_type(title: str, body: str, answer: str, explanation: str, choices: list[str]) -> str:
    combined = "\n".join(part for part in (title, body, answer, explanation) if part)
    if "논술" in combined:
        return "essay"
    if choices:
        return "multiple_choice"
    if any(token in combined for token in ("약술", "서술", "설명하시오", "기술하시오", "비교", "장단점", "코드", "SQL", "작성하시오", "구하시오", "원인", "개선방안", "출력결과")):
        return "subjective"
    if any(token in title for token in FIN_CORP_SHORT_HINTS):
        return "short"
    return "subjective"



def fin_corp_question_bank_points(question_type: str) -> int:
    if question_type == "multiple_choice":
        return FIN_CORP_MULTIPLE_CHOICE_POINTS
    if question_type == "short":
        return FIN_CORP_SHORT_POINTS
    if question_type == "essay":
        return FIN_CORP_ESSAY_POINTS
    return FIN_CORP_SUBJECTIVE_POINTS



def fin_corp_question_bank_expected_seconds(question_type: str) -> int:
    if question_type == "multiple_choice":
        return FIN_CORP_MULTIPLE_CHOICE_EXPECTED_SECONDS
    if question_type == "short":
        return FIN_CORP_SHORT_EXPECTED_SECONDS
    if question_type == "essay":
        return FIN_CORP_ESSAY_EXPECTED_SECONDS
    return FIN_CORP_SUBJECTIVE_EXPECTED_SECONDS



def fin_corp_question_bank_answer_guide(question_type: str) -> str:
    if question_type == "multiple_choice":
        return FIN_CORP_MULTIPLE_CHOICE_ANSWER_GUIDE
    if question_type == "short":
        return FIN_CORP_SHORT_ANSWER_GUIDE
    if question_type == "essay":
        return FIN_CORP_ESSAY_ANSWER_GUIDE
    return FIN_CORP_SUBJECTIVE_ANSWER_GUIDE



def fin_corp_question_bank_override_category(title: str, body: str, answer: str, explanation: str) -> str:
    combined = "\n".join(part for part in (title, body, answer, explanation) if part)
    for category, hints in FIN_CORP_CATEGORY_OVERRIDE_HINTS.items():
        if any(fin_corp_question_bank_contains_hint(combined, hint) for hint in hints):
            return category
    return ""


def fin_corp_question_bank_contains_hint(text: str, hint: str) -> bool:
    haystack = str(text or "").casefold()
    needle = str(hint or "").casefold().strip()
    if not haystack or not needle:
        return False
    if re.fullmatch(r"[0-9a-z .+#/-]+", needle):
        return re.search(rf"(?<![0-9a-z]){re.escape(needle)}(?![0-9a-z])", haystack) is not None
    return needle in haystack


def fin_corp_question_bank_subject(title: str, *, card: dict[str, Any] | None = None) -> str:
    topic = fin_corp_question_bank_topic(title)
    subject = next((key for key, prompt in FIN_CORP_CONVERTED_PROMPT_OVERRIDES.items() if topic == prompt), "")
    if not subject:
        subject = FIN_CORP_SUBJECT_OVERRIDES.get(topic, topic)
    subject = re.sub(r"^\d+\.\s*", "", subject)
    subject = re.sub(r"^\[[^\]]+\]\s*", "", subject)
    subject = re.sub(r"^\((?:약술|서술|논술|주관식)\)\s*", "", subject, flags=re.IGNORECASE)
    subject = subject.rstrip(".?")
    extraction_patterns = (
        (r"^다음\s+중\s+(.+?)에서\s+없는\s+함수는\??$", r"\1"),
        (r"^다음\s+중\s+(.+?)인\s+것(?:은)?\??$", r"\1"),
        (r"^다음\s+중\s+(.+?)로\s+올바[른은].*$", r"\1"),
        (r"^다음\s+중\s+(.+?)\s+특징은\??$", r"\1"),
        (r"^다음중\s+(.+?)에\s+해당하지\s+않은\s+것은\??$", r"\1"),
        (r"^다음\s+(.+?)\s+코드(?:의)?\s*(?:실행)?\s*결과.*$", r"\1"),
        (r"^(.+?)에서\s+문자열을\s+비교하는\s+함수는\??$", r"\1"),
        (r"^(.+?)에서\s+우선순위\s+기준은\??$", r"\1"),
        (r"^.+?에서\s+(.+?)는\s+무엇인가\??$", r"\1"),
        (r"^(.+?)는\s+무엇인가\??$", r"\1"),
        (r"^(.+?)\s*특징으로\s+.*$", r"\1"),
        (r"^(.+?)의\s+특징이\s+.*$", r"\1"),
        (r"^(?:\d+\s+)?(.+?)의\s+크기는\??$", r"\1"),
        (r"^(.+?)\s*설명\s*중\s+.*$", r"\1"),
        (r"^(.+?)기능으로\s+.*$", r"\1"),
        (r"^(.+?)\s*(?:의)?\s*의미는\??$", r"\1"),
        (r"^(.+?)\s*뜻$", r"\1"),
        (r"^(.+?)\s+분류\s+및\s+특징.*$", r"\1"),
        (r"^(.+?)\s+관련\s+트랜잭션.*$", r"\1"),
        (r"^(.+?)\s+별\s+시간\s*복잡도$", r"\1"),
        (r"^SQL\s+문제\s+약술\s*-\s*(.+)$", r"\1"),
        (r"^.*서브넷\s+마스크.*$", "서브넷 마스크"),
        (r"^IP\s+주소\s+.+서브넷을\s+설계하시오.*$", "서브넷 설계"),
    )
    changed = True
    while changed:
        changed = False
        for pattern, replacement in extraction_patterns:
            updated = re.sub(pattern, replacement, subject, flags=re.IGNORECASE).strip()
            if updated and updated != subject:
                subject = updated
                changed = True
    cleanup_patterns = (
        r"\s*보여주고.*$",
        r"\s*주면서.*$",
        r"\s*에\s+대한\s+.*$",
        r"\s*에\s+대한$",
        r"\s*에\s+관한\s+.*$",
        r"\s*에\s+대해\s+.*$",
        r"\s*관련(?:하여)?\s+.*$",
        r"\s*설명\s*중$",
        r"\s*기능으로$",
        r"\s*기준은$",
        r"\s*(?:옳지 않은 것은|옳은 것은|적절한 것은|알맞은 것은|바른 설명은|해당하는 용어는|고르시오|선택하라는.*|선택.*|무엇인가\??).*$",
        r"\s*(?:계산문제|출력결과|트리그리기|손코딩|빈칸 채우기|코드(?:\s*문제)?|관련 서술식|관련 문제|문제 약술|객관식 문제|주관식 문제|문제)\s*$",
        r"\s*(?:뜻|의미|특징(?:으로)?|개념|약술|서술식|서술|설명)\s*$",
        r"\s*(?:의\s+개념과\s+차이를\s+설명하시오|의\s+의미를\s+(?:쓰시오|설명하시오)|의\s+특징을\s+설명하시오|의\s+역할(?:과\s+차이)?를\s+설명하시오|의\s+동작\s+차이를\s+설명하시오|에\s+대해\s+핵심\s+원리와\s+풀이\s+기준을\s+설명하시오|에\s+대해\s+설명하시오|를\s+간단히\s+설명하시오)\s*$",
    )
    changed = True
    while changed:
        changed = False
        for pattern in cleanup_patterns:
            updated = re.sub(pattern, "", subject, flags=re.IGNORECASE).strip()
            if updated and updated != subject:
                subject = updated
                changed = True
    replacements = {
        "시간복잡도": "시간 복잡도",
        "공간복잡도": "공간 복잡도",
        "최대힙": "최대 힙",
        "연결리스트": "연결 리스트",
        "이진트리": "이진 트리",
        "버퍼오버플로우": "버퍼 오버플로우",
        "페이지폴트": "페이지 폴트",
        "가상메모리": "가상 메모리",
        "C언어": "C 언어",
        "JAVA": "Java",
        "Rsa": "RSA",
        "vpn": "VPN",
    }
    for before, after in replacements.items():
        subject = subject.replace(before, after)
    subject = re.sub(r"\s+", " ", subject).strip(" -,:·/[]")
    if subject:
        return subject
    if isinstance(card, dict) and card.get("term"):
        return str(card.get("term") or "").strip()
    return topic


def fin_corp_question_bank_needs_concept_conversion(
    title: str,
    body: str,
    answer: str,
    explanation: str,
    *,
    question_type: str = "",
) -> bool:
    normalized_body = str(body or "").strip()
    topic = fin_corp_question_bank_topic(title)
    choices = fin_corp_question_bank_choices(body)
    if question_type == "multiple_choice":
        if len(choices) >= 2 and not (
            all(normalize_question_bank_text(choice, limit=20) in {"-", ""} for choice in choices)
            or ("transport 계층의 전송 단위(pdu)" in str(title or "").casefold() and "서버 내부 오류" in str(body or ""))
        ):
            return False
        if "transport 계층의 전송 단위(pdu)" in str(title or "").casefold() and "서버 내부 오류" in str(body or ""):
            return True
    elif normalized_body and topic not in FIN_CORP_FORCE_CONCEPT_TITLES:
        return False
    if topic in FIN_CORP_FORCE_CONCEPT_TITLES:
        return True
    if FIN_CORP_LIMITED_SOURCE_ANSWER in str(answer or ""):
        return True
    lowered = str(title or "").casefold()
    if question_type == "multiple_choice" and len(choices) < 2:
        return True
    if any(token in lowered for token in (
        "옳지 않은 것은",
        "옳은 것은",
        "적절한 것은",
        "알맞은 것은",
        "바른 설명은",
        "해당하는 용어는",
        "무엇인가",
    )) and len(choices) < 2:
        return True
    if not normalized_body and (lowered.startswith("다음 중") or lowered.startswith("다음중")):
        return True
    if any(marker.casefold() in lowered for marker in FIN_CORP_CONCEPT_CONVERSION_MARKERS):
        return True
    return not normalized_body and "문제" in lowered


def fin_corp_question_bank_converted_prompt(
    title: str,
    *,
    question_type: str = "",
    card: dict[str, Any] | None = None,
) -> str:
    subject = fin_corp_question_bank_subject(title, card=card)
    lowered = str(title or "").casefold()
    number_match = re.match(r"^\s*(\d+\.)\s*", str(title or ""))
    prompt = FIN_CORP_CONVERTED_PROMPT_OVERRIDES.get(subject, "")
    if not prompt:
        if "무엇인가" in lowered:
            prompt = f"{subject}의 의미를 설명하시오."
        elif any(token in lowered for token in ("비교", "차이", "장단점")):
            prompt = f"{subject}의 개념과 차이를 설명하시오."
        elif any(token in lowered for token in ("뜻", "의미", "약어")):
            prompt = f"{subject}의 의미를 {'쓰시오' if question_type == 'short' else '설명하시오'}."
        elif "특징" in lowered:
            prompt = f"{subject}의 특징을 설명하시오."
        elif any(token in lowered for token in ("계산문제", "출력결과", "구하기", "손코딩", "트리그리기", "코드")):
            prompt = f"{subject}에 대해 핵심 원리와 풀이 기준을 설명하시오."
        elif any(token in lowered for token in ("약술", "서술", "설명", "개념")):
            prompt = f"{subject}에 대해 설명하시오."
        elif question_type == "short":
            prompt = f"{subject}를 간단히 설명하시오."
        else:
            prompt = f"{subject}에 대해 설명하시오."
    prompt = re.sub(r"\s+", " ", prompt).strip()
    if number_match:
        prompt = f"{number_match.group(1)} {prompt}"
    return prompt


def fin_corp_question_bank_topic_particle(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "는"
    last = text[-1]
    if not ('가' <= last <= '힣'):
        return "는"
    return "은" if (ord(last) - ord('가')) % 28 else "는"


def fin_corp_question_bank_conversion_note(title: str) -> str:
    original_title = fin_corp_question_bank_topic(title)
    lowered = original_title.casefold()
    if any(token in lowered for token in ("계산문제", "출력결과", "구하기", "손코딩", "트리그리기", "코드")):
        reason = "원문에 계산/코드/입력 조건이 충분히 남아 있지 않아 개념문제로 변환함."
    else:
        reason = "원문에 선택지/세부 조건이 충분히 남아 있지 않아 개념문제로 변환함."
    return f"변환 메모: {reason}\n원문 제목: {original_title}"


def fin_corp_question_bank_answer_is_meaningful(answer: str) -> bool:
    text = normalize_question_bank_text(answer, limit=500)
    if not text or text in {"*", "-"}:
        return False
    if re.fullmatch(r"\d+번", text):
        return False
    return True


def fin_corp_question_bank_should_prefer_card_answer(
    title: str,
    answer: str,
    *,
    question_type: str = "",
    card: dict[str, Any] | None = None,
) -> bool:
    if not isinstance(card, dict) or not card:
        return False
    if FIN_CORP_LIMITED_SOURCE_ANSWER in str(answer or "") or not fin_corp_question_bank_answer_is_meaningful(answer):
        return True
    lowered = str(title or "").casefold()
    subject_tokens = fin_corp_question_bank_tokens(fin_corp_question_bank_subject(title, card=card))
    answer_tokens = fin_corp_question_bank_tokens(answer)
    if any(token in lowered for token in ("옳지 않은 것은", "옳은 것은", "적절한 것은", "알맞은 것은", "바른 설명은", "무엇인가")):
        if subject_tokens and not (subject_tokens & answer_tokens):
            return True
        if len(normalize_question_bank_text(answer, limit=200)) < 40:
            return True
    if question_type != "multiple_choice" and any(token in lowered for token in ("계산문제", "출력결과", "구하기", "손코딩", "트리그리기", "코드")):
        if len(normalize_question_bank_text(answer, limit=200)) < 24:
            return True
    return False


def fin_corp_question_bank_converted_answer(
    title: str,
    answer: str,
    explanation: str,
    *,
    category: str = "",
    card: dict[str, Any] | None = None,
    prefer_card_answer: bool = False,
) -> tuple[str, str]:
    lowered = str(title or "").casefold()
    if "transport 계층" in lowered and "pdu" in lowered:
        converted_answer = "Transport 계층의 PDU는 TCP에서는 세그먼트(segment), UDP에서는 데이터그램(datagram)이다."
        converted_explanation = converted_answer + "\n\nPDU는 각 계층에서 전달되는 데이터 단위를 뜻하며, 네트워크 계층은 packet, 데이터 링크 계층은 frame, 물리 계층은 bit로 구분한다."
        return converted_answer, converted_explanation
    if isinstance(card, dict) and card and (prefer_card_answer or FIN_CORP_LIMITED_SOURCE_ANSWER in str(answer or "")):
        grounded_answer, grounded_explanation = fin_corp_question_bank_grounded_card_answer(card)
        if grounded_answer:
            return grounded_answer, grounded_explanation
    if fin_corp_question_bank_answer_is_meaningful(answer) and not prefer_card_answer and FIN_CORP_LIMITED_SOURCE_ANSWER not in str(answer or ""):
        return answer, explanation
    subject = fin_corp_question_bank_subject(title, card=card)
    if "sql" in lowered:
        converted_answer = "집계 SQL에서는 GROUP BY로 그룹을 나눈 뒤 COUNT로 개수를 계산하고, 그 결과에서 MAX나 ORDER BY DESC LIMIT 같은 방식으로 최댓값을 구한다."
        converted_explanation = converted_answer + "\n\n실전에서는 서브쿼리, HAVING, ORDER BY를 조합해 그룹별 개수와 최댓값 조건을 함께 표현한다."
        return converted_answer, converted_explanation
    if any(token in lowered for token in ("python", "java", "c언어", "코드", "출력결과")):
        converted_answer = "코드 실행 결과를 해석할 때는 변수 초기화, 연산자 우선순위, 조건 분기, 반복문, 함수 호출 순서, 참조 공유 여부를 단계적으로 추적해야 한다."
        converted_explanation = converted_answer + "\n\n전역/static 변수, 증감 연산, 배열·리스트 변경, 값 전달과 참조 전달 차이를 먼저 확인하면 대부분의 출력 결과 문제를 구조적으로 풀 수 있다."
        return converted_answer, converted_explanation
    if any(token in lowered for token in ("공개키", "rsa", "전자서명")) or category == "보안":
        particle = fin_corp_question_bank_topic_particle(subject)
        converted_answer = f"{subject}{particle} 보안에서 자주 쓰이는 핵심 개념으로, 기본 원리와 활용 목적을 함께 설명할 수 있어야 한다."
        converted_explanation = converted_answer + "\n\n대표 예시, 적용 위치, 장단점 또는 관련 공격/대응 방식까지 함께 정리하면 서술형 대비에 도움이 된다."
        return converted_answer, converted_explanation
    converted_answer = f"{subject}의 핵심 개념과 대표 원리·판단 기준을 설명할 수 있어야 한다."
    converted_explanation = converted_answer
    return converted_answer, converted_explanation


def fin_corp_question_bank_convert_incomplete_row(
    title: str,
    body: str,
    answer: str,
    explanation: str,
    *,
    question_type: str = "",
    category: str = "",
    card: dict[str, Any] | None = None,
) -> tuple[str, str, str, str]:
    if not fin_corp_question_bank_needs_concept_conversion(title, body, answer, explanation, question_type=question_type):
        return title, body, answer, explanation
    converted_title = fin_corp_question_bank_converted_prompt(title, question_type=question_type, card=card)
    converted_body = fin_corp_question_bank_conversion_note(title)
    converted_answer, converted_explanation = fin_corp_question_bank_converted_answer(
        title,
        answer,
        explanation,
        category=category,
        card=card,
        prefer_card_answer=fin_corp_question_bank_should_prefer_card_answer(title, answer, question_type=question_type, card=card),
    )
    return converted_title, converted_body, converted_answer, converted_explanation


def fin_corp_question_bank_keyword_noise(value: str) -> bool:
    text = normalize_question_bank_text(value, limit=80)
    if not text:
        return True
    if text in {"*", "-"} or len(text) <= 1:
        return True
    if text.endswith("번") and re.fullmatch(r"\d+번", text):
        return True
    if re.search(r"\d", text) and re.search(r"[A-Za-z가-힣]{2,}", text):
        return False
    if re.fullmatch(r"[0-9,./%\- ]+[A-Za-z가-힣]{0,3}", text):
        return True
    if any(token in text for token in FIN_CORP_KEYWORD_DROP_TOKENS):
        return True
    if len(text) > 28 and text.count(" ") >= 2:
        return True
    if text.count(" ") >= 4:
        return True
    if text.endswith(("이다.", "한다.", "있다.")):
        return True
    return False


def fin_corp_question_bank_answer_can_seed_keywords(answer: str) -> bool:
    text = normalize_question_bank_text(answer, limit=120)
    if not fin_corp_question_bank_answer_is_meaningful(text):
        return False
    if len(text) > 40 or text.count(" ") >= 4:
        return False
    if text.endswith((".", "다")):
        return False
    if any(token in text for token in (":", ";", "```", "=", "(")):
        return False
    if text[0].isdigit():
        return False
    return True

def fin_corp_question_bank_choice_can_seed_keywords(choice_text: str) -> bool:
    text = normalize_question_bank_text(choice_text, limit=120)
    if not text:
        return False
    if any(symbol in text for symbol in ("=", "+", "/")) and not re.search(r"[A-Za-z]{2,}", text):
        return False
    if text.count(" ") >= 4:
        return False
    return True

def fin_corp_question_bank_subject_keyword_candidates(subject: str) -> list[str]:
    normalized = normalize_question_bank_text(subject, limit=255)
    if not normalized:
        return []
    candidates = list(bok_topic_keyword_candidates(normalized))
    split_pattern = re.compile(r"\s*(?:,|/|&|\bvs\b|와|과|및)\s*", re.IGNORECASE)
    for piece in split_pattern.split(normalized):
        cleaned = bok_normalize_keyword_fragment(piece)
        if cleaned and not bok_keyword_is_noise(cleaned):
            candidates.append(cleaned)
    return normalize_question_bank_list(candidates, item_limit=255)


def fin_corp_question_bank_text_contains_keyword(keyword: str, *texts: str) -> bool:
    raw = "\n".join(str(text or "") for text in texts)
    needle = str(keyword or "").strip()
    if not raw or not needle:
        return False
    if re.search(r"[가-힣]", needle):
        return needle.casefold() in raw.casefold()
    if re.fullmatch(r"[A-Za-z0-9.+#\-/ ]+", needle) and len(needle) <= 4:
        return bool(re.search(rf"(?<![0-9A-Za-z]){re.escape(needle)}(?![0-9A-Za-z])", raw, flags=re.IGNORECASE))
    needle_key = normalize_question_bank_match_text(needle)
    haystack_key = normalize_question_bank_match_text(raw)
    return bool(needle_key and haystack_key and needle_key in haystack_key)


def fin_corp_question_bank_registered_keyword_candidates(
    rows: list[dict[str, Any]],
    title: str,
    body: str,
    answer: str,
    explanation: str,
    *,
    card: dict[str, Any] | None = None,
    choice_text: str = "",
) -> list[str]:
    candidates: list[str] = []
    effective_choice_text = choice_text if fin_corp_question_bank_choice_can_seed_keywords(choice_text) else ""
    texts = (title, body, effective_choice_text)
    current_term_key = normalize_question_bank_match_text(card.get("term")) if isinstance(card, dict) else ""
    current_english_key = normalize_question_bank_match_text(card.get("english")) if isinstance(card, dict) else ""
    if isinstance(card, dict) and card:
        candidates.extend([str(card.get("term") or ""), str(card.get("english") or "")])
    for row in rows:
        canonical = str(row.get("term") or row.get("english") or "").strip()
        canonical_key = normalize_question_bank_match_text(canonical)
        if not canonical or not canonical_key:
            continue
        if current_term_key and canonical_key in current_term_key:
            continue
        if current_english_key and canonical_key in current_english_key:
            continue
        if re.search(r"[가-힣]", canonical) and len(canonical_key) < 4:
            continue
        if fin_corp_question_bank_text_contains_keyword(str(row.get("term") or ""), *texts):
            candidates.append(canonical)
            continue
        if fin_corp_question_bank_text_contains_keyword(str(row.get("english") or ""), *texts):
            candidates.append(canonical)
    return normalize_question_bank_list(candidates, item_limit=255)


def fin_corp_question_bank_keyword_candidates(
    title: str,
    answer: str,
    *,
    body: str = "",
    card: dict[str, Any] | None = None,
    choice_text: str = "",
) -> list[str]:
    subject = fin_corp_question_bank_subject(title, card=card)
    candidates: list[str] = []
    effective_choice_text = choice_text if fin_corp_question_bank_choice_can_seed_keywords(choice_text) else ""
    if isinstance(card, dict) and card:
        candidates.extend([str(card.get("term") or ""), str(card.get("english") or "")])
    candidates.extend(fin_corp_question_bank_subject_keyword_candidates(subject))
    if effective_choice_text:
        candidates.extend(fin_corp_question_bank_subject_keyword_candidates(effective_choice_text))
    if fin_corp_question_bank_answer_can_seed_keywords(answer):
        candidates.extend(fin_corp_question_bank_subject_keyword_candidates(answer))
    return normalize_question_bank_list(candidates, item_limit=255)


def fin_corp_question_bank_category(
    title: str,
    body: str,
    answer: str,
    explanation: str,
    *,
    card_category: str = "",
    progress_db_path: Path | None = None,
) -> str:
    override = fin_corp_question_bank_override_category(title, body, answer, explanation)
    if override:
        return override
    combined_body = "\n\n".join(part for part in (body, answer, explanation) if part)
    category = infer_question_bank_category(
        card_category,
        card_category=card_category,
        topic=fin_corp_question_bank_subject(title),
        prompt=f"### {title}",
        body=combined_body,
        progress_db_path=progress_db_path,
    )
    if category:
        return category
    combined = "\n".join(part for part in (title, body, answer, explanation) if part)
    for fallback_category, hints in FIN_CORP_FALLBACK_CATEGORY_HINTS.items():
        if any(fin_corp_question_bank_contains_hint(combined, hint) for hint in hints):
            return fallback_category
    return card_category or "금융IT·신기술"


def fin_corp_question_bank_keywords(
    title: str,
    body: str,
    answer: str,
    explanation: str,
    *,
    card: dict[str, Any] | None = None,
    rows: list[dict[str, Any]] | None = None,
    choice_text: str = "",
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    candidates: list[str] = []
    if isinstance(rows, list) and rows:
        candidates.extend(fin_corp_question_bank_registered_keyword_candidates(rows, title, body, answer, explanation, card=card, choice_text=choice_text))
    candidates.extend(fin_corp_question_bank_keyword_candidates(title, answer, body=body, card=card, choice_text=choice_text))
    if not isinstance(card, dict) or not card:
        if not str(body or "").startswith("변환 메모:") or not candidates:
            candidates.extend(bok_detect_keyword_matches(title, body, answer, explanation))
    for candidate in candidates:
        normalized = bok_normalize_keyword_fragment(candidate)
        key = normalize_question_bank_match_text(normalized) or normalized.casefold()
        if not normalized or key in seen or fin_corp_question_bank_keyword_noise(normalized):
            continue
        seen.add(key)
        ordered.append(normalized)
    if not ordered:
        subject = bok_normalize_keyword_fragment(fin_corp_question_bank_subject(title, card=card))
        if subject and not fin_corp_question_bank_keyword_noise(subject):
            ordered.append(subject)
    return ordered[:6]


def fin_corp_question_bank_card_is_grounded(
    card: dict[str, Any] | None,
    title: str,
    body: str,
    answer: str,
    explanation: str,
) -> bool:
    if not isinstance(card, dict) or not card:
        return False
    title_key = normalize_question_bank_match_text(title)
    candidate_keys = fin_corp_question_bank_candidate_keys(title, body, answer, explanation)
    for raw_value in (card.get("term"), card.get("english")):
        key = normalize_question_bank_match_text(raw_value)
        if not key:
            continue
        if key in candidate_keys:
            return True
        if len(key) >= 4 and key in title_key:
            return True
    return False


def fin_corp_question_bank_candidate_keys(title: str, body: str, answer: str, explanation: str) -> set[str]:
    subject = fin_corp_question_bank_subject(title)
    include_answer = not str(body or "").startswith("변환 메모:")
    short_answer = answer if include_answer and len(answer) <= 120 else ""
    candidate_terms = normalize_question_bank_list([
        fin_corp_question_bank_topic(title),
        subject,
        *bok_topic_keyword_candidates(subject),
        short_answer,
        *bok_topic_keyword_candidates(short_answer),
    ], item_limit=255)
    return {normalize_question_bank_match_text(item) for item in candidate_terms if normalize_question_bank_match_text(item)}



def fin_corp_question_bank_card(
    rows: list[dict[str, Any]],
    title: str,
    body: str,
    answer: str,
    explanation: str,
    *,
    category: str = "",
) -> dict[str, Any]:
    combined = "\n".join(part for part in (title, body, answer, explanation) if part)
    match_text = normalize_question_bank_match_text(combined)
    if not match_text:
        return {}
    candidate_keys = fin_corp_question_bank_candidate_keys(title, body, answer, explanation)
    topic_key = normalize_question_bank_match_text(fin_corp_question_bank_topic(title))
    answer_key = normalize_question_bank_match_text(answer)
    best_score = 0
    best_card: dict[str, Any] = {}
    for row in rows:
        row_score = 0
        direct_hit = False
        term_key = normalize_question_bank_match_text(row.get("term"))
        english_key = normalize_question_bank_match_text(row.get("english"))
        direct_keys = tuple(key for key in (term_key, english_key) if key)
        for direct_key in direct_keys:
            if direct_key in candidate_keys:
                row_score = max(row_score, 640 + len(direct_key))
                direct_hit = True
            elif len(direct_key) >= 4 and direct_key in match_text:
                row_score = max(row_score, 420 + len(direct_key))
                direct_hit = True
        if not direct_hit:
            related_hits = 0
            for keyword in question_bank_keywords_for_card(row):
                keyword_key = normalize_question_bank_match_text(keyword)
                if len(keyword_key) < 4 or keyword_key in direct_keys:
                    continue
                if keyword_key in candidate_keys:
                    related_hits += 1
                    row_score = max(row_score, 300 + related_hits * 40 + len(keyword_key))
            if related_hits < 2:
                continue
        if category and row.get("category") == category:
            row_score += 40
        if term_key and term_key == topic_key:
            row_score += 80
        if answer_key and term_key and term_key == answer_key:
            row_score += 120
        if answer_key and english_key and english_key == answer_key:
            row_score += 120
        if row_score > best_score:
            best_score = row_score
            best_card = row
    if best_score < 400:
        return {}
    return best_card



def fin_corp_question_bank_tokens(value: str) -> set[str]:
    return {token.casefold() for token in re.findall(r"[0-9A-Za-z가-힣]{2,}", str(value or ""))}



def fin_corp_question_bank_grounded_card_answer(card: dict[str, Any]) -> tuple[str, str]:
    parts: list[str] = []
    for raw_value in (card.get("definition"), card.get("detailed_explanation"), card.get("exam_note")):
        normalized = normalize_question_bank_markdown(raw_value, limit=20000)
        if normalized and normalized not in parts:
            parts.append(normalized)
    if not parts:
        fallback = normalize_question_bank_markdown(card.get("term"), limit=20000)
        return fallback, fallback
    return parts[0], "\n\n".join(parts)



def fin_corp_question_bank_salvage_answer_from_explanation(answer: str, explanation: str) -> str:
    if fin_corp_question_bank_answer_is_meaningful(answer):
        return answer
    for raw_line in str(explanation or "").splitlines():
        cleaned = re.sub(r"^[#>*\-\s]+", "", raw_line).strip()
        normalized = normalize_question_bank_text(cleaned, limit=500)
        if normalized and len(normalized) >= 4:
            return normalized
    return answer


def fin_corp_question_bank_repair_answer(
    title: str,
    body: str,
    answer: str,
    explanation: str,
    *,
    card: dict[str, Any] | None = None,
    question_type: str = "",
    ai_only: bool = False,
) -> tuple[str, str]:
    if "dp[i] = ㄱ" in body and "dp2[i] = ㄴ" in body:
        repaired_answer = "ㄱ = max(dfs(i - 1), dfs(i - 2) + arr[i]), ㄴ = max(dp2[i - 1], dp2[i - 2] + arr[i])"
        repaired_explanation = "동적 계획법 점화식이다. 인접한 두 원소를 동시에 선택하지 않는 최대합을 구하므로 직전 값과 두 칸 전 값에 현재 값을 더한 경우를 비교한다.\n\n- Top-down: dp[i] = max(dfs(i - 1), dfs(i - 2) + arr[i])\n- Bottom-up: dp2[i] = max(dp2[i - 1], dp2[i - 2] + arr[i])"
        return repaired_answer, repaired_explanation
    if question_type == "multiple_choice":
        return answer, explanation
    salvaged_answer = fin_corp_question_bank_salvage_answer_from_explanation(answer, explanation)
    if salvaged_answer != answer:
        return salvaged_answer, explanation
    if not ai_only or not isinstance(card, dict) or not card:
        return answer, explanation
    if answer != explanation:
        return answer, explanation
    topic_key = normalize_question_bank_match_text(fin_corp_question_bank_topic(title))
    term_key = normalize_question_bank_match_text(card.get("term"))
    english_key = normalize_question_bank_match_text(card.get("english"))
    if not ((term_key and term_key in topic_key) or (english_key and english_key in topic_key)):
        return answer, explanation
    answer_key = normalize_question_bank_match_text(answer)
    if (term_key and term_key in answer_key) or (english_key and english_key in answer_key):
        return answer, explanation
    if fin_corp_question_bank_tokens(fin_corp_question_bank_topic(title)) & fin_corp_question_bank_tokens(answer):
        return answer, explanation
    grounded_answer, grounded_explanation = fin_corp_question_bank_grounded_card_answer(card)
    return grounded_answer or answer, grounded_explanation or explanation



def normalized_question_bank_difficulty(value: Any) -> str:
    difficulty = normalize_question_bank_text(value, limit=64)
    return difficulty if difficulty in QUESTION_BANK_DIFFICULTY_LEVELS else ""



def infer_question_bank_difficulty(
    question_type: str,
    prompt: str,
    body: str,
    answer: str,
    explanation: str,
    *,
    card: dict[str, Any] | None = None,
) -> str:
    normalized_question_type = normalize_question_bank_text(question_type, limit=64).lower()
    card_difficulty = normalized_question_bank_difficulty(card.get("difficulty")) if isinstance(card, dict) else ""
    if card_difficulty:
        if normalized_question_type == "essay":
            return "상"
        return card_difficulty
    combined = "\n".join(part for part in (prompt, body, answer, explanation) if part).casefold()
    if normalized_question_type == "essay":
        return "상"
    if normalized_question_type in {"multiple_choice", "short"}:
        if any(hint.casefold() in combined for hint in FIN_CORP_HIGH_DIFFICULTY_HINTS):
            return "중"
        return "하"
    if "```" in body or any(hint.casefold() in combined for hint in FIN_CORP_HIGH_DIFFICULTY_HINTS):
        return "상"
    if any(hint.casefold() in combined for hint in FIN_CORP_MID_DIFFICULTY_HINTS):
        return "중"
    return "중"



def backfill_question_bank_difficulty_rows(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT id, card_id, question_type, prompt, body, answer, explanation, difficulty, keywords_json, missing_card_keywords_json
        FROM question_bank
        """
    ).fetchall()
    if not rows:
        return
    card_ids = sorted({str(row["card_id"] or "").strip() for row in rows if str(row["card_id"] or "").strip()})
    card_map: dict[str, dict[str, Any]] = {}
    if card_ids:
        qmarks = ", ".join("?" for _ in card_ids)
        card_rows = conn.execute(
            f"SELECT card_id, term, english, related_concepts, difficulty FROM cards WHERE card_id IN ({qmarks})",
            tuple(card_ids),
        ).fetchall()
        card_map = {
            str(row["card_id"] or "").strip(): {
                "term": row["term"] or "",
                "english": row["english"] or "",
                "related_concepts": row["related_concepts"] or "",
                "difficulty": row["difficulty"] or "",
            }
            for row in card_rows
            if str(row["card_id"] or "").strip()
        }
    difficulty_updates: list[tuple[str, str]] = []
    keyword_updates: list[tuple[str, str]] = []
    for row in rows:
        card = card_map.get(str(row["card_id"] or "").strip())
        expected_keywords = question_bank_keywords_for_linked_card(card)
        current_keywords = question_bank_json_list(row["keywords_json"] if "keywords_json" in row.keys() else "[]")
        if current_keywords != expected_keywords:
            keyword_updates.append((question_bank_json_text(expected_keywords, item_limit=255), row["id"]))
        current_difficulty = normalized_question_bank_difficulty(row["difficulty"] if "difficulty" in row.keys() else "")
        expected_difficulty = current_difficulty
        if not expected_difficulty:
            card_difficulty = normalized_question_bank_difficulty(card.get("difficulty")) if isinstance(card, dict) else ""
            question_type = normalize_question_bank_text(row["question_type"] or "", limit=64).lower()
            if card_difficulty:
                expected_difficulty = infer_question_bank_difficulty(
                    row["question_type"] or "",
                    row["prompt"] or "",
                    row["body"] or "",
                    row["answer"] or "",
                    row["explanation"] or "",
                    card=card,
                )
            elif question_type == "essay":
                expected_difficulty = "상"
            else:
                expected_difficulty = QUESTION_BANK_DEFAULT_DIFFICULTY
        if current_difficulty != expected_difficulty:
            difficulty_updates.append((expected_difficulty, row["id"]))
    if keyword_updates:
        conn.executemany("UPDATE question_bank SET keywords_json = ? WHERE id = ?", keyword_updates)
    if difficulty_updates:
        conn.executemany("UPDATE question_bank SET difficulty = ? WHERE id = ?", difficulty_updates)




def fin_corp_question_bank_difficulty(
    question_type: str,
    title: str,
    body: str,
    answer: str,
    explanation: str,
    *,
    card: dict[str, Any] | None = None,
) -> str:
    return infer_question_bank_difficulty(question_type, title, body, answer, explanation, card=card)




def parse_fin_corp_question_bank_entries(
    repo_dir: Path | None = None,
    progress_db_path: Path | None = PROGRESS_DB_PATH,
) -> list[dict[str, Any]]:
    rows, _ = read_cards(progress_db_path)
    entries: list[dict[str, Any]] = []
    for source_path in fin_corp_question_bank_source_pages(repo_dir):
        text = source_path.read_text(encoding="utf-8")
        page_title = clean_fin_corp_question_bank_title(extract_markdown_title(text, source_path.stem))
        issuer = fin_corp_question_bank_issuer(page_title)
        matches = list(FIN_CORP_QUESTION_HEADING_RE.finditer(text))
        page_code = "-".join(source_path.stem.split("-")[:2]) or source_path.stem
        for offset, match in enumerate(matches, start=1):
            question_number = int(match.group(1))
            title = match.group(2).strip()
            start = match.end()
            next_question_start = matches[offset].start() if offset < len(matches) else len(text)
            remaining = text[start:next_question_start]
            section_match = re.search(r"^##\s+", remaining, re.MULTILINE)
            if section_match:
                end = start + section_match.start()
            else:
                end = next_question_start
            content = text[start:end].strip()
            title, content = fin_corp_question_bank_promote_title_continuation(title, content)
            body, answer, explanation = fin_corp_question_bank_answer_parts(content)
            body = fin_corp_question_bank_normalize_body(body)
            choices = fin_corp_question_bank_choices(body)
            question_type = fin_corp_question_bank_type(title, body, answer, explanation, choices)
            provisional_category = fin_corp_question_bank_category(
                title,
                body,
                answer,
                explanation,
                        progress_db_path=progress_db_path,
            )
            card = fin_corp_question_bank_card(rows, title, body, answer, explanation, category=provisional_category)
            if not fin_corp_question_bank_card_is_grounded(card, title, body, answer, explanation):
                card = {}
            answer, explanation = fin_corp_question_bank_repair_answer(
                title,
                body,
                answer,
                explanation,
                card=card,
                question_type=question_type,
                ai_only=fin_corp_question_bank_has_ai_only_answer(content),
            )
            title, body, answer, explanation = fin_corp_question_bank_convert_incomplete_row(
                title,
                body,
                answer,
                explanation,
                question_type=question_type,
                category=provisional_category,
                card=card,
            )
            body = fin_corp_question_bank_normalize_body(body)
            choices = fin_corp_question_bank_choices(body)
            question_type = fin_corp_question_bank_type(title, body, answer, explanation, choices)
            provisional_category = fin_corp_question_bank_category(
                title,
                body,
                answer,
                explanation,
                        progress_db_path=progress_db_path,
            )
            card = fin_corp_question_bank_card(rows, title, body, answer, explanation, category=provisional_category)
            if not fin_corp_question_bank_card_is_grounded(card, title, body, answer, explanation):
                card = {}
            category = fin_corp_question_bank_category(
                title,
                body,
                answer,
                explanation,
                card_category=str(card.get("category") or provisional_category),
                        progress_db_path=progress_db_path,
            )
            answer_index = None
            if question_type == "multiple_choice":
                answer_key = normalize_question_bank_match_text(answer)
                number_match = re.search(r"(?<!\d)(\d+)\s*번", answer)
                if number_match:
                    numeric_index = int(number_match.group(1)) - 1
                    if 0 <= numeric_index < len(choices):
                        answer_index = numeric_index
                elif answer_key:
                    for index, choice in enumerate(choices):
                        choice_key = normalize_question_bank_match_text(choice)
                        if choice_key and (choice_key == answer_key or choice_key in answer_key or answer_key in choice_key):
                            answer_index = index
                            break
                if answer_index is None:
                    special_index = fin_corp_question_bank_all_true_choice_index(choices)
                    if special_index is not None and fin_corp_question_bank_has_ai_only_answer(content):
                        original_answer = answer
                        answer = f"{special_index + 1}번"
                        answer_index = special_index
                        special_choice = choices[special_index]
                        explanation_parts = [special_choice]
                        if original_answer and original_answer not in explanation_parts:
                            explanation_parts.append(original_answer)
                        if explanation and explanation not in explanation_parts:
                            explanation_parts.append(explanation)
                        explanation = "\n\n".join(part for part in explanation_parts if part)
                    elif fin_corp_question_bank_is_all_true_answer(answer):
                        special_choice = fin_corp_question_bank_all_true_choice(answer)
                        if special_choice and special_choice not in choices:
                            choices.append(special_choice)
                        if special_choice:
                            answer_index = choices.index(special_choice)
                            answer = f"{answer_index + 1}번"
                            if explanation and special_choice not in explanation:
                                explanation = "\n\n".join(part for part in (special_choice, explanation) if part)
                            elif not explanation:
                                explanation = special_choice
            choice_text = choices[answer_index] if answer_index is not None and 0 <= answer_index < len(choices) else ""
            stored_body = fin_corp_question_bank_strip_duplicate_choices(body, question_type=question_type)
            entries.append({
                "question_bank_id": f"qb-fin239-{page_code}-{offset:02d}",
                "card_id": str(card.get("id") or ""),
                "question_type": question_type,
                "prompt": f"### {question_number}. {title}",
                "body": stored_body,
                "answer": answer,
                "explanation": explanation,
                "rubric": [],
                "choices": choices,
                "answer_index": answer_index,
                "topic": fin_corp_question_bank_topic(title),
                "field_name": FIN_CORP_FIELD_NAME,
                "category": category,
                "keywords": question_bank_keywords_for_linked_card(card),

                "difficulty": fin_corp_question_bank_difficulty(question_type, title, stored_body, answer, explanation, card=card),
                "issuer": issuer,
                "source_location": f"{page_title} · {question_number}. {title}",
                "section": FIN_CORP_SECTION,
                "points": fin_corp_question_bank_points(question_type),
                "expected_time_seconds": fin_corp_question_bank_expected_seconds(question_type),
                "answer_guide": fin_corp_question_bank_answer_guide(question_type),
                "session_mode": FIN_CORP_SESSION_MODE,
            })
    return entries




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
                                progress_db_path=progress_db_path,
                )
                if not category:
                    category = infer_question_bank_category(
                        "",
                        topic=topic,
                        prompt=" ".join(part for part in (page_title, *context_headings, prompt) if part).strip(),
                        body=body,
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
                    "keywords": [],
                    "difficulty": infer_question_bank_difficulty(question_type, prompt, body, "", ""),

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
                progress_db_path=progress_db_path,
        )
        if not category:
            category = infer_question_bank_category(
                "",
                topic=fallback_topic,
                prompt=f"{page_title} ### 1. {fallback_topic}",
                body=body,
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
            "keywords": [],
            "difficulty": infer_question_bank_difficulty(question_type, f"### 1. {fallback_topic}", body, "", ""),

            "issuer": "한국은행",
            "source_location": f"{page_title} · 1. {fallback_topic}" if fallback_topic else f"{page_title} · 1",
            "section": bok_question_bank_section_name(field_name, question_type),
            "points": bok_question_bank_points(question_type),
            "expected_time_seconds": bok_question_bank_expected_seconds(question_type),
            "answer_guide": bok_question_bank_answer_guide(question_type),
            "session_mode": "bok",
        })
    return entries





def question_attempt_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    raw_result = row["is_correct"]
    is_correct = None if raw_result is None else bool(int(raw_result))
    judgment = resolved_question_attempt_judgment(row["judgment"] if "judgment" in row.keys() else None, is_correct)
    return {
        "question_id": row["question_id"],
        "question_bank_id": row["question_bank_id"] if "question_bank_id" in row.keys() else "",
        "card_id": row["card_id"] or "",
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
    progress_db_path: Path | None = None,
    *,
    card_ids: list[str] | None = None,
    result: str = "all",
    limit: int = 200,
) -> dict[str, Any]:
    normalized_result = normalize_question_attempt_result(result)
    selected_ids = sorted(normalize_card_ids(card_ids) or [])
    safe_limit = max(1, min(int(limit or 200), 500))
    db_path = progress_db_for(progress_db_path)
    ensure_progress_db(db_path, must_exist=True)

    where_clauses: list[str] = []
    where_params: list[Any] = []
    if selected_ids:
        placeholders = ", ".join(["?"] * len(selected_ids))
        where_clauses.append(f"card_id IN ({placeholders})")
        where_params.extend(selected_ids)

    judgment_sql = resolved_question_attempt_judgment_sql()
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
        selected_card_count = len(selected_ids)
        if not selected_ids:
            count_row = conn.execute("SELECT COUNT(*) AS total_count FROM cards").fetchone()
            selected_card_count = int(count_row["total_count"] or 0) if count_row else 0
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

    attempt_card_ids = [str(row["card_id"] or "").strip() for row in attempt_rows if str(row["card_id"] or "").strip()]
    card_map = read_card_attempt_context(db_path, attempt_card_ids)
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
            "selected_card_count": selected_card_count,
            "returned": len(items),
        },
    }


def read_question_attempt_stats(progress_db_path: Path) -> dict[str, dict[str, Any]]:
    ensure_progress_db(progress_db_path, must_exist=True)
    stats: dict[str, dict[str, Any]] = {}
    with closing(connect_progress_db(progress_db_path)) as conn:
        for row in conn.execute(
            """
            SELECT
                card_id,
                question_attempt_count,
                question_correct_count,
                question_wrong_count,
                latest_wrong_note,
                latest_wrong_note_updated_at
            FROM question_attempt_card_summary
            """
        ).fetchall():
            stats[row["card_id"]] = _question_attempt_summary_dict(row)
    return stats




def read_question_bank_attempts(
    progress_db_path: Path | None = None,
    *,
    question_bank_ids: list[str] | None = None,
    result: str = "all",
    limit: int = 200,
) -> dict[str, Any]:
    normalized_result = normalize_question_attempt_result(result)
    selected_ids = normalize_question_bank_ids(question_bank_ids)
    safe_limit = max(1, min(int(limit or 200), 500))
    db_path = progress_db_for(progress_db_path)
    ensure_progress_db(db_path)

    where_clauses = ["TRIM(COALESCE(question_attempts.question_bank_id, '')) <> ''"]
    where_params: list[Any] = []
    if selected_ids:
        placeholders = ", ".join(["?"] * len(selected_ids))
        where_clauses.append(f"question_attempts.question_bank_id IN ({placeholders})")
        where_params.extend(selected_ids)

    judgment_sql = resolved_question_attempt_judgment_sql(
        judgment_column="question_attempts.judgment",
        is_correct_column="question_attempts.is_correct",
    )
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
                SUM(CASE WHEN {judgment_sql} = 'pending' THEN 1 ELSE 0 END) AS pending_count,
                SUM(CASE WHEN TRIM(COALESCE(question_attempts.wrong_note, '')) <> '' THEN 1 ELSE 0 END) AS note_count
            FROM question_attempts
            {base_where}
            """,
            tuple(where_params),
        ).fetchone()
        attempt_rows = conn.execute(
            f"""
            SELECT question_attempts.question_id, question_attempts.question_bank_id, question_attempts.card_id,
                   question_attempts.question_type, question_attempts.prompt, question_attempts.body,
                   question_attempts.user_answer, question_attempts.selected_choice_index,
                   question_attempts.is_correct, question_attempts.judgment, question_attempts.wrong_note,
                   question_attempts.session_id, question_attempts.session_title, question_attempts.session_mode,
                   question_attempts.section, question_attempts.points, question_attempts.expected_time_seconds,
                   question_attempts.answer_guide, question_attempts.question_order,
                   question_attempts.question_elapsed_seconds, question_attempts.session_elapsed_seconds,
                   question_attempts.time_limit_seconds, question_attempts.question_started_at,
                   question_attempts.answered_at, question_attempts.created_at, question_attempts.updated_at,
                   question_bank.answer AS bank_answer, question_bank.explanation AS bank_explanation,
                   question_bank.topic AS bank_topic, question_bank.field_name AS bank_field_name,
                   question_bank.category AS bank_category, question_bank.issuer AS bank_issuer,
                   question_bank.source_location AS bank_source_location,
                   question_bank.section AS bank_section,
                   question_bank.keywords_json AS bank_keywords_json
            FROM question_attempts
            LEFT JOIN question_bank ON question_bank.id = question_attempts.question_bank_id
            {list_where}
            ORDER BY question_attempts.updated_at DESC, question_attempts.created_at DESC, question_attempts.question_id DESC
            LIMIT ?
            """,
            tuple(list_params + [safe_limit]),
        ).fetchall()

    attempt_card_ids = [str(row["card_id"] or "").strip() for row in attempt_rows if str(row["card_id"] or "").strip()]
    card_map = read_card_attempt_context(db_path, attempt_card_ids)
    items: list[dict[str, Any]] = []
    for row in attempt_rows:
        item = question_attempt_row_to_dict(row) or {}
        card = card_map.get(item.get("card_id", ""), {})
        item["answer"] = row["bank_answer"] or ""
        item["explanation"] = row["bank_explanation"] or ""
        item["topic"] = row["bank_topic"] or ""
        item["field_name"] = row["bank_field_name"] or ""
        item["category"] = card.get("category") or row["bank_category"] or ""
        item["issuer"] = row["bank_issuer"] or ""
        item["source_location"] = row["bank_source_location"] or ""
        item["section"] = item.get("section") or row["bank_section"] or ""
        item["keywords"] = question_bank_json_list(row["bank_keywords_json"] if "bank_keywords_json" in row.keys() else [])
        item["term"] = card.get("term") or card.get("english") or item.get("card_id") or ""
        item["english"] = card.get("english") or ""
        item["card_url"] = flashcard_card_url(item.get("card_id") or "") if item.get("card_id") else ""
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
            "note_count": int(summary_row["note_count"] or 0) if summary_row else 0,
            "selected_question_bank_count": len(selected_ids),
            "returned": len(items),
        },
    }


def save_question_attempt(payload: QuestionAttemptRequest, progress_db_path: Path | None = None) -> dict[str, Any]:
    card_id = normalize_question_bank_text(payload.card_id, limit=255)
    question_bank_id = normalize_question_bank_text(payload.question_bank_id, limit=255)
    if not card_id and not question_bank_id:
        raise ValueError("card_id or question_bank_id is required")
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
    db_path = progress_db_for(progress_db_path)
    ensure_progress_db(db_path)
    now = utc_now_iso()
    answered_at = str(payload.answered_at or now)[:64]
    question_started_at = str(payload.question_started_at or "")[:64]
    session_id = str(payload.session_id or "")[:255]
    session_title = str(payload.session_title or "")[:255]
    session_mode = str(payload.session_mode or "practice")[:32] or "practice"
    section = str(payload.section or "")[:64]
    answer_guide = str(payload.answer_guide or "")[:255]
    with closing(connect_progress_db(db_path)) as conn:
        if question_bank_id:
            linked = conn.execute("SELECT id, card_id FROM question_bank WHERE id = ?", (question_bank_id,)).fetchone()
            if linked is None:
                raise ValueError(f"Unknown question_bank_id: {question_bank_id}")
            linked_card_id = normalize_question_bank_text(linked["card_id"] if "card_id" in linked.keys() else "", limit=255)
            if linked_card_id:
                if card_id and card_id != linked_card_id:
                    raise ValueError(f"question_bank_id {question_bank_id} is linked to card_id {linked_card_id}, not {card_id}")
                card_id = linked_card_id
        if card_id:
            _ensure_card_exists(card_id, db_path)
            conn.execute(
                """
                INSERT INTO card_progress (card_id, known_status, last_reviewed, review_count, bookmarked, memo, memo_updated_at, updated_at)
                VALUES (?, '', '', 0, 0, '', '', ?)
                ON CONFLICT(card_id) DO NOTHING
                """,
                (card_id, now),
            )

        existing = conn.execute(
            "SELECT created_at, question_started_at, card_id FROM question_attempts WHERE question_id = ?",
            (question_id,),
        ).fetchone()
        existing_card_id = normalize_question_bank_text(existing["card_id"] if existing else "", limit=255)
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
                card_id or None,
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
        _refresh_question_attempt_card_summary_cache(conn, [existing_card_id, card_id])
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

    refreshed_card = read_card(db_path, card_id) if card_id else None
    return {
        "attempt": question_attempt_row_to_dict(saved),
        "card": refreshed_card,
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
    return "local"


def wiki_github_archive_enabled() -> bool:
    return bool(WIKI_GITHUB_REPO and WIKI_GITHUB_TOKEN)


def wiki_archive_public_state() -> dict[str, Any]:
    return {
        "enabled": wiki_github_archive_enabled(),
        "repo": WIKI_GITHUB_REPO,
        "branch": WIKI_GITHUB_BRANCH,
        "path_prefix": WIKI_GITHUB_PATH_PREFIX,
    }


def wiki_github_repo_parts() -> tuple[str, str]:
    repo_slug = WIKI_GITHUB_REPO.strip().strip("/")
    if repo_slug.count("/") != 1:
        raise ValueError(f"Invalid GitHub repo slug: {WIKI_GITHUB_REPO}")
    owner, repo = repo_slug.split("/", 1)
    if not owner or not repo:
        raise ValueError(f"Invalid GitHub repo slug: {WIKI_GITHUB_REPO}")
    return owner, repo


def wiki_github_repo_api_base_url() -> str:
    owner, repo = wiki_github_repo_parts()
    return f"{WIKI_GITHUB_API_BASE}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"


def wiki_github_content_path(relative_path: str) -> str:
    normalized = PurePosixPath(str(relative_path or "").replace(os.sep, "/").lstrip("/"))
    if not normalized.parts or any(part in {"", ".", ".."} for part in normalized.parts):
        raise ValueError(f"Invalid GitHub wiki path: {relative_path}")
    repo_path = normalized.as_posix()
    if WIKI_GITHUB_PATH_PREFIX:
        repo_path = f"{WIKI_GITHUB_PATH_PREFIX}/{repo_path}"
    return repo_path


def wiki_github_contents_api_url(relative_path: str) -> str:
    content_path = wiki_github_content_path(relative_path)
    return f"{wiki_github_repo_api_base_url()}/contents/{quote(content_path, safe='/')}"


def wiki_github_git_ref_api_url(branch_name: str | None = None) -> str:
    branch = str(branch_name or WIKI_GITHUB_BRANCH).strip() or "main"
    return f"{wiki_github_repo_api_base_url()}/git/refs/{quote(f'heads/{branch}', safe='/')}"


def wiki_github_git_commit_api_url(commit_sha: str) -> str:
    return f"{wiki_github_repo_api_base_url()}/git/commits/{quote(str(commit_sha or '').strip(), safe='')}"


def wiki_github_git_tree_api_url(tree_sha: str) -> str:
    return f"{wiki_github_repo_api_base_url()}/git/trees/{quote(str(tree_sha or '').strip(), safe='')}"


def wiki_github_git_blobs_api_url() -> str:
    return f"{wiki_github_repo_api_base_url()}/git/blobs"


def wiki_github_git_commits_api_url() -> str:
    return f"{wiki_github_repo_api_base_url()}/git/commits"


def wiki_github_api_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    allow_missing: bool = False,
) -> dict[str, Any] | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "cs-flashcards/wiki-archive",
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
        if allow_missing and exc.code == 404:
            return None
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


def is_wiki_archive_relative_path(relative_path: str) -> bool:
    normalized = PurePosixPath(str(relative_path or "").replace(os.sep, "/").lstrip("/"))
    if not normalized.parts or any(part in {"", ".", ".."} for part in normalized.parts):
        return False
    if any(part.startswith(".") for part in normalized.parts):
        return False
    relative = normalized.as_posix()
    if relative in {WIKI_BOOK_README_NAME, WIKI_TOC_NAME}:
        return True
    return normalized.parts[0] in {"pages", "assets"}


def wiki_archive_relative_path_from_repo_path(repo_path: str) -> str | None:
    normalized = PurePosixPath(str(repo_path or "").replace(os.sep, "/").lstrip("/"))
    if not normalized.parts or any(part in {"", ".", ".."} for part in normalized.parts):
        return None
    parts = normalized.parts
    if WIKI_GITHUB_PATH_PREFIX:
        prefix_parts = PurePosixPath(WIKI_GITHUB_PATH_PREFIX).parts
        if tuple(parts[: len(prefix_parts)]) != prefix_parts:
            return None
        parts = parts[len(prefix_parts):]
        if not parts:
            return None
    relative = PurePosixPath(*parts).as_posix()
    return relative if is_wiki_archive_relative_path(relative) else None


def collect_local_wiki_archive_snapshot(repo_dir: Path | None = None) -> dict[str, bytes]:
    repo = wiki_book_dir(repo_dir)
    snapshot: dict[str, bytes] = {}
    for target in sorted(repo.rglob("*")):
        if not target.is_file():
            continue
        relative = str(target.relative_to(repo)).replace(os.sep, "/")
        if not is_wiki_archive_relative_path(relative):
            continue
        snapshot[relative] = target.read_bytes()
    return snapshot


def git_blob_sha_for_content(content: bytes) -> str:
    payload = content if isinstance(content, bytes) else bytes(content)
    return hashlib.sha1(f"blob {len(payload)}\0".encode("utf-8") + payload).hexdigest()


def github_read_wiki_archive_head_state() -> tuple[str, str, dict[str, str]]:
    ref_payload = wiki_github_api_json("GET", wiki_github_git_ref_api_url()) or {}
    commit_sha = str(((ref_payload.get("object") or {}).get("sha") or "")).strip()
    if not commit_sha:
        raise RuntimeError(f"GitHub 브랜치 HEAD를 찾지 못했습니다: {WIKI_GITHUB_BRANCH}")
    commit_payload = wiki_github_api_json("GET", wiki_github_git_commit_api_url(commit_sha)) or {}
    tree_sha = str(((commit_payload.get("tree") or {}).get("sha") or "")).strip()
    if not tree_sha:
        raise RuntimeError(f"GitHub 커밋 트리를 찾지 못했습니다: {commit_sha}")
    tree_payload = wiki_github_api_json("GET", f"{wiki_github_git_tree_api_url(tree_sha)}?recursive=1") or {}
    remote_snapshot: dict[str, str] = {}
    for entry in tree_payload.get("tree") or []:
        if str(entry.get("type") or "") != "blob":
            continue
        relative = wiki_archive_relative_path_from_repo_path(str(entry.get("path") or ""))
        sha = str(entry.get("sha") or "").strip()
        if relative and sha:
            remote_snapshot[relative] = sha
    return commit_sha, tree_sha, remote_snapshot


def github_create_wiki_archive_blob(content: bytes) -> str:
    payload = wiki_github_api_json(
        "POST",
        wiki_github_git_blobs_api_url(),
        {
            "content": base64.b64encode(content).decode("ascii"),
            "encoding": "base64",
        },
    ) or {}
    sha = str(payload.get("sha") or "").strip()
    if not sha:
        raise RuntimeError("GitHub blob SHA를 찾지 못했습니다.")
    return sha


def github_create_wiki_archive_tree(base_tree_sha: str, entries: list[dict[str, Any]]) -> str:
    payload = wiki_github_api_json(
        "POST",
        f"{wiki_github_repo_api_base_url()}/git/trees",
        {
            "base_tree": base_tree_sha,
            "tree": entries,
        },
    ) or {}
    sha = str(payload.get("sha") or "").strip()
    if not sha:
        raise RuntimeError("GitHub 트리 SHA를 찾지 못했습니다.")
    return sha


def github_create_wiki_archive_commit(message: str, tree_sha: str, parent_commit_sha: str) -> str:
    payload = wiki_github_api_json(
        "POST",
        wiki_github_git_commits_api_url(),
        {
            "message": message,
            "tree": tree_sha,
            "parents": [parent_commit_sha],
        },
    ) or {}
    sha = str(payload.get("sha") or "").strip()
    if not sha:
        raise RuntimeError("GitHub 커밋 SHA를 찾지 못했습니다.")
    return sha


def github_update_wiki_archive_branch_head(commit_sha: str) -> dict[str, Any]:
    return wiki_github_api_json(
        "PATCH",
        wiki_github_git_ref_api_url(),
        {
            "sha": commit_sha,
            "force": False,
        },
    ) or {}


def wiki_github_archive_commit_message(source_path: str, *, changed_count: int, deleted_count: int) -> str:
    subject = normalized_card_text(source_path, limit=255) or "manual-wiki-archive"
    return (
        f"Archive wiki snapshot from cs-flashcards ({subject}) · "
        f"{changed_count} changed, {deleted_count} deleted · {utc_now_iso()}"
    )


def archive_wiki_snapshot_to_github(source_path: str = "", repo_dir: Path | None = None) -> dict[str, Any]:
    if not wiki_github_archive_enabled():
        raise RuntimeError("GitHub 보관 구성이 없어 실행할 수 없습니다. 서버 환경변수에 CS_FLASHCARDS_WIKI_GITHUB_REPO 와 CS_FLASHCARDS_WIKI_GITHUB_TOKEN 을 설정하세요.")
    local_snapshot = collect_local_wiki_archive_snapshot(repo_dir)
    head_commit_sha, base_tree_sha, remote_snapshot = github_read_wiki_archive_head_state()
    tree_entries: list[dict[str, Any]] = []
    created_paths: list[str] = []
    updated_paths: list[str] = []
    for relative_path, content in local_snapshot.items():
        local_sha = git_blob_sha_for_content(content)
        remote_sha = remote_snapshot.get(relative_path)
        if remote_sha == local_sha:
            continue
        blob_sha = github_create_wiki_archive_blob(content)
        tree_entries.append({
            "path": wiki_github_content_path(relative_path),
            "mode": "100644",
            "type": "blob",
            "sha": blob_sha,
        })
        if remote_sha:
            updated_paths.append(relative_path)
        else:
            created_paths.append(relative_path)
    deleted_paths = sorted(set(remote_snapshot) - set(local_snapshot))
    for relative_path in deleted_paths:
        tree_entries.append({
            "path": wiki_github_content_path(relative_path),
            "mode": "100644",
            "type": "blob",
            "sha": None,
        })
    committed = bool(tree_entries)
    commit_sha = ""
    commit_message = wiki_github_archive_commit_message(
        source_path,
        changed_count=len(created_paths) + len(updated_paths),
        deleted_count=len(deleted_paths),
    )
    if committed:
        tree_sha = github_create_wiki_archive_tree(base_tree_sha, tree_entries)
        commit_sha = github_create_wiki_archive_commit(commit_message, tree_sha, head_commit_sha)
        github_update_wiki_archive_branch_head(commit_sha)
    return {
        "enabled": True,
        "repo": WIKI_GITHUB_REPO,
        "branch": WIKI_GITHUB_BRANCH,
        "path_prefix": WIKI_GITHUB_PATH_PREFIX,
        "source_path": normalized_card_text(source_path, limit=4096),
        "committed": committed,
        "commit_sha": commit_sha,
        "commit_message": commit_message,
        "created_file_count": len(created_paths),
        "updated_file_count": len(updated_paths),
        "changed_file_count": len(created_paths) + len(updated_paths),
        "deleted_file_count": len(deleted_paths),
        "created_paths": created_paths[:20],
        "updated_paths": updated_paths[:20],
        "deleted_paths": deleted_paths[:20],
        "local_file_count": len(local_snapshot),
    }


def resolve_wiki_markdown_source(source_path: str, repo_dir: Path | None = None) -> tuple[Path, Path, str, str]:
    repo = wiki_book_dir(repo_dir)
    target = safe_wiki_path(repo, source_path)
    if not target or not target.exists() or not target.is_file():
        raise FileNotFoundError(f"Wiki file not found: {source_path}")
    if target.suffix.lower() != ".md":
        raise ValueError(f"Wiki updates support Markdown files only: {source_path}")
    source_relative = str(target.relative_to(repo)).replace(os.sep, "/")
    return repo, target, source_relative, target.read_text(encoding="utf-8")


def ensure_wiki_source_matches_previous_content(previous_content: str | None, local_content: str) -> None:
    if previous_content is not None and previous_content != local_content:
        raise RuntimeError("문서 원본이 다른 내용으로 바뀌어 저장을 중단했습니다. 문서를 새로고침한 뒤 다시 수정하세요.")


def update_wiki_checklist_item(
    source_path: str,
    line_number: int,
    checked: bool,
    previous_content: str | None = None,
    repo_dir: Path | None = None,
) -> dict[str, Any]:
    repo, target, source_relative, local_content = resolve_wiki_markdown_source(source_path, repo_dir)
    ensure_wiki_source_matches_previous_content(previous_content, local_content)
    updated_content, task_meta = set_markdown_task_state(local_content, line_number, checked)
    if updated_content != local_content:
        target.write_text(updated_content, encoding="utf-8")
    return {
        "source_path": source_relative,
        "line_number": line_number,
        "page_slug": wiki_slug_for_source(repo, target),
        "sync_target": "local",
        **task_meta,
    }


def update_wiki_page_source(
    source_path: str,
    content: str,
    previous_content: str | None = None,
    repo_dir: Path | None = None,
) -> dict[str, Any]:
    repo, target, source_relative, local_content = resolve_wiki_markdown_source(source_path, repo_dir)
    ensure_wiki_source_matches_previous_content(previous_content, local_content)
    changed = content != local_content
    if changed:
        target.write_text(content, encoding="utf-8")
    return {
        "source_path": source_relative,
        "page_slug": wiki_slug_for_source(repo, target),
        "sync_target": "local",
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



def normalized_wiki_image_format(value: str) -> str:
    normalized = str(value or "png").strip().lower() or "png"
    if normalized not in WIKI_IMAGE_FORMATS:
        raise ValueError("지원하지 않는 위키 이미지 포맷입니다. png, svg, gif 중에서 선택하세요.")
    return normalized



def wiki_markdown_image_format(href: str) -> str:
    clean = str(href or "").split("#", 1)[0].split("?", 1)[0].strip()
    suffix = PurePosixPath(urlparse(clean).path or clean).suffix.lower().lstrip(".")
    return suffix if suffix in WIKI_IMAGE_FORMATS else "png"



def render_wiki_image_prompt_template(template_text: str, page_title: str, image: dict[str, Any]) -> str:
    context = {
        "page_title": str(page_title or "").strip() or "문서",
        "section_title": str(image.get("section_title") or page_title or "").strip() or "문서",
        "alt": str(image.get("alt") or page_title or "").strip() or "문서",
        "caption": str(image.get("caption") or "").strip(),
        "source_note": str(image.get("source_note") or "").strip(),
        "context_excerpt": str(image.get("context_excerpt") or "").strip(),
    }
    context["focus_subject"] = str(
        context["caption"] or context["alt"] or context["section_title"] or context["page_title"]
    ).strip() or context["page_title"]

    def replace(match: re.Match[str]) -> str:
        return str(context.get(match.group(1).strip().lower(), "")).strip()

    return re.sub(r"\{\{\s*([a-z_]+)\s*\}\}", replace, str(template_text or ""), flags=re.IGNORECASE).strip()



def normalized_markdown_excerpt(lines: list[str], *, limit: int = 1200) -> str:
    parts: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('![') or stripped.startswith('> 그림:') or stripped.startswith('> 출처:'):
            continue
        stripped = re.sub(r'^#+\s*', '', stripped)
        stripped = re.sub(r'`([^`]*)`', r'\1', stripped)
        stripped = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', stripped)
        stripped = re.sub(r'\*\*([^*]+)\*\*', r'\1', stripped)
        stripped = re.sub(r'\*([^*]+)\*', r'\1', stripped)
        stripped = re.sub(r'\s+', ' ', stripped).strip()
        if stripped:
            parts.append(stripped)
    return normalized_card_text(' '.join(parts), limit=limit)



def wiki_image_context_excerpt(lines: list[str], line_number: int, *, window: int = 6) -> str:
    start = max(0, line_number - 1 - window)
    end = min(len(lines), line_number + 2 + window)
    excerpt_lines = [lines[index] for index in range(start, end) if index not in {line_number - 1, line_number, line_number + 1}]
    return normalized_markdown_excerpt(excerpt_lines, limit=1200)



def parse_wiki_markdown_images(markdown_text: str, repo_dir: Path, current_source: Path) -> list[dict[str, Any]]:
    lines = markdown_text.splitlines()
    section_by_line: dict[int, str] = {}
    current_section = extract_markdown_title(markdown_text, current_source.stem)
    for line_number, line in enumerate(lines, start=1):
        heading = WIKI_HEADING_RE.match(line.strip())
        if heading:
            current_section = heading.group(2).strip()
        section_by_line[line_number] = current_section
    images: list[dict[str, Any]] = []
    for image_index, match in enumerate(WIKI_MARKDOWN_IMAGE_RE.finditer(markdown_text)):
        href = match.group("href").strip()
        line_number = markdown_text.count("\n", 0, match.start()) + 1
        caption = ""
        source_note = ""
        if line_number < len(lines):
            next_line = lines[line_number].strip()
            if next_line.startswith("> 그림:"):
                caption = next_line.removeprefix("> 그림:").strip()
        if line_number + 1 < len(lines):
            source_line = lines[line_number + 1].strip()
            if source_line.startswith("> 출처:"):
                source_note = source_line.removeprefix("> 출처:").strip()
        images.append({
            "index": image_index,
            "line_number": line_number,
            "alt": match.group("alt").strip(),
            "source_href": href,
            "src": rewrite_markdown_href(repo_dir, current_source, href),
            "caption": caption,
            "source_note": source_note,
            "context_excerpt": wiki_image_context_excerpt(lines, line_number),
            "section_title": section_by_line.get(line_number, current_source.stem),
            "format": wiki_markdown_image_format(href),
        })
    return images



def wiki_generated_section_asset_prefix(source_relative: str, section_index: int) -> str:
    base_name = re.sub(r"[^A-Za-z0-9._-]+", "-", PurePosixPath(source_relative).stem).strip("-") or "wiki"
    token = hashlib.sha1(str(source_relative).encode("utf-8")).hexdigest()[:8]
    return (WIKI_GENERATED_ASSET_DIR / f"{base_name}-{token}-section-{section_index + 1:02d}").as_posix()



def wiki_generated_section_asset_relative_path(source_relative: str, section_index: int, image_format: str) -> str:
    normalized_format = normalized_wiki_image_format(image_format)
    return f"{wiki_generated_section_asset_prefix(source_relative, section_index)}.{normalized_format}"



def find_generated_wiki_section_image_href(lines: list[str], source_relative: str, section_index: int, start_line_number: int, end_line_number: int) -> str:
    prefix = wiki_generated_section_asset_prefix(source_relative, section_index)
    for index in range(max(0, start_line_number - 1), min(len(lines), end_line_number)):
        match = WIKI_MARKDOWN_IMAGE_RE.match(lines[index].strip())
        if not match:
            continue
        href = match.group("href").strip()
        if href.startswith(prefix):
            return href
    return ""



def parse_wiki_markdown_sections(markdown_text: str, repo_dir: Path, current_source: Path) -> list[dict[str, Any]]:
    lines = markdown_text.splitlines()
    source_relative = str(current_source.relative_to(repo_dir)).replace(os.sep, "/")
    headings: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        heading = WIKI_HEADING_RE.match(line.strip())
        if not heading:
            continue
        title = heading.group(2).strip()
        headings.append({
            "index": len(headings),
            "line_number": line_number,
            "level": len(heading.group(1)),
            "title": title,
            "heading_id": wiki_heading_id(title),
        })
    sections: list[dict[str, Any]] = []
    for offset, heading in enumerate(headings):
        end_line_number = len(lines)
        for candidate in headings[offset + 1 :]:
            if int(candidate["level"]) <= int(heading["level"]):
                end_line_number = int(candidate["line_number"]) - 1
                break
        content_start_line = int(heading["line_number"]) + 1
        content_lines = lines[content_start_line - 1 : end_line_number]
        generated_href = find_generated_wiki_section_image_href(
            lines,
            source_relative,
            int(heading["index"]),
            content_start_line,
            end_line_number,
        )
        sections.append({
            **heading,
            "section_title": heading["title"],
            "alt": heading["title"],
            "caption": "",
            "source_note": "",
            "context_excerpt": normalized_markdown_excerpt(content_lines, limit=4000),
            "generated_image_href": generated_href,
            "format": wiki_markdown_image_format(generated_href) if generated_href else "png",
        })
    return sections



def replace_nth_markdown_image_href(markdown_text: str, image_index: int, next_href: str) -> tuple[str, dict[str, Any]]:
    matches = list(WIKI_MARKDOWN_IMAGE_RE.finditer(markdown_text))
    if image_index < 0 or image_index >= len(matches):
        raise ValueError(f"위키 이미지 인덱스를 찾지 못했습니다: {image_index}")
    target = matches[image_index]
    updated = markdown_text[: target.start("href")] + next_href + markdown_text[target.end("href") :]
    return updated, {
        "index": image_index,
        "alt": target.group("alt").strip(),
        "previous_href": target.group("href").strip(),
        "next_href": next_href,
    }



def wiki_generated_image_asset_relative_path(source_relative: str, image_index: int, image_format: str) -> str:
    normalized_format = normalized_wiki_image_format(image_format)
    base_name = re.sub(r"[^A-Za-z0-9._-]+", "-", PurePosixPath(source_relative).stem).strip("-") or "wiki"
    token = hashlib.sha1(str(source_relative).encode("utf-8")).hexdigest()[:8]
    return (WIKI_GENERATED_ASSET_DIR / f"{base_name}-{token}-image-{image_index + 1:02d}.{normalized_format}").as_posix()



def upsert_wiki_section_image_markdown(
    markdown_text: str,
    source_relative: str,
    section: dict[str, Any],
    next_href: str,
) -> tuple[str, dict[str, Any]]:
    lines = markdown_text.splitlines()
    keep_trailing_newline = markdown_text.endswith("\n")
    section_index = int(section.get("index") or 0)
    title = str(section.get("title") or section.get("section_title") or "섹션").strip() or "섹션"
    heading_line_number = int(section.get("line_number") or 1)
    level = int(section.get("level") or 1)
    prefix = wiki_generated_section_asset_prefix(source_relative, section_index)
    end_line_number = len(lines)
    for line_number in range(heading_line_number + 1, len(lines) + 1):
        match = WIKI_HEADING_RE.match(lines[line_number - 1].strip())
        if match and len(match.group(1)) <= level:
            end_line_number = line_number - 1
            break
    image_line_index: int | None = None
    previous_href = ""
    for index in range(max(0, heading_line_number), min(len(lines), end_line_number)):
        match = WIKI_MARKDOWN_IMAGE_RE.match(lines[index].strip())
        if not match:
            continue
        href = match.group("href").strip()
        if href.startswith(prefix):
            image_line_index = index
            previous_href = href
            break
    alt = normalized_card_text(f"{title} AI 이미지", limit=400)
    next_line = f"![{alt}]({next_href})"
    inserted = image_line_index is None
    if image_line_index is None:
        insert_at = min(len(lines), heading_line_number)
        insertion = [next_line]
        if insert_at >= len(lines) or lines[insert_at].strip():
            insertion.append("")
        lines[insert_at:insert_at] = insertion
    else:
        lines[image_line_index] = next_line
    updated = "\n".join(lines)
    if keep_trailing_newline:
        updated += "\n"
    return updated, {
        "section_index": section_index,
        "title": title,
        "line_number": heading_line_number,
        "previous_href": previous_href,
        "next_href": next_href,
        "inserted": inserted,
    }



def wiki_image_focus_subject(page_title: str, image: dict[str, Any]) -> str:
    caption = normalized_card_text(image.get("caption", ""), limit=240)
    alt = normalized_card_text(image.get("alt", ""), limit=200)
    section_title = normalized_card_text(image.get("section_title", ""), limit=200)
    return caption or alt or section_title or page_title



def wiki_png_image_prompt(page_title: str, image: dict[str, Any]) -> str:
    focus_subject = wiki_image_focus_subject(page_title, image)
    section_title = normalized_card_text(image.get("section_title", ""), limit=200)
    alt = normalized_card_text(image.get("alt", ""), limit=400)
    caption = normalized_card_text(image.get("caption", ""), limit=800)
    source_note = normalized_card_text(image.get("source_note", ""), limit=500)
    context_excerpt = normalized_card_text(image.get("context_excerpt", ""), limit=1200)
    return (
        "Create a clean, minimal educational concept illustration for a Korean CS wiki page. "
        "No text, no letters, no labels, no UI, no watermark, no logo, no border, no collage. "
        "Use a simple single-scene composition with soft modern colors and high clarity. "
        f"Primary subject: {focus_subject}. "
        f"Page title: {page_title}. "
        f"Section: {section_title or page_title}. "
        f"Image alt: {alt or page_title}. "
        f"Caption: {caption}. "
        f"Source note: {source_note}. "
        f"Local content context: {context_excerpt}. "
        "Visualize the real mechanism or mental model described by the local content context so a learner can understand it at a glance. "
        "Prefer a neutral academic diagram-like illustration, but rendered as a polished image rather than literal text diagram."
    )



def wiki_gif_image_prompt(page_title: str, image: dict[str, Any]) -> str:
    focus_subject = wiki_image_focus_subject(page_title, image)
    section_title = normalized_card_text(image.get("section_title", ""), limit=200)
    alt = normalized_card_text(image.get("alt", ""), limit=400)
    caption = normalized_card_text(image.get("caption", ""), limit=800)
    source_note = normalized_card_text(image.get("source_note", ""), limit=500)
    context_excerpt = normalized_card_text(image.get("context_excerpt", ""), limit=1200)
    return (
        f"{focus_subject}을 설명하는 학습용 GIF를 만들어줘.\n\n"
        "요구사항:\n"
        "- 설명문보다 움직임만 보고 작동 원리가 직관적으로 이해되게 만들어.\n"
        "- 텍스트/자막은 최소화.\n"
        "- 한 번 보면 ‘아, 이렇게 동작하는구나’가 바로 와야 해.\n"
        "- 정적인 인포그래픽 말고 실제 looping GIF로 만들어.\n"
        "- 핵심 상태 변화가 분명히 보여야 해. (예: push/pop, enqueue/dequeue, 탐색 순서, split, swap, relax 등)\n"
        "- 모바일/위키 본문 폭에서도 식별 가능하게 만들어.\n"
        "- active 요소는 색상/강조로 분명히 보여줘.\n"
        "- 아래 문맥에 없는 임의의 메커니즘은 만들지 말고, 실제 설명된 단계/상태 변화만 시각화해.\n\n"
        "문맥:\n"
        f"- 문서 제목: {page_title}\n"
        f"- 섹션: {section_title or page_title}\n"
        f"- 그림 대체텍스트: {alt or page_title}\n"
        f"- 그림 설명: {caption}\n"
        f"- 인접 본문 요약: {context_excerpt}\n"
        f"- 출처 메모: {source_note}\n\n"
        "의도:\n"
        "- 시험/면접용 학습 자료라서 긴 설명보다 동작 구조를 한눈에 이해시키는 게 목적이야.\n"
        "- ‘설명’이 아니라 ‘상태 변화 시각화’에 집중해."
    )



def validate_generated_wiki_svg(svg_text: str) -> str:
    clean = str(svg_text or "").strip()
    if not clean:
        raise ValueError("AI SVG 본문이 비어 있습니다.")
    if len(clean) > 200_000:
        raise ValueError("AI SVG 본문이 너무 깁니다.")
    try:
        root = ET.fromstring(clean)
    except ET.ParseError as exc:
        raise ValueError("AI SVG 응답이 올바른 XML이 아닙니다.") from exc
    if root.tag.rsplit("}", 1)[-1].lower() != "svg":
        raise ValueError("AI SVG 응답의 루트가 svg가 아닙니다.")
    for element in root.iter():
        tag_name = element.tag.rsplit("}", 1)[-1].lower()
        if tag_name in {"script", "foreignobject", "iframe", "object", "embed"}:
            raise ValueError("AI SVG 응답에 허용되지 않는 요소가 포함되어 있습니다.")
        for attr_name, attr_value in element.attrib.items():
            local_name = attr_name.rsplit("}", 1)[-1].lower()
            value = str(attr_value or "").strip()
            if local_name == "href" and value and not value.startswith("#"):
                raise ValueError("AI SVG 응답에 외부 참조가 포함되어 있습니다.")
    return clean



def generate_wiki_svg_markup(page_title: str, image: dict[str, Any], *, prompt_override: str = "") -> str:
    section_title = normalized_card_text(image.get("section_title", ""), limit=200)
    alt = normalized_card_text(image.get("alt", ""), limit=400)
    caption = normalized_card_text(image.get("caption", ""), limit=800)
    source_note = normalized_card_text(image.get("source_note", ""), limit=500)
    context_excerpt = normalized_card_text(image.get("context_excerpt", ""), limit=1200)
    custom_prompt = normalized_card_text(prompt_override, limit=12000)
    parsed = request_codex_json_object(
        (
            "You design valid standalone SVG illustrations. Return only one JSON object with the key svg. "
            "The svg value must be a complete standalone SVG string sized for a square canvas. "
            "Use only safe SVG elements and attributes. Do not use script, foreignObject, iframe, external href, CSS imports, fonts, or text. "
            "When custom_prompt is provided, follow it as the highest-priority visual brief while still obeying all SVG safety constraints."
        ),
        {
            "page": {
                "title": page_title,
                "section_title": section_title,
            },
            "image": {
                "alt": alt,
                "caption": caption,
                "source_note": source_note,
                "context_excerpt": context_excerpt,
            },
            "custom_prompt": custom_prompt,
            "style": {
                "tone": "clean minimal educational concept illustration",
                "constraints": [
                    "no text",
                    "no letters",
                    "no labels",
                    "no UI",
                    "soft modern colors",
                    "simple academic diagram feel",
                ],
            },
        },
        parse_error_message="AI SVG 응답을 JSON으로 해석하지 못했습니다.",
    )
    return validate_generated_wiki_svg(str(parsed.get("svg") or ""))



WIKI_GIF_FONT_CANDIDATES = (
    STATIC_DIR / "fonts" / "NanumGothic-Regular.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJKkr-Regular.otf",
)
WIKI_GIF_NODE_ID_RE = re.compile(r"[^a-z0-9_-]+")
WIKI_GIF_CANVAS_SIZE = (960, 540)
WIKI_GIF_BASE_COLORS = ("#dbeafe", "#e0e7ff", "#dcfce7", "#fef3c7", "#ffe4e6", "#ede9fe")
WIKI_GIF_ACCENT_COLORS = ("#2563eb", "#7c3aed", "#16a34a", "#d97706", "#e11d48", "#0891b2")


def clamp_number(value: Any, lower: float, upper: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(lower, min(upper, number))



def normalized_gif_color(value: Any, fallback: str) -> str:
    candidate = str(value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", candidate):
        return candidate.lower()
    return fallback.lower()



def sanitize_wiki_gif_node_id(value: Any, fallback: str) -> str:
    candidate = WIKI_GIF_NODE_ID_RE.sub("-", str(value or "").strip().lower()).strip("-")
    return candidate[:32] or fallback



def wrap_wiki_gif_label(value: str, max_lines: int = 2, line_width: int = 9) -> list[str]:
    text = normalized_card_text(value, limit=max_lines * line_width * 2).replace("\n", " ").strip()
    if not text:
        return [""]
    words = [chunk for chunk in text.split(" ") if chunk]
    if not words:
        words = [text]
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) <= line_width:
            current = f"{current} {word}"
            continue
        if current:
            lines.append(current)
            current = ""
            if len(lines) >= max_lines:
                break
        if len(word) <= line_width:
            current = word
            continue
        start = 0
        while start < len(word) and len(lines) < max_lines:
            piece = word[start:start + line_width]
            start += line_width
            if len(piece) == line_width or start >= len(word):
                lines.append(piece)
            else:
                current = piece
        if len(lines) >= max_lines:
            current = ""
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if not lines:
        lines = [text[:line_width]]
    return [line[:line_width] for line in lines[:max_lines]]



def load_wiki_gif_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    _, _, image_font_module = _pil_modules()
    for candidate in WIKI_GIF_FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return image_font_module.truetype(candidate, size=size)
            except OSError:
                continue
    return image_font_module.load_default()



def fallback_wiki_gif_plan(page_title: str, image: dict[str, Any]) -> dict[str, Any]:
    focus_subject = normalized_card_text(wiki_image_focus_subject(page_title, image), limit=20)
    seed_text = "\n".join(
        part for part in (
            image.get("section_title"),
            image.get("alt"),
            image.get("caption"),
            image.get("context_excerpt"),
        )
        if str(part or "").strip()
    )
    steps: list[str] = []
    seen: set[str] = set()
    for chunk in re.split(r"[\n.!?。,:;]+|->|=>|→", seed_text):
        label = normalized_card_text(chunk, limit=20).replace("  ", " ").strip()
        if len(label) < 2 or label in seen:
            continue
        seen.add(label)
        steps.append(label)
        if len(steps) >= 4:
            break
    if focus_subject and focus_subject not in seen:
        steps.insert(0, focus_subject)
    while len(steps) < 3:
        steps.append(("핵심 단계", "상태 변화", "결과 확인")[len(steps)])
    steps = steps[:5]
    x_positions = [0.16, 0.38, 0.62, 0.84, 0.84]
    y_positions = [0.5, 0.5, 0.5, 0.5, 0.78]
    nodes = []
    for idx, label in enumerate(steps):
        nodes.append({
            "id": f"node-{idx + 1}",
            "label": label,
            "x": x_positions[idx],
            "y": y_positions[idx],
            "width": 0.2,
            "height": 0.15,
            "color": WIKI_GIF_BASE_COLORS[idx % len(WIKI_GIF_BASE_COLORS)],
            "accent": WIKI_GIF_ACCENT_COLORS[idx % len(WIKI_GIF_ACCENT_COLORS)],
        })
    edges = []
    for idx in range(len(nodes) - 1):
        edges.append({
            "id": f"edge-{idx + 1}",
            "from": nodes[idx]["id"],
            "to": nodes[idx + 1]["id"],
        })
    stages = []
    for idx, node in enumerate(nodes):
        stages.append({"active_nodes": [node["id"]], "active_edges": []})
        if idx < len(edges):
            stages.append({
                "active_nodes": [node["id"], nodes[idx + 1]["id"]],
                "active_edges": [edges[idx]["id"]],
            })
    return {"nodes": nodes, "edges": edges, "stages": stages}



def validate_wiki_gif_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise ValueError("GIF 계획은 객체여야 합니다.")
    raw_nodes = plan.get("nodes")
    if not isinstance(raw_nodes, list):
        raise ValueError("GIF 계획에 nodes 배열이 필요합니다.")
    nodes: list[dict[str, Any]] = []
    node_lookup: dict[str, dict[str, Any]] = {}
    default_positions = (
        (0.18, 0.28),
        (0.5, 0.28),
        (0.82, 0.28),
        (0.18, 0.68),
        (0.5, 0.68),
        (0.82, 0.68),
    )
    for idx, raw in enumerate(raw_nodes[:6]):
        if not isinstance(raw, dict):
            continue
        fallback_id = f"node-{idx + 1}"
        node_id = sanitize_wiki_gif_node_id(raw.get("id"), fallback_id)
        while node_id in node_lookup:
            node_id = f"{node_id}-{idx + 1}"[:32]
        default_x, default_y = default_positions[idx]
        color = normalized_gif_color(raw.get("color"), WIKI_GIF_BASE_COLORS[idx % len(WIKI_GIF_BASE_COLORS)])
        accent = normalized_gif_color(raw.get("accent"), WIKI_GIF_ACCENT_COLORS[idx % len(WIKI_GIF_ACCENT_COLORS)])
        node = {
            "id": node_id,
            "label": normalized_card_text(raw.get("label") or raw.get("title") or fallback_id, limit=24) or fallback_id,
            "x": clamp_number(raw.get("x"), 0.12, 0.88, default_x),
            "y": clamp_number(raw.get("y"), 0.16, 0.84, default_y),
            "width": clamp_number(raw.get("width"), 0.14, 0.26, 0.2),
            "height": clamp_number(raw.get("height"), 0.11, 0.2, 0.15),
            "color": color,
            "accent": accent,
        }
        nodes.append(node)
        node_lookup[node_id] = node
    if len(nodes) < 2:
        raise ValueError("GIF 계획에는 최소 두 개의 노드가 필요합니다.")
    raw_edges = plan.get("edges") if isinstance(plan.get("edges"), list) else []
    edges: list[dict[str, str]] = []
    edge_lookup: dict[str, dict[str, str]] = {}
    for idx, raw in enumerate(raw_edges[:12]):
        if not isinstance(raw, dict):
            continue
        from_id = sanitize_wiki_gif_node_id(raw.get("from"), "")
        to_id = sanitize_wiki_gif_node_id(raw.get("to"), "")
        if from_id not in node_lookup or to_id not in node_lookup or from_id == to_id:
            continue
        fallback_id = f"edge-{idx + 1}"
        edge_id = sanitize_wiki_gif_node_id(raw.get("id"), fallback_id)
        while edge_id in edge_lookup:
            edge_id = f"{edge_id}-{idx + 1}"[:32]
        edge = {"id": edge_id, "from": from_id, "to": to_id}
        edges.append(edge)
        edge_lookup[edge_id] = edge
    if not edges:
        for idx in range(len(nodes) - 1):
            edge = {"id": f"edge-{idx + 1}", "from": nodes[idx]["id"], "to": nodes[idx + 1]["id"]}
            edges.append(edge)
            edge_lookup[edge["id"]] = edge
    raw_stages = plan.get("stages") if isinstance(plan.get("stages"), list) else []
    stages: list[dict[str, Any]] = []
    for idx, raw in enumerate(raw_stages[:6]):
        if not isinstance(raw, dict):
            continue
        active_nodes = [sanitize_wiki_gif_node_id(item, "") for item in raw.get("active_nodes") or []]
        active_nodes = [item for item in active_nodes if item in node_lookup]
        active_edges = [sanitize_wiki_gif_node_id(item, "") for item in raw.get("active_edges") or []]
        active_edges = [item for item in active_edges if item in edge_lookup]
        if active_edges:
            for edge_id in active_edges:
                edge = edge_lookup[edge_id]
                if edge["from"] not in active_nodes:
                    active_nodes.append(edge["from"])
                if edge["to"] not in active_nodes:
                    active_nodes.append(edge["to"])
        if not active_nodes and not active_edges:
            continue
        stages.append({
            "id": f"stage-{idx + 1}",
            "active_nodes": active_nodes,
            "active_edges": active_edges,
        })
    if not stages:
        for idx, node in enumerate(nodes):
            stages.append({"id": f"stage-{len(stages) + 1}", "active_nodes": [node["id"]], "active_edges": []})
            if idx < len(edges):
                stages.append({
                    "id": f"stage-{len(stages) + 1}",
                    "active_nodes": [node["id"], nodes[idx + 1]["id"]],
                    "active_edges": [edges[idx]["id"]],
                })
        stages = stages[:6]
    return {"nodes": nodes, "edges": edges, "stages": stages}



def request_wiki_gif_plan(page_title: str, image: dict[str, Any], *, prompt_override: str = "") -> dict[str, Any]:
    prompt_text = normalized_card_text(prompt_override or wiki_gif_image_prompt(page_title, image), limit=20000)
    payload = {
        "page": {
            "title": page_title,
            "section_title": normalized_card_text(image.get("section_title", ""), limit=200),
        },
        "image": {
            "alt": normalized_card_text(image.get("alt", ""), limit=400),
            "caption": normalized_card_text(image.get("caption", ""), limit=800),
            "source_note": normalized_card_text(image.get("source_note", ""), limit=500),
            "context_excerpt": normalized_card_text(image.get("context_excerpt", ""), limit=1200),
        },
        "design_brief": prompt_text,
        "output_schema": {
            "nodes": [{"id": "input", "label": "입력", "x": 0.18, "y": 0.5, "width": 0.2, "height": 0.15, "color": "#dbeafe", "accent": "#2563eb"}],
            "edges": [{"id": "flow-1", "from": "input", "to": "process"}],
            "stages": [{"active_nodes": ["input"], "active_edges": []}, {"active_nodes": ["input", "process"], "active_edges": ["flow-1"]}],
        },
    }
    try:
        parsed = request_codex_json_object(
            (
                "You design motion-first educational GIF storyboards for Korean CS/IT wiki pages. "
                "Return only one JSON object with keys nodes, edges, stages. "
                "The result must describe real state transitions, not camera shake, zoom wobble, or decorative motion. "
                "Use 2-6 short-labeled nodes, 1-12 directed edges, and 2-6 stages. "
                "Each node needs id, label, normalized x and y coordinates, and may include width, height, color, accent. "
                "Each edge needs id, from, to. Each stage needs active_nodes and active_edges. "
                "Prefer a simple flow diagram that can animate tokens moving through the active edges. "
                "Keep labels short and grounded only in the provided page context and design brief."
            ),
            payload,
            parse_error_message="AI GIF 계획을 JSON으로 해석하지 못했습니다.",
        )
        return validate_wiki_gif_plan(parsed)
    except RuntimeError as exc:
        if "OPENAI_API_KEY" in str(exc):
            raise
    except ValueError:
        pass
    return validate_wiki_gif_plan(fallback_wiki_gif_plan(page_title, image))



def node_center(node: dict[str, Any]) -> tuple[float, float]:
    width, height = WIKI_GIF_CANVAS_SIZE
    return node["x"] * width, node["y"] * height



def node_anchor_point(node: dict[str, Any], target_x: float, target_y: float) -> tuple[float, float]:
    center_x, center_y = node_center(node)
    half_w = node["width"] * WIKI_GIF_CANVAS_SIZE[0] / 2
    half_h = node["height"] * WIKI_GIF_CANVAS_SIZE[1] / 2
    dx = target_x - center_x
    dy = target_y - center_y
    if abs(dx) * half_h >= abs(dy) * half_w:
        edge_x = center_x + (half_w if dx >= 0 else -half_w)
        scale = 0 if abs(dx) < 1e-6 else half_w / abs(dx)
        edge_y = center_y + dy * scale
    else:
        edge_y = center_y + (half_h if dy >= 0 else -half_h)
        scale = 0 if abs(dy) < 1e-6 else half_h / abs(dy)
        edge_x = center_x + dx * scale
    return edge_x, edge_y



def interpolate_color(start: str, end: str, amount: float) -> tuple[int, int, int, int]:
    amount = max(0.0, min(1.0, amount))
    start_rgb = tuple(int(start[index:index + 2], 16) for index in (1, 3, 5))
    end_rgb = tuple(int(end[index:index + 2], 16) for index in (1, 3, 5))
    return tuple(int(start_rgb[idx] + (end_rgb[idx] - start_rgb[idx]) * amount) for idx in range(3)) + (255,)



def draw_arrow(draw: ImageDraw.ImageDraw, start: tuple[float, float], end: tuple[float, float], *, fill: tuple[int, int, int, int], width: int) -> None:
    draw.line([start, end], fill=fill, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    head = max(10, width * 3)
    left = (
        end[0] - head * math.cos(angle - math.pi / 7),
        end[1] - head * math.sin(angle - math.pi / 7),
    )
    right = (
        end[0] - head * math.cos(angle + math.pi / 7),
        end[1] - head * math.sin(angle + math.pi / 7),
    )
    draw.polygon([end, left, right], fill=fill)



def draw_wrapped_centered_text(draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float], text: str, font: ImageFont.ImageFont, fill: tuple[int, int, int, int]) -> None:
    lines = wrap_wiki_gif_label(text)
    if not lines:
        return
    bboxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    line_heights = [bbox[3] - bbox[1] for bbox in bboxes]
    total_height = sum(line_heights) + max(0, len(lines) - 1) * 4
    top = box[1] + (box[3] - box[1] - total_height) / 2
    for line, bbox, line_height in zip(lines, bboxes, line_heights):
        width = bbox[2] - bbox[0]
        left = box[0] + (box[2] - box[0] - width) / 2
        draw.text((left, top), line, font=font, fill=fill)
        top += line_height + 4



def render_wiki_gif_plan(plan: dict[str, Any]) -> bytes:
    image_module, image_draw_module, _ = _pil_modules()
    validated = validate_wiki_gif_plan(plan)
    canvas_width, canvas_height = WIKI_GIF_CANVAS_SIZE
    bg_color = (248, 250, 252, 255)
    text_color = (15, 23, 42, 255)
    shadow_color = (15, 23, 42, 24)
    label_font = load_wiki_gif_font(22)
    nodes = validated["nodes"]
    node_lookup = {node["id"]: node for node in nodes}
    edges = validated["edges"]
    edge_lookup = {edge["id"]: edge for edge in edges}
    frames: list[Image.Image] = []
    stage_total = len(validated["stages"])
    for stage_index, stage in enumerate(validated["stages"]):
        edge_count = max(1, len(stage["active_edges"]))
        subframes = 4 if edge_count else 3
        for step in range(subframes):
            progress = 0.0 if subframes == 1 else step / (subframes - 1)
            pulse = 0.5 + 0.5 * math.sin(progress * math.pi)
            frame = image_module.new("RGBA", (canvas_width, canvas_height), bg_color)
            draw = image_draw_module.Draw(frame, "RGBA")
            for edge in edges:
                start_node = node_lookup[edge["from"]]
                end_node = node_lookup[edge["to"]]
                target_center = node_center(end_node)
                source_center = node_center(start_node)
                start = node_anchor_point(start_node, *target_center)
                end = node_anchor_point(end_node, *source_center)
                active = edge["id"] in stage["active_edges"]
                accent = normalized_gif_color(end_node.get("accent"), WIKI_GIF_ACCENT_COLORS[0])
                edge_fill = interpolate_color("#94a3b8", accent, 0.8 if active else 0.0)
                draw_arrow(draw, start, end, fill=edge_fill, width=5 if active else 3)
            for node in nodes:
                center_x, center_y = node_center(node)
                width = node["width"] * canvas_width
                height = node["height"] * canvas_height
                active = node["id"] in stage["active_nodes"]
                accent = normalized_gif_color(node["accent"], WIKI_GIF_ACCENT_COLORS[0])
                fill = normalized_gif_color(node["color"], WIKI_GIF_BASE_COLORS[0])
                outline_fill = interpolate_color(fill, accent, 0.68 if active else 0.25)
                box = [center_x - width / 2, center_y - height / 2, center_x + width / 2, center_y + height / 2]
                glow_pad = 8 + int(6 * pulse) if active else 6
                draw.rounded_rectangle(
                    [box[0] - glow_pad, box[1] - glow_pad, box[2] + glow_pad, box[3] + glow_pad],
                    radius=26,
                    fill=(outline_fill[0], outline_fill[1], outline_fill[2], 40 if active else 18),
                )
                draw.rounded_rectangle(
                    [box[0] + 4, box[1] + 6, box[2] + 4, box[3] + 6],
                    radius=22,
                    fill=shadow_color,
                )
                draw.rounded_rectangle(box, radius=22, fill=fill, outline=outline_fill, width=5 if active else 3)
                draw_wrapped_centered_text(draw, tuple(box), node["label"], label_font, text_color)
            for edge_id in stage["active_edges"]:
                edge = edge_lookup[edge_id]
                start_node = node_lookup[edge["from"]]
                end_node = node_lookup[edge["to"]]
                target_center = node_center(end_node)
                source_center = node_center(start_node)
                start = node_anchor_point(start_node, *target_center)
                end = node_anchor_point(end_node, *source_center)
                token_x = start[0] + (end[0] - start[0]) * progress
                token_y = start[1] + (end[1] - start[1]) * progress
                accent = normalized_gif_color(end_node.get("accent"), WIKI_GIF_ACCENT_COLORS[0])
                token_fill = interpolate_color("#ffffff", accent, 0.92)
                radius = 10 + int(3 * pulse)
                draw.ellipse([token_x - radius - 3, token_y - radius - 3, token_x + radius + 3, token_y + radius + 3], fill=(255, 255, 255, 120))
                draw.ellipse([token_x - radius, token_y - radius, token_x + radius, token_y + radius], fill=token_fill, outline=(255, 255, 255, 255), width=2)
            progress_y = canvas_height - 28
            dot_radius = 7
            total_width = stage_total * 24
            start_x = (canvas_width - total_width) / 2 + 12
            for idx in range(stage_total):
                cx = start_x + idx * 24
                active_dot = idx == stage_index
                dot_fill = (37, 99, 235, 255) if active_dot else (203, 213, 225, 255)
                radius = dot_radius + (2 if active_dot else 0)
                draw.ellipse([cx - radius, progress_y - radius, cx + radius, progress_y + radius], fill=dot_fill)
            frames.append(frame.convert("P", palette=image_module.Palette.ADAPTIVE))
    out = io.BytesIO()
    frames[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=120,
        loop=0,
        optimize=False,
        disposal=2,
    )
    return out.getvalue()



def normalize_wiki_gif_frame_image(image_bytes: bytes, size: tuple[int, int] = WIKI_GIF_CANVAS_SIZE) -> Image.Image:
    image_module, _, _ = _pil_modules()
    resampling = getattr(getattr(image_module, "Resampling", image_module), "LANCZOS", image_module.LANCZOS)
    with image_module.open(io.BytesIO(image_bytes)) as original:
        base = original.convert("RGBA")
    canvas = image_module.new("RGBA", size, (248, 250, 252, 255))
    scale = min(size[0] / max(1, base.width), size[1] / max(1, base.height))
    target = (max(1, int(base.width * scale)), max(1, int(base.height * scale)))
    resized = base.resize(target, resampling)
    left = (size[0] - target[0]) // 2
    top = (size[1] - target[1]) // 2
    canvas.paste(resized, (left, top), resized)
    return canvas



def build_wiki_gif_frame_prompt(
    page_title: str,
    image: dict[str, Any],
    plan: dict[str, Any],
    stage_index: int,
    stage: dict[str, Any],
    *,
    prompt_override: str = "",
) -> str:
    node_lookup = {node["id"]: node for node in plan["nodes"]}
    edge_lookup = {edge["id"]: edge for edge in plan["edges"]}
    active_nodes = [node_lookup[node_id]["label"] for node_id in stage.get("active_nodes", []) if node_id in node_lookup]
    active_edges = []
    for edge_id in stage.get("active_edges", []):
        edge = edge_lookup.get(edge_id)
        if not edge:
            continue
        start = node_lookup.get(edge["from"], {}).get("label", edge["from"])
        end = node_lookup.get(edge["to"], {}).get("label", edge["to"])
        active_edges.append(f"{start} -> {end}")
    design_brief = normalized_card_text(prompt_override or wiki_gif_image_prompt(page_title, image), limit=12000)
    context_excerpt = normalized_card_text(image.get("context_excerpt", ""), limit=1200)
    section_title = normalized_card_text(image.get("section_title", ""), limit=200) or page_title
    alt = normalized_card_text(image.get("alt", ""), limit=400) or page_title
    return (
        "Create exactly one still frame for a Korean educational animated GIF. "
        "This frame must look like part of the same GIF sequence as the neighboring frames. "
        "Keep the same camera, layout, palette, icon style, and object positions across frames. "
        "No text, no letters, no labels, no watermark, no UI chrome. "
        "Use clean academic diagram-like visuals with obvious state changes, highlighted active elements, and motion implied by token movement or progression. "
        "Do not return multiple panels or collage. Return one 16:9 frame only. "
        f"Page title: {page_title}. "
        f"Section: {section_title}. "
        f"Image subject: {alt}. "
        f"Sequence frame: {stage_index + 1}/{len(plan['stages'])}. "
        f"Active states in this frame: {', '.join(active_nodes) or 'none'}. "
        f"Active transitions in this frame: {', '.join(active_edges) or 'none'}. "
        f"Local content context: {context_excerpt}. "
        f"Overall design brief: {design_brief}."
    )



def build_wiki_gif_playback_indices(stage_count: int) -> list[int]:
    if stage_count <= 1:
        return [0, 0, 0]
    forward = list(range(stage_count))
    reverse = list(range(stage_count - 2, 0, -1)) if stage_count > 2 else []
    sequence = forward + reverse
    playback: list[int] = []
    for index in sequence:
        playback.extend([index, index])
    return playback



def gif_from_api_frame_bytes(frame_bytes_list: list[bytes], playback_indices: list[int]) -> bytes:
    image_module, _, _ = _pil_modules()
    normalized_frames = [normalize_wiki_gif_frame_image(frame_bytes) for frame_bytes in frame_bytes_list]
    rendered_frames = [normalized_frames[index].convert("P", palette=image_module.Palette.ADAPTIVE) for index in playback_indices]
    out = io.BytesIO()
    rendered_frames[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=rendered_frames[1:],
        duration=140,
        loop=0,
        optimize=False,
        disposal=2,
    )
    return out.getvalue()



def render_wiki_learning_gif(page_title: str, image: dict[str, Any], *, prompt_override: str = "") -> bytes:
    plan = request_wiki_gif_plan(page_title, image, prompt_override=prompt_override)
    frame_bytes_list: list[bytes] = []
    for stage_index, stage in enumerate(plan["stages"]):
        frame_prompt = build_wiki_gif_frame_prompt(
            page_title,
            image,
            plan,
            stage_index,
            stage,
            prompt_override=prompt_override,
        )
        frame_bytes_list.append(request_openai_generated_image_bytes(frame_prompt))
    return gif_from_api_frame_bytes(frame_bytes_list, build_wiki_gif_playback_indices(len(frame_bytes_list)))



def upsert_wiki_binary_asset(
    relative_path: str,
    content: bytes,
    *,
    message: str,
    repo_dir: Path | None = None,
) -> dict[str, Any]:
    repo = wiki_book_dir(repo_dir)
    target = safe_wiki_path(repo, relative_path)
    if not target:
        raise ValueError(f"잘못된 위키 자산 경로입니다: {relative_path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    previous = target.read_bytes() if target.exists() else None
    if previous != content:
        target.write_bytes(content)
    return {
        "sync_target": "local",
        "relative_path": str(relative_path).replace(os.sep, "/"),
        "url": wiki_raw_url(relative_path),
    }



def regenerate_wiki_image_asset(
    payload: WikiImageRegenerateRequest,
    repo_dir: Path | None = None,
) -> dict[str, Any]:
    repo, target, source_relative, local_content = resolve_wiki_markdown_source(payload.source_path, repo_dir)
    images = parse_wiki_markdown_images(local_content, repo, target)
    if payload.image_index >= len(images):
        raise ValueError(f"위키 이미지 인덱스를 찾지 못했습니다: {payload.image_index}")
    image = images[payload.image_index]
    image_format = normalized_wiki_image_format(payload.format)
    prompt_override = normalized_card_text(payload.prompt_override, limit=20000)
    page_title = extract_markdown_title(local_content, target.stem)
    if image_format == "svg":
        asset_bytes = generate_wiki_svg_markup(page_title, image, prompt_override=prompt_override).encode("utf-8")
    elif image_format == "gif":
        asset_bytes = render_wiki_learning_gif(page_title, image, prompt_override=prompt_override)
    else:
        asset_bytes = request_openai_generated_image_bytes(prompt_override or wiki_png_image_prompt(page_title, image))
    asset_relative_path = wiki_generated_image_asset_relative_path(source_relative, payload.image_index, image_format)
    asset_saved = upsert_wiki_binary_asset(
        asset_relative_path,
        asset_bytes,
        message=f"Regenerate wiki asset: {asset_relative_path}",
        repo_dir=repo,
    )
    updated_content, image_update = replace_nth_markdown_image_href(local_content, payload.image_index, asset_relative_path)
    changed = updated_content != local_content
    if changed:
        target.write_text(updated_content, encoding="utf-8")
    page_slug = wiki_slug_for_source(repo, target)
    return {
        "page": read_wiki_page(page_slug, repo),
        "updated": {
            "source_path": source_relative,
            "page_slug": page_slug,
            "sync_target": "local",
            "changed": changed,
            "format": image_format,
            "image_index": payload.image_index,
            "asset_relative_path": asset_saved["relative_path"],
            "asset_url": asset_saved["url"],
            "alt": image.get("alt") or "",
            "previous_href": image_update["previous_href"],
            "next_href": image_update["next_href"],
        },
    }



def execute_wiki_page_batch_generation(
    source_path: str,
    *,
    image_format: str,
    prompt_template: str,
    include_existing_images: bool,
    include_sections: bool,
    repo_dir: Path | None = None,
) -> dict[str, int]:
    processed_images = 0
    processed_sections = 0
    normalized_template = str(prompt_template or "").strip()
    if include_existing_images:
        while True:
            repo, target, _, current_content = resolve_wiki_markdown_source(source_path, repo_dir)
            images = parse_wiki_markdown_images(current_content, repo, target)
            if processed_images >= len(images):
                break
            page_title = extract_markdown_title(current_content, target.stem)
            image = images[processed_images]
            prompt_override = render_wiki_image_prompt_template(normalized_template, page_title, image) if normalized_template else ""
            regenerate_wiki_image_asset(
                WikiImageRegenerateRequest(
                    source_path=source_path,
                    image_index=processed_images,
                    format=image_format,
                    prompt_override=prompt_override,
                ),
                repo_dir,
            )
            processed_images += 1
    if include_sections:
        while True:
            repo, target, _, current_content = resolve_wiki_markdown_source(source_path, repo_dir)
            sections = parse_wiki_markdown_sections(current_content, repo, target)
            if processed_sections >= len(sections):
                break
            page_title = extract_markdown_title(current_content, target.stem)
            section = sections[processed_sections]
            prompt_override = render_wiki_image_prompt_template(normalized_template, page_title, section) if normalized_template else ""
            generate_wiki_section_image_asset(
                WikiSectionImageGenerateRequest(
                    source_path=source_path,
                    section_index=processed_sections,
                    format=image_format,
                    prompt_override=prompt_override,
                ),
                repo_dir,
            )
            processed_sections += 1
    return {"images": processed_images, "sections": processed_sections}



def normalize_wiki_ai_job_request(payload: WikiAiJobCreateRequest) -> dict[str, Any]:
    source_paths = []
    seen: set[str] = set()
    for value in payload.source_paths:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        source_paths.append(normalized)
    if not source_paths:
        raise ValueError("처리할 위키 문서를 하나 이상 선택하세요.")
    target = str(payload.target or "page_batch").strip().lower() or "page_batch"
    if target not in WIKI_AI_JOB_TARGET_VALUES:
        raise ValueError("지원하지 않는 위키 AI 작업 종류입니다.")
    if target == "single_image" and payload.image_index is None:
        raise ValueError("단일 이미지 작업에는 image_index가 필요합니다.")
    if target == "single_section" and payload.section_index is None:
        raise ValueError("단일 섹션 작업에는 section_index가 필요합니다.")
    if target != "page_batch" and len(source_paths) != 1:
        raise ValueError("단일 항목 작업은 문서 하나에만 요청할 수 있습니다.")
    include_existing_images = bool(payload.include_existing_images)
    include_sections = bool(payload.include_sections)
    if target == "page_batch" and not include_existing_images and not include_sections:
        raise ValueError("일괄 작업은 기존 이미지 또는 섹션 중 하나 이상을 포함해야 합니다.")
    return {
        "source_paths": source_paths,
        "format": normalized_wiki_image_format(payload.format),
        "prompt_template": str(payload.prompt_template or ""),
        "include_existing_images": include_existing_images,
        "include_sections": include_sections,
        "target": target,
        "image_index": payload.image_index,
        "section_index": payload.section_index,
    }



def wiki_ai_job_snapshot(job: dict[str, Any] | sqlite3.Row | None) -> dict[str, Any] | None:
    if not job:
        return None
    payload = dict(job)
    source_paths = payload.get("source_paths")
    if source_paths is None:
        try:
            source_paths = json.loads(payload.get("source_paths_json") or "[]")
        except json.JSONDecodeError:
            source_paths = []
    if not isinstance(source_paths, list):
        source_paths = []
    return {
        "job_id": payload["job_id"],
        "status": payload["status"],
        "target": payload["target"],
        "source_paths": [str(value or "") for value in source_paths],
        "format": payload.get("format") or "png",
        "prompt_template": payload.get("prompt_template") or "",
        "include_existing_images": bool(payload.get("include_existing_images")),
        "include_sections": bool(payload.get("include_sections")),
        "image_index": payload.get("image_index"),
        "section_index": payload.get("section_index"),
        "queued_targets": int(payload.get("queued_targets") or 0),
        "processed_targets": int(payload.get("processed_targets") or 0),
        "requested_at": payload.get("requested_at") or "",
        "started_at": payload.get("started_at") or "",
        "completed_at": payload.get("completed_at") or "",
        "message": payload.get("message") or "",
        "error": payload.get("error") or "",
    }



def create_wiki_ai_job(payload: WikiAiJobCreateRequest) -> dict[str, Any]:
    normalized = normalize_wiki_ai_job_request(payload)
    job_id = uuid4().hex
    if normalized["target"] == "single_image":
        queued_targets = 1
    elif normalized["target"] == "single_section":
        queued_targets = 1
    else:
        queued_targets = len(normalized["source_paths"])
    now = utc_now_iso()
    job = {
        **normalized,
        "job_id": job_id,
        "status": "queued",
        "queued_targets": queued_targets,
        "processed_targets": 0,
        "requested_at": now,
        "started_at": "",
        "completed_at": "",
        "message": "요청 대기 중",
        "error": "",
        "updated_at": now,
    }
    db_path = progress_db_for(PROGRESS_DB_PATH)
    ensure_progress_db(db_path, must_exist=True)
    with closing(connect_progress_db(db_path, must_exist=True)) as conn:
        conn.execute(
            """
            INSERT INTO wiki_ai_jobs (
                job_id, status, target, source_paths_json, format, prompt_template,
                include_existing_images, include_sections, image_index, section_index,
                queued_targets, processed_targets, requested_at, started_at, completed_at,
                message, error, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job["job_id"],
                job["status"],
                job["target"],
                json.dumps(job["source_paths"], ensure_ascii=False),
                job["format"],
                job["prompt_template"],
                int(job["include_existing_images"]),
                int(job["include_sections"]),
                job["image_index"],
                job["section_index"],
                job["queued_targets"],
                job["processed_targets"],
                job["requested_at"],
                job["started_at"],
                job["completed_at"],
                job["message"],
                job["error"],
                job["updated_at"],
            ),
        )
        conn.commit()
    WIKI_AI_JOB_EVENT.set()
    ensure_wiki_ai_worker_started()
    return wiki_ai_job_snapshot(job) or {}



def update_wiki_ai_job(job_id: str, **changes: Any) -> dict[str, Any] | None:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return None
    column_map = {
        "status": ("status", lambda value: str(value or "").strip()),
        "target": ("target", lambda value: str(value or "").strip()),
        "source_paths": ("source_paths_json", lambda value: json.dumps([str(item or "") for item in list(value or [])], ensure_ascii=False)),
        "format": ("format", lambda value: normalized_wiki_image_format(value)),
        "prompt_template": ("prompt_template", lambda value: str(value or "")),
        "include_existing_images": ("include_existing_images", lambda value: int(bool(value))),
        "include_sections": ("include_sections", lambda value: int(bool(value))),
        "image_index": ("image_index", lambda value: None if value is None else int(value)),
        "section_index": ("section_index", lambda value: None if value is None else int(value)),
        "queued_targets": ("queued_targets", lambda value: int(value or 0)),
        "processed_targets": ("processed_targets", lambda value: int(value or 0)),
        "requested_at": ("requested_at", lambda value: str(value or "")),
        "started_at": ("started_at", lambda value: str(value or "")),
        "completed_at": ("completed_at", lambda value: str(value or "")),
        "message": ("message", lambda value: str(value or "")),
        "error": ("error", lambda value: str(value or "")),
    }
    assignments: list[str] = []
    params: list[Any] = []
    for key, value in changes.items():
        if key not in column_map:
            continue
        column, serializer = column_map[key]
        assignments.append(f"{column} = ?")
        params.append(serializer(value))
    if not assignments:
        return get_wiki_ai_job(normalized_job_id)
    db_path = progress_db_for(PROGRESS_DB_PATH)
    try:
        ensure_progress_db(db_path, must_exist=True)
    except FileNotFoundError:
        return None
    params.append(utc_now_iso())
    params.append(normalized_job_id)
    with closing(connect_progress_db(db_path, must_exist=True)) as conn:
        conn.execute(
            f"UPDATE wiki_ai_jobs SET {', '.join(assignments)}, updated_at = ? WHERE job_id = ?",
            tuple(params),
        )
        row = conn.execute("SELECT * FROM wiki_ai_jobs WHERE job_id = ?", (normalized_job_id,)).fetchone()
        conn.commit()
    return wiki_ai_job_snapshot(row)



def recover_incomplete_wiki_ai_jobs() -> int:
    db_path = progress_db_for(PROGRESS_DB_PATH)
    try:
        ensure_progress_db(db_path, must_exist=True)
    except FileNotFoundError:
        return 0
    now = utc_now_iso()
    with closing(connect_progress_db(db_path, must_exist=True)) as conn:
        cursor = conn.execute(
            """
            UPDATE wiki_ai_jobs
            SET status = 'queued',
                started_at = '',
                completed_at = '',
                message = '요청 대기 중 (프로세스 재개)',
                updated_at = ?
            WHERE status = 'running'
            """,
            (now,),
        )
        conn.commit()
    return int(cursor.rowcount or 0)



def claim_next_wiki_ai_job() -> dict[str, Any] | None:
    db_path = progress_db_for(PROGRESS_DB_PATH)
    try:
        ensure_progress_db(db_path, must_exist=True)
    except FileNotFoundError:
        return None
    now = utc_now_iso()
    with closing(connect_progress_db(db_path, must_exist=True)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        next_row = conn.execute(
            """
            SELECT job_id
            FROM wiki_ai_jobs
            WHERE status = 'queued'
            ORDER BY requested_at ASC, job_id ASC
            LIMIT 1
            """
        ).fetchone()
        if not next_row:
            conn.commit()
            return None
        conn.execute(
            """
            UPDATE wiki_ai_jobs
            SET status = 'running',
                started_at = CASE WHEN TRIM(COALESCE(started_at, '')) = '' THEN ? ELSE started_at END,
                completed_at = '',
                message = 'AI 이미지 생성 중',
                error = '',
                updated_at = ?
            WHERE job_id = ?
            """,
            (now, now, next_row["job_id"]),
        )
        claimed = conn.execute("SELECT * FROM wiki_ai_jobs WHERE job_id = ?", (next_row["job_id"],)).fetchone()
        conn.commit()
    return wiki_ai_job_snapshot(claimed)



def run_wiki_ai_job(job_id: str, snapshot: dict[str, Any] | None = None) -> None:
    snapshot = snapshot or get_wiki_ai_job(job_id)
    if not snapshot:
        return
    try:
        if snapshot["target"] == "single_image":
            regenerate_wiki_image_asset(
                WikiImageRegenerateRequest(
                    source_path=snapshot["source_paths"][0],
                    image_index=int(snapshot["image_index"] or 0),
                    format=snapshot["format"],
                    prompt_override=snapshot["prompt_template"],
                )
            )
            update_wiki_ai_job(job_id, processed_targets=1, message="이미지 생성 완료")
        elif snapshot["target"] == "single_section":
            generate_wiki_section_image_asset(
                WikiSectionImageGenerateRequest(
                    source_path=snapshot["source_paths"][0],
                    section_index=int(snapshot["section_index"] or 0),
                    format=snapshot["format"],
                    prompt_override=snapshot["prompt_template"],
                )
            )
            update_wiki_ai_job(job_id, processed_targets=1, message="섹션 이미지 생성 완료")
        else:
            processed_targets = 0
            generated_images = 0
            generated_sections = 0
            for source_path in snapshot["source_paths"]:
                counts = execute_wiki_page_batch_generation(
                    source_path,
                    image_format=snapshot["format"],
                    prompt_template=snapshot["prompt_template"],
                    include_existing_images=bool(snapshot.get("include_existing_images")),
                    include_sections=bool(snapshot.get("include_sections")),
                )
                generated_images += int(counts.get("images") or 0)
                generated_sections += int(counts.get("sections") or 0)
                processed_targets += 1
                update_wiki_ai_job(
                    job_id,
                    processed_targets=processed_targets,
                    message=f"{processed_targets}/{len(snapshot['source_paths'])} 문서 처리 완료",
                )
            update_wiki_ai_job(job_id, message=f"이미지 {generated_images}개, 섹션 {generated_sections}개 생성 완료")
        update_wiki_ai_job(job_id, status="completed", completed_at=utc_now_iso())
    except Exception as exc:
        update_wiki_ai_job(job_id, status="failed", completed_at=utc_now_iso(), error=str(exc), message="AI 이미지 생성 실패")



def wiki_ai_worker_loop() -> None:
    while True:
        snapshot = claim_next_wiki_ai_job()
        if snapshot is None:
            WIKI_AI_JOB_EVENT.wait(timeout=1)
            WIKI_AI_JOB_EVENT.clear()
            continue
        run_wiki_ai_job(snapshot["job_id"], snapshot=snapshot)



def ensure_wiki_ai_worker_started() -> None:
    global WIKI_AI_WORKER_THREAD, WIKI_AI_WORKER_RECOVERY_DONE
    recovered_jobs = 0
    with WIKI_AI_JOB_LOCK:
        if not WIKI_AI_WORKER_RECOVERY_DONE:
            recovered_jobs = recover_incomplete_wiki_ai_jobs()
            WIKI_AI_WORKER_RECOVERY_DONE = True
        if WIKI_AI_WORKER_THREAD and WIKI_AI_WORKER_THREAD.is_alive():
            if recovered_jobs:
                WIKI_AI_JOB_EVENT.set()
            return
        WIKI_AI_WORKER_THREAD = threading.Thread(target=wiki_ai_worker_loop, name="wiki-ai-worker", daemon=True)
        WIKI_AI_WORKER_THREAD.start()
    if recovered_jobs:
        WIKI_AI_JOB_EVENT.set()



def get_wiki_ai_job(job_id: str) -> dict[str, Any] | None:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return None
    db_path = progress_db_for(PROGRESS_DB_PATH)
    try:
        ensure_progress_db(db_path, must_exist=True)
    except FileNotFoundError:
        return None
    with closing(connect_progress_db(db_path, must_exist=True)) as conn:
        row = conn.execute("SELECT * FROM wiki_ai_jobs WHERE job_id = ?", (normalized_job_id,)).fetchone()
    return wiki_ai_job_snapshot(row)



def generate_wiki_section_image_asset(
    payload: WikiSectionImageGenerateRequest,
    repo_dir: Path | None = None,
) -> dict[str, Any]:
    repo, target, source_relative, local_content = resolve_wiki_markdown_source(payload.source_path, repo_dir)
    sections = parse_wiki_markdown_sections(local_content, repo, target)
    if payload.section_index >= len(sections):
        raise ValueError(f"위키 섹션 인덱스를 찾지 못했습니다: {payload.section_index}")
    section = sections[payload.section_index]
    section_subject = {
        "section_title": section.get("section_title") or section.get("title") or target.stem,
        "alt": section.get("alt") or section.get("title") or target.stem,
        "caption": section.get("caption") or "",
        "source_note": section.get("source_note") or "",
        "context_excerpt": section.get("context_excerpt") or "",
    }
    image_format = normalized_wiki_image_format(payload.format)
    prompt_override = normalized_card_text(payload.prompt_override, limit=20000)
    page_title = extract_markdown_title(local_content, target.stem)
    if image_format == "svg":
        asset_bytes = generate_wiki_svg_markup(page_title, section_subject, prompt_override=prompt_override).encode("utf-8")
    elif image_format == "gif":
        asset_bytes = render_wiki_learning_gif(page_title, section_subject, prompt_override=prompt_override)
    else:
        asset_bytes = request_openai_generated_image_bytes(prompt_override or wiki_png_image_prompt(page_title, section_subject))
    asset_relative_path = wiki_generated_section_asset_relative_path(source_relative, payload.section_index, image_format)
    asset_saved = upsert_wiki_binary_asset(
        asset_relative_path,
        asset_bytes,
        message=f"Generate wiki section image: {asset_relative_path}",
        repo_dir=repo,
    )
    updated_content, section_update = upsert_wiki_section_image_markdown(local_content, source_relative, section, asset_relative_path)
    changed = updated_content != local_content
    if changed:
        target.write_text(updated_content, encoding="utf-8")
    page_slug = wiki_slug_for_source(repo, target)
    return {
        "page": read_wiki_page(page_slug, repo),
        "updated": {
            "source_path": source_relative,
            "page_slug": page_slug,
            "sync_target": "local",
            "changed": changed,
            "format": image_format,
            "section_index": payload.section_index,
            "heading_id": section.get("heading_id") or "",
            "title": section.get("title") or "",
            "asset_relative_path": asset_saved["relative_path"],
            "asset_url": asset_saved["url"],
            **section_update,
        },
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
        "archive": wiki_archive_public_state(),
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
    progress_db_path: Path | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    rows, _ = read_cards(progress_db_path)
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
    if slug == RECRUITMENT_SCHEDULE_PAGE_SLUG:
        markdown_text = render_recruitment_schedule_wiki_page(markdown_text)
    source_relative = str(source_path.relative_to(repo)).replace(os.sep, "/")
    page_meta = index["pages"].get(slug, {})
    title = page_meta.get("title") or extract_markdown_title(markdown_text, source_path.stem)
    linked_cards = linked_cards_for_wiki_page(slug, title, source_relative, progress_db_path=PROGRESS_DB_PATH)
    last_modified_at, last_modified_label = wiki_last_modified_metadata(source_path)
    images = parse_wiki_markdown_images(markdown_text, repo, source_path)
    sections = parse_wiki_markdown_sections(markdown_text, repo, source_path)

    return {
        "slug": slug,
        "title": title,
        "source_path": source_relative,
        "raw_url": wiki_raw_url(source_relative),
        "url": wiki_page_url(slug),
        "breadcrumbs": index["breadcrumbs"].get(slug, [{"title": title, "slug": slug, "url": wiki_page_url(slug)}]),
        "html": render_markdown_page(markdown_text, repo, source_path),
        "images": images,
        "sections": sections,
        "last_modified_at": last_modified_at,
        "last_modified_label": last_modified_label,
        "primary_card": linked_cards[0] if linked_cards else None,
        "linked_cards": linked_cards,
        "archive": index.get("archive") or wiki_archive_public_state(),
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/question-bank")
def question_bank_shell() -> FileResponse:
    return FileResponse(STATIC_DIR / "question-bank.html")


@app.get(RECRUITMENT_CALENDAR_PATH)
def recruitment_calendar_shell() -> FileResponse:
    return FileResponse(STATIC_DIR / "calendar.html")


@app.get(RECRUITMENT_CALENDAR_API_PATH)
def api_recruitment_calendar(request: Request) -> dict[str, Any]:
    return build_recruitment_calendar_payload(base_url=str(request.base_url).rstrip("/"))


@app.get(RECRUITMENT_CALENDAR_ICS_PATH)
def api_recruitment_calendar_ics(request: Request) -> Response:
    return Response(
        build_recruitment_calendar_ics(base_url=str(request.base_url).rstrip("/")),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="recruitment-calendar-2026.ics"'},
    )
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



@app.post("/api/wiki/image-ai/regenerate")
def api_wiki_image_regenerate(payload: WikiImageRegenerateRequest) -> dict[str, Any]:
    try:
        return regenerate_wiki_image_asset(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/wiki/section-image/generate")
def api_wiki_section_image_generate(payload: WikiSectionImageGenerateRequest) -> dict[str, Any]:
    try:
        return generate_wiki_section_image_asset(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/wiki/ai-jobs")
def api_wiki_ai_job_create(payload: WikiAiJobCreateRequest) -> dict[str, Any]:
    try:
        return create_wiki_ai_job(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/wiki/ai-jobs/{job_id}")
def api_wiki_ai_job_get(job_id: str) -> dict[str, Any]:
    job = get_wiki_ai_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Wiki AI job not found: {job_id}")
    return job


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

@app.post("/api/wiki/archive/github")
def api_wiki_archive_github(payload: WikiGithubArchiveRequest) -> dict[str, Any]:
    try:
        return {
            "archive": archive_wiki_snapshot_to_github(payload.source_path or ""),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
        updated = update_wiki_checklist_item(payload.source_path, payload.line_number, payload.checked, payload.previous_content)
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
        rows, _ = read_cards(progress_db_path=PROGRESS_DB_PATH)


    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"cards": rows, "summary": summarize(rows)}


@app.post("/api/cards/{card_id}/mark")
def api_mark(card_id: str, payload: MarkRequest) -> dict[str, Any]:
    try:
        card = mark_card(card_id, payload.known_status, progress_db_path=PROGRESS_DB_PATH)
        summary = read_card_mutation_summary(PROGRESS_DB_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"card": card, "summary": summary}


@app.post("/api/cards/{card_id}/bookmark")
def api_bookmark(card_id: str, payload: BookmarkRequest) -> dict[str, Any]:
    try:
        card = set_bookmark(card_id, payload.bookmarked, progress_db_path=PROGRESS_DB_PATH)
        summary = read_card_mutation_summary(PROGRESS_DB_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"card": card, "summary": summary}


@app.post("/api/cards/{card_id}/memo")
def api_memo(card_id: str, payload: MemoRequest) -> dict[str, Any]:
    try:
        card = save_memo(card_id, payload.memo, progress_db_path=PROGRESS_DB_PATH)
        summary = read_card_mutation_summary(PROGRESS_DB_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"card": card, "summary": summary}
@app.post("/api/cards/{card_id}/ai-rewrite/preview")
def api_card_ai_rewrite_preview(card_id: str, payload: CardAiRewriteRequest) -> dict[str, Any]:
    try:
        current = read_card(PROGRESS_DB_PATH, card_id)
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
        card, backup_path = update_card_ai_content(card_id, payload, backup_dir=BACKUP_DIR, progress_db_path=PROGRESS_DB_PATH)
        summary = read_card_mutation_summary(PROGRESS_DB_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "card": card,
        "summary": summary,
        "backup_path": str(backup_path) if backup_path else "",
    }


@app.post("/api/cards/{card_id}/concept-media")
def api_card_concept_media(card_id: str, payload: CardConceptMediaRequest) -> dict[str, Any]:
    try:
        card, backup_path = update_card_concept_media(card_id, payload, backup_dir=BACKUP_DIR, progress_db_path=PROGRESS_DB_PATH)
        summary = read_card_mutation_summary(PROGRESS_DB_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "card": card,
        "summary": summary,
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
        current = read_card(PROGRESS_DB_PATH, card_id)
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
            backup_dir=BACKUP_DIR,
            progress_db_path=PROGRESS_DB_PATH,
            image_dir=AI_IMAGE_DIR,
            preview_dir=AI_IMAGE_PREVIEW_DIR,
        )
        summary = read_card_mutation_summary(PROGRESS_DB_PATH)
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
        "summary": summary,
        "backup_path": str(backup_path) if backup_path else "",
        "image_url": image_url,
    }



@app.post("/api/questions/generate")
def api_generate_questions(payload: QuestionGenerateRequest) -> dict[str, Any]:
    try:
        rows, _ = read_cards(progress_db_path=PROGRESS_DB_PATH)
        generated = generate_questions(
            rows,
            card_ids=payload.card_ids,
            types=payload.types,
            count=payload.count,
            seed=payload.seed,
        )
        return attach_generated_question_bank_ids(generated, rows, progress_db_path=PROGRESS_DB_PATH)


    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/question-bank")
def api_question_bank_upsert(payload: QuestionBankUpsertRequest) -> dict[str, Any]:
    try:
        return upsert_question_bank_entries(payload.questions, progress_db_path=PROGRESS_DB_PATH)


    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Card not found: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.put("/api/question-bank/{question_bank_id}")
def api_question_bank_update(question_bank_id: str, payload: QuestionBankEntryRequest) -> dict[str, Any]:
    try:
        item = update_question_bank_entry(question_bank_id, payload, progress_db_path=PROGRESS_DB_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Question bank item not found: {question_bank_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "question_bank_id": question_bank_id,
        "item": item,
    }


@app.post("/api/question-bank/{question_bank_id}/ai-refine-answer")
def api_question_bank_ai_refine_answer(question_bank_id: str, payload: QuestionBankAiRefineRequest) -> dict[str, Any]:
    try:
        item = update_question_bank_ai_content(question_bank_id, payload, progress_db_path=PROGRESS_DB_PATH)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Question bank item not found: {question_bank_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "question_bank_id": question_bank_id,
        "model": CODEX_MODEL,
        "item": item,
    }
@app.get("/api/question-bank")
def api_question_bank(request: Request) -> dict[str, Any]:
    raw_limit = str(request.query_params.get("limit") or "200").strip()
    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid limit: {raw_limit}") from exc
    try:
        return read_question_bank_entries(
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
            attempt_status=request.query_params.get("attempt_status", request.query_params.get("status", "")),
            include_missing_cards=str(request.query_params.get("include_missing_cards", "")).strip().lower() in {"1", "true", "yes", "y", "on"},
            limit=limit,
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/question-bank/attempts")
def api_question_bank_attempts(request: Request) -> dict[str, Any]:
    raw_limit = str(request.query_params.get("limit") or "200").strip()
    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid limit: {raw_limit}") from exc
    try:
        return read_question_bank_attempts(
            progress_db_path=PROGRESS_DB_PATH,
            question_bank_ids=request.query_params.getlist("question_bank_id"),
            result=request.query_params.get("result", "all"),
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/question-bank/attempts/query")
def api_question_bank_attempts_query(payload: QuestionBankAttemptQueryRequest) -> dict[str, Any]:
    try:
        return read_question_bank_attempts(
            progress_db_path=PROGRESS_DB_PATH,
            question_bank_ids=payload.question_bank_ids,
            result=payload.result,
            limit=payload.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.post("/api/questions/attempt")
def api_question_attempt(payload: QuestionAttemptRequest) -> dict[str, Any]:
    try:
        return save_question_attempt(payload, progress_db_path=PROGRESS_DB_PATH)

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
def health(response: Response) -> dict[str, Any]:
    try:
        resolved_wiki_book_dir = wiki_book_dir()
        wiki_book_exists = True
    except FileNotFoundError:
        resolved_wiki_book_dir = WIKI_BOOK_DIR
        wiki_book_exists = False
    db_summary = progress_db_runtime_summary(PROGRESS_DB_PATH)
    ok = bool(db_summary["ok"])
    if not ok:
        response.status_code = 503
    return {
        "ok": ok,
        "content_db_path": str(PROGRESS_DB_PATH),
        "content_db_exists": db_summary["exists"],
        "content_card_count": db_summary["content_card_count"],
        "question_bank_count": db_summary["question_bank_count"],
        "question_attempt_count": db_summary["question_attempt_count"],
        "progress_db_path": str(PROGRESS_DB_PATH),
        "progress_db_exists": db_summary["exists"],
        "progress_db_readable": db_summary["readable"],
        "progress_db_error": db_summary["error"],
        "wiki_book_dir": str(resolved_wiki_book_dir),
        "wiki_book_exists": wiki_book_exists,
        "wiki_book_configured_dir": str(WIKI_BOOK_DIR),
        "wiki_checklist_sync_target": wiki_checklist_sync_target(),
        "wiki_archive_enabled": wiki_github_archive_enabled(),
        "wiki_github_repo": WIKI_GITHUB_REPO,
        "wiki_github_branch": WIKI_GITHUB_BRANCH,
        "wiki_github_path_prefix": WIKI_GITHUB_PATH_PREFIX,
        "wiki_ai_job_queue_count": db_summary["wiki_ai_job_queue_count"],
        "wiki_ai_job_running_count": db_summary["wiki_ai_job_running_count"],
        "wiki_ai_job_failed_count": db_summary["wiki_ai_job_failed_count"],
        "ai_rewrite_enabled": bool(OPENAI_API_KEY),
        "codex_model": CODEX_MODEL,
        "ai_image_model": IMAGE_MODEL,
    }
