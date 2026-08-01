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


mkdir -p "$(dirname "$OUTPUT_PATH")" "$BACKUP_DIR"
if [[ -f "$OUTPUT_PATH" ]]; then
  cp "$OUTPUT_PATH" "$BACKUP_DIR/progress-before-pull-$(date +%Y%m%dT%H%M%S).sqlite"
fi

TMP_FILE="$(mktemp -t cs-flashcards-remote-db.XXXXXX.sqlite)"
cleanup() {
  rm -f "$TMP_FILE"
}
trap cleanup EXIT

SCP=(scp -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new)
"${SCP[@]}" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DB_PATH" "$TMP_FILE"
mv "$TMP_FILE" "$OUTPUT_PATH"

python3 - <<'PY' "$OUTPUT_PATH"
import json
import os
import sqlite3
import sys
path = sys.argv[1]
conn = sqlite3.connect(path)
rows = {}
for table in ['cards', 'card_progress', 'question_bank', 'question_attempts']:
    try:
        rows[table] = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    except Exception as exc:
        rows[table] = str(exc)
conn.close()
print(json.dumps({'output_path': path, 'size': os.path.getsize(path), 'rows': rows}, ensure_ascii=False, indent=2))
PY
