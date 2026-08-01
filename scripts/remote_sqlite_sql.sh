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
SQL_TEXT=""

usage() {
  cat <<'EOF'
Usage: ./scripts/remote_sqlite_sql.sh [--sql 'UPDATE ...;']
       ./scripts/remote_sqlite_sql.sh <<'SQL'
       UPDATE ...;
       SQL

Executes SQL directly against the live remote SQLite DB.
Fixed remote DB path only; file upload and DB replacement are prohibited.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sql)
      SQL_TEXT="$2"
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

if [[ -z "$SQL_TEXT" ]]; then
  if [[ -t 0 ]]; then
    echo "실행할 SQL이 없습니다. --sql 또는 stdin으로 SQL을 제공하세요." >&2
    exit 1
  fi
  SQL_TEXT="$(cat)"
fi

if [[ -z "$(printf '%s' "$SQL_TEXT" | tr -d '[:space:]')" ]]; then
  echo "빈 SQL은 실행할 수 없습니다." >&2
  exit 1
fi

chmod 400 "$SSH_KEY" 2>/dev/null || true
SSH=(ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new "$REMOTE_USER@$REMOTE_HOST")

env SQL_TEXT="$SQL_TEXT" "${SSH[@]}" bash -s -- "$REMOTE_DB_PATH" <<'REMOTE'
set -euo pipefail
REMOTE_DB_PATH="$1"
if [[ ! -f "$REMOTE_DB_PATH" ]]; then
  echo "원격 SQLite 파일이 없습니다: $REMOTE_DB_PATH" >&2
  exit 1
fi
printf 'BEGIN IMMEDIATE;\n%s\nCOMMIT;\n' "$SQL_TEXT" | sqlite3 -bail "$REMOTE_DB_PATH"
REMOTE
