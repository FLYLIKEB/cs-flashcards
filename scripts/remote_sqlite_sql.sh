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

validate_sql_text() {
  python3 - "$1" <<'PY'
import re
import sys

TRANSACTION_KEYWORDS = {'BEGIN', 'COMMIT', 'ROLLBACK', 'SAVEPOINT', 'RELEASE', 'END'}
BOUNDARY_KEYWORDS = {'ATTACH', 'DETACH', 'PRAGMA'}


def sanitize_sql(sql: str) -> str:
    result: list[str] = []
    index = 0
    state = 'normal'
    while index < len(sql):
        char = sql[index]
        nxt = sql[index + 1] if index + 1 < len(sql) else ''
        if state == 'normal':
            if char == "'":
                state = 'single'
                result.append(' ')
            elif char == '"':
                state = 'double'
                result.append(' ')
            elif char == '-' and nxt == '-':
                state = 'line_comment'
                result.extend((' ', ' '))
                index += 1
            elif char == '/' and nxt == '*':
                state = 'block_comment'
                result.extend((' ', ' '))
                index += 1
            else:
                result.append(char)
        elif state == 'single':
            if char == "'":
                if nxt == "'":
                    result.extend((' ', ' '))
                    index += 1
                else:
                    state = 'normal'
                    result.append(' ')
            else:
                result.append('\n' if char == '\n' else ' ')
        elif state == 'double':
            if char == '"':
                if nxt == '"':
                    result.extend((' ', ' '))
                    index += 1
                else:
                    state = 'normal'
                    result.append(' ')
            else:
                result.append('\n' if char == '\n' else ' ')
        elif state == 'line_comment':
            if char == '\n':
                state = 'normal'
                result.append('\n')
            else:
                result.append(' ')
        else:
            if char == '*' and nxt == '/':
                state = 'normal'
                result.extend((' ', ' '))
                index += 1
            else:
                result.append('\n' if char == '\n' else ' ')
        index += 1
    return ''.join(result)


sql = sys.argv[1]
sanitized = sanitize_sql(sql)
for line in sanitized.splitlines():
    if re.match(r'^[ \t]*\.', line):
        print('sqlite dot-command는 허용되지 않습니다.', file=sys.stderr)
        sys.exit(1)
for statement in sanitized.split(';'):
    tokens = re.findall(r'[A-Za-z_]+|\.', statement)
    if not tokens:
        continue
    first = tokens[0].upper()
    second = tokens[1].upper() if len(tokens) > 1 and tokens[1] != '.' else None
    if first in TRANSACTION_KEYWORDS or (first == 'EXPLAIN' and second in TRANSACTION_KEYWORDS):
        print('트랜잭션 제어 SQL은 허용되지 않습니다.', file=sys.stderr)
        sys.exit(1)
    if first in BOUNDARY_KEYWORDS or (first == 'EXPLAIN' and second in BOUNDARY_KEYWORDS):
        print('SQLite 실행 경계를 변경하는 SQL은 허용되지 않습니다.', file=sys.stderr)
        sys.exit(1)
PY
}

validate_sql_text "$SQL_TEXT"

chmod 400 "$SSH_KEY" 2>/dev/null || true
SSH=(ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new "$REMOTE_USER@$REMOTE_HOST")

env SQL_TEXT="$SQL_TEXT" "${SSH[@]}" bash -s -- "$REMOTE_DB_PATH" <<'REMOTE'
set -euo pipefail
REMOTE_DB_PATH="$1"
if [[ ! -f "$REMOTE_DB_PATH" ]]; then
  echo "원격 SQLite 파일이 없습니다: $REMOTE_DB_PATH" >&2
  exit 1
fi
python3 - <<'PY' "$SQL_TEXT"
import re
import sys

TRANSACTION_KEYWORDS = {'BEGIN', 'COMMIT', 'ROLLBACK', 'SAVEPOINT', 'RELEASE', 'END'}
BOUNDARY_KEYWORDS = {'ATTACH', 'DETACH', 'PRAGMA'}


def sanitize_sql(sql: str) -> str:
    result: list[str] = []
    index = 0
    state = 'normal'
    while index < len(sql):
        char = sql[index]
        nxt = sql[index + 1] if index + 1 < len(sql) else ''
        if state == 'normal':
            if char == "'":
                state = 'single'
                result.append(' ')
            elif char == '"':
                state = 'double'
                result.append(' ')
            elif char == '-' and nxt == '-':
                state = 'line_comment'
                result.extend((' ', ' '))
                index += 1
            elif char == '/' and nxt == '*':
                state = 'block_comment'
                result.extend((' ', ' '))
                index += 1
            else:
                result.append(char)
        elif state == 'single':
            if char == "'":
                if nxt == "'":
                    result.extend((' ', ' '))
                    index += 1
                else:
                    state = 'normal'
                    result.append(' ')
            else:
                result.append('\n' if char == '\n' else ' ')
        elif state == 'double':
            if char == '"':
                if nxt == '"':
                    result.extend((' ', ' '))
                    index += 1
                else:
                    state = 'normal'
                    result.append(' ')
            else:
                result.append('\n' if char == '\n' else ' ')
        elif state == 'line_comment':
            if char == '\n':
                state = 'normal'
                result.append('\n')
            else:
                result.append(' ')
        else:
            if char == '*' and nxt == '/':
                state = 'normal'
                result.extend((' ', ' '))
                index += 1
            else:
                result.append('\n' if char == '\n' else ' ')
        index += 1
    return ''.join(result)


sql = sys.argv[1]
sanitized = sanitize_sql(sql)
for line in sanitized.splitlines():
    if re.match(r'^[ \t]*\.', line):
        print('sqlite dot-command는 허용되지 않습니다.', file=sys.stderr)
        sys.exit(1)
for statement in sanitized.split(';'):
    tokens = re.findall(r'[A-Za-z_]+|\.', statement)
    if not tokens:
        continue
    first = tokens[0].upper()
    second = tokens[1].upper() if len(tokens) > 1 and tokens[1] != '.' else None
    if first in TRANSACTION_KEYWORDS or (first == 'EXPLAIN' and second in TRANSACTION_KEYWORDS):
        print('트랜잭션 제어 SQL은 허용되지 않습니다.', file=sys.stderr)
        sys.exit(1)
    if first in BOUNDARY_KEYWORDS or (first == 'EXPLAIN' and second in BOUNDARY_KEYWORDS):
        print('SQLite 실행 경계를 변경하는 SQL은 허용되지 않습니다.', file=sys.stderr)
        sys.exit(1)
PY
python3 - <<'PY' "$REMOTE_DB_PATH" "$SQL_TEXT"
import sqlite3
import sys


db_path, sql_text = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(db_path, isolation_level=None)
try:
    conn.executescript(f"BEGIN IMMEDIATE;\n{sql_text}\nCOMMIT;\n")
except Exception:
    if conn.in_transaction:
        conn.rollback()
    raise
finally:
    conn.close()
PY
REMOTE
