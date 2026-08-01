#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

CHALOG_CONFIG="${CS_FLASHCARDS_REMOTE_CONFIG:-/Users/jwp/Developer/ChaLog/.ec2-config}"
REMOTE_HOST="${CS_FLASHCARDS_LIGHTSAIL_HOST:-}"
REMOTE_USER="${CS_FLASHCARDS_LIGHTSAIL_USER:-ubuntu}"
SSH_KEY="${CS_FLASHCARDS_LIGHTSAIL_KEY:-}"
REMOTE_DIR="${CS_FLASHCARDS_REMOTE_DIR:-/home/ubuntu/cs-flashcards}"
REMOTE_DB_PATH="$REMOTE_DIR/state/progress.sqlite"
OUTPUT_PATH="${CS_FLASHCARDS_LOCAL_DB:-$ROOT_DIR/state/progress.sqlite}"
BACKUP_DIR="${CS_FLASHCARDS_LOCAL_DB_BACKUP_DIR:-$ROOT_DIR/backups/manual-db-pull}"

usage() {
  cat <<'EOF'
Usage: ./scripts/pull_remote_sqlite.sh [--output PATH]

Copies the live remote SQLite DB to the local workspace before intentional DB edits.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      OUTPUT_PATH="$2"
      shift 2
      ;;
    --remote-db)
      echo "원격 DB 경로 변경은 금지됩니다. 고정 경로만 사용합니다: $REMOTE_DB_PATH" >&2
      exit 1
      ;;

    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -f "$CHALOG_CONFIG" ]]; then
  # shellcheck disable=SC1090
  source "$CHALOG_CONFIG"
  REMOTE_HOST="${REMOTE_HOST:-${EC2_HOST:-}}"
  REMOTE_USER="${CS_FLASHCARDS_LIGHTSAIL_USER:-${EC2_USER:-ubuntu}}"
  SSH_KEY="${SSH_KEY:-${SSH_KEY_PATH:-${LIGHTSAIL_KEY_PATH:-}}}"
fi

if [[ ! -f "${SSH_KEY:-}" && -f "/Users/jwp/Developer/ChaLog/LightsailDefaultKey-ap-northeast-2.pem" ]]; then
  SSH_KEY="/Users/jwp/Developer/ChaLog/LightsailDefaultKey-ap-northeast-2.pem"
fi

if [[ -z "${REMOTE_HOST:-}" || ! -f "${SSH_KEY:-}" ]]; then
  echo "Lightsail 접속 정보가 없습니다. CS_FLASHCARDS_LIGHTSAIL_HOST / CS_FLASHCARDS_LIGHTSAIL_KEY를 지정하세요." >&2
  exit 1
fi
if [[ -n "${CS_FLASHCARDS_REMOTE_DB_PATH:-}" && "$CS_FLASHCARDS_REMOTE_DB_PATH" != "$REMOTE_DB_PATH" ]]; then
  echo "원격 DB 경로 변경은 금지됩니다: $CS_FLASHCARDS_REMOTE_DB_PATH" >&2
  exit 1
fi

TMP_FILE="$(mktemp -t cs-flashcards-remote-db.XXXXXX.sqlite)"
cleanup() {
  rm -f "$TMP_FILE"
}
trap cleanup EXIT

validate_downloaded_sqlite() {
  python3 - "$1" <<'PY'
import sqlite3
import sys

path = sys.argv[1]
required_schema = {
    'cards': {
        'card_id', 'term', 'english', 'category', 'alphabet_index', 'korean_initial',
        'definition', 'detailed_explanation', 'related_concepts', 'source_files',
        'exam_note', 'bok_appeared', 'importance', 'difficulty', 'concept_image_url',
        'concept_image_alt', 'concept_media_type', 'concept_media_payload', 'sort_order', 'updated_at',
    },
    'card_progress': {
        'card_id', 'known_status', 'last_reviewed', 'review_count', 'bookmarked', 'memo', 'memo_updated_at', 'updated_at',
    },
    'question_bank': {
        'id', 'fingerprint', 'card_id', 'question_type', 'prompt', 'body', 'answer', 'explanation',
        'rubric_json', 'choices_json', 'answer_index', 'topic', 'field_name', 'category',
        'keywords_json', 'missing_card_keywords_json', 'difficulty', 'issuer', 'source_location',
        'section', 'points', 'expected_time_seconds', 'answer_guide', 'session_mode', 'created_at', 'updated_at',
    },
    'question_attempts': {
        'question_id', 'question_bank_id', 'card_id', 'question_type', 'prompt', 'body', 'user_answer',
        'selected_choice_index', 'is_correct', 'judgment', 'wrong_note', 'session_id', 'session_title',
        'session_mode', 'section', 'points', 'expected_time_seconds', 'answer_guide', 'question_order',
        'question_elapsed_seconds', 'session_elapsed_seconds', 'time_limit_seconds', 'question_started_at',
        'answered_at', 'created_at', 'updated_at',
    },
    'wiki_ai_jobs': {
        'job_id', 'status', 'target', 'source_paths_json', 'format', 'prompt_template',
        'include_existing_images', 'include_sections', 'image_index', 'section_index', 'queued_targets',
        'processed_targets', 'requested_at', 'started_at', 'completed_at', 'message', 'error', 'updated_at',
    },
}

try:
    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        conn.execute('PRAGMA schema_version').fetchone()
        table_names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if row[0] and not str(row[0]).startswith('sqlite_')
        }
        missing_tables = sorted(required_schema.keys() - table_names)
        if missing_tables:
            raise RuntimeError(f"앱 스키마 테이블이 누락되었습니다: {', '.join(missing_tables)}")
        missing_columns = []
        for table, required_columns in required_schema.items():
            column_names = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            for column in sorted(required_columns - column_names):
                missing_columns.append(f'{table}.{column}')
        if missing_columns:
            raise RuntimeError(f"앱 스키마 컬럼이 누락되었습니다: {', '.join(missing_columns)}")
        card_count = conn.execute('SELECT COUNT(*) FROM cards').fetchone()[0]
        if card_count <= 0:
            raise RuntimeError('cards 테이블이 비어 있습니다.')
    finally:
        conn.close()
except Exception as exc:
    print(f'다운로드한 SQLite 검증에 실패했습니다: {exc}', file=sys.stderr)
    sys.exit(1)
PY
}

SCP=(scp -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new)
"${SCP[@]}" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DB_PATH" "$TMP_FILE"
if ! validate_downloaded_sqlite "$TMP_FILE"; then
  echo "기존 로컬 SQLite는 유지됩니다: $OUTPUT_PATH" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_PATH")" "$BACKUP_DIR"
if [[ -f "$OUTPUT_PATH" ]]; then
  cp "$OUTPUT_PATH" "$BACKUP_DIR/progress-before-pull-$(date +%Y%m%dT%H%M%S).sqlite"
fi

mv "$TMP_FILE" "$OUTPUT_PATH"

python3 - "$OUTPUT_PATH" <<'PY'
import json
import os
import sqlite3
import sys
path = sys.argv[1]
conn = sqlite3.connect(path)
rows = {}
for table in ['cards', 'card_progress', 'question_bank', 'question_attempts', 'wiki_ai_jobs']:
    try:
        rows[table] = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    except Exception as exc:
        rows[table] = str(exc)
conn.close()
print(json.dumps({'output_path': path, 'size': os.path.getsize(path), 'rows': rows}, ensure_ascii=False, indent=2))
PY
