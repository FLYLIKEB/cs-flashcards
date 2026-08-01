#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

CHALOG_CONFIG="${CS_FLASHCARDS_REMOTE_CONFIG:-/Users/jwp/Developer/ChaLog/.ec2-config}"
LOCAL_DB="${CS_FLASHCARDS_LOCAL_DB:-$ROOT_DIR/state/progress.sqlite}"
REMOTE_HOST="${CS_FLASHCARDS_LIGHTSAIL_HOST:-}"
REMOTE_USER="${CS_FLASHCARDS_LIGHTSAIL_USER:-ubuntu}"
SSH_KEY="${CS_FLASHCARDS_LIGHTSAIL_KEY:-}"
REMOTE_DIR="${CS_FLASHCARDS_REMOTE_DIR:-/home/ubuntu/cs-flashcards}"
REMOTE_DB="${CS_FLASHCARDS_REMOTE_DB_PATH:-$REMOTE_DIR/state/progress.sqlite}"
LOCAL_TARGET=""
KEY_COLUMN=""

usage() {
  cat <<'EOF'
Usage: ./scripts/sync_remote_sqlite_rows.sh [--local-db PATH] [--remote-db PATH] [--key COLUMN] [--local-target PATH] <table> <row-id> [<row-id>...]

Examples:
  ./scripts/sync_remote_sqlite_rows.sh question_bank qb-011b1c688f53bb3974beb2e3
  ./scripts/sync_remote_sqlite_rows.sh cards CS-001 CS-002
  ./scripts/sync_remote_sqlite_rows.sh --local-target /tmp/remote.sqlite question_bank qb-011b1c688f53bb3974beb2e3
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local-db)
      LOCAL_DB="$2"
      shift 2
      ;;
    --remote-db)
      REMOTE_DB="$2"
      shift 2
      ;;
    --key)
      KEY_COLUMN="$2"
      shift 2
      ;;
    --local-target)
      LOCAL_TARGET="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      break
      ;;
  esac
done

if [[ $# -lt 2 ]]; then
  usage >&2
  exit 1
fi

TABLE="$1"
shift
IDS=("$@")

if [[ -z "$KEY_COLUMN" ]]; then
  case "$TABLE" in
    cards|card_progress)
      KEY_COLUMN="card_id"
      ;;
    question_bank)
      KEY_COLUMN="id"
      ;;
    question_attempts)
      KEY_COLUMN="question_id"
      ;;
    *)
      echo "키 컬럼을 추론할 수 없는 테이블입니다. --key COLUMN 을 함께 지정하세요: $TABLE" >&2
      exit 1
      ;;
  esac
fi

if [[ ! -f "$LOCAL_DB" ]]; then
  echo "로컬 SQLite 파일을 찾을 수 없습니다: $LOCAL_DB" >&2
  exit 1
fi

PAYLOAD_FILE="$(mktemp -t cs-flashcards-row-sync.XXXXXX.json)"
REMOTE_PAYLOAD="/tmp/$(basename "$PAYLOAD_FILE")"
cleanup() {
  rm -f "$PAYLOAD_FILE"
}
trap cleanup EXIT

python3 - <<'PY' "$LOCAL_DB" "$TABLE" "$KEY_COLUMN" "$PAYLOAD_FILE" "${IDS[@]}"
import json
import re
import sqlite3
import sys
from pathlib import Path

def valid_identifier(value: str) -> bool:
    return bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value))

db_path = Path(sys.argv[1])
table = sys.argv[2]
key_column = sys.argv[3]
payload_path = Path(sys.argv[4])
ids = []
seen = set()
for raw in sys.argv[5:]:
    if raw not in seen:
        ids.append(raw)
        seen.add(raw)
if not ids:
    raise SystemExit('동기화할 row id가 필요합니다.')
if not valid_identifier(table) or not valid_identifier(key_column):
    raise SystemExit('테이블명/키 컬럼명은 안전한 식별자여야 합니다.')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
columns = [row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()]
if not columns:
    raise SystemExit(f'테이블이 없습니다: {table}')
if key_column not in columns:
    raise SystemExit(f'키 컬럼이 없습니다: {table}.{key_column}')
qmarks = ','.join('?' for _ in ids)
rows = conn.execute(f'SELECT * FROM {table} WHERE {key_column} IN ({qmarks})', ids).fetchall()
row_map = {str(row[key_column]): {column: row[column] for column in columns} for row in rows}
missing = [row_id for row_id in ids if row_id not in row_map]
if missing:
    raise SystemExit('로컬 DB에 없는 row id: ' + ', '.join(missing))
payload = {
    'table': table,
    'key_column': key_column,
    'columns': columns,
    'ids': ids,
    'rows': [row_map[row_id] for row_id in ids],
}
payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'table': table, 'key_column': key_column, 'rows': len(ids), 'payload_path': str(payload_path)}, ensure_ascii=False))
conn.close()
PY

APPLY_PY=$(cat <<'PY'
import json
import re
import sqlite3
import sys
from pathlib import Path

def valid_identifier(value: str) -> bool:
    return bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value))

db_path = Path(sys.argv[1])
payload_path = Path(sys.argv[2])
payload = json.loads(payload_path.read_text(encoding='utf-8'))
table = payload['table']
key_column = payload['key_column']
columns = payload['columns']
ids = payload['ids']
rows = payload['rows']
if not valid_identifier(table) or not valid_identifier(key_column) or any(not valid_identifier(column) for column in columns):
    raise SystemExit('안전하지 않은 식별자가 포함되어 있습니다.')
conn = sqlite3.connect(db_path)
remote_columns = [row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()]
if not remote_columns:
    raise SystemExit(f'원격 테이블이 없습니다: {table}')
missing_columns = [column for column in columns if column not in remote_columns]
if missing_columns:
    raise SystemExit(f'원격 테이블에 없는 컬럼: {", ".join(missing_columns)}')
placeholders = ', '.join('?' for _ in columns)
assignments = [f'{column}=excluded.{column}' for column in columns if column != key_column]
if assignments:
    on_conflict = f'ON CONFLICT({key_column}) DO UPDATE SET ' + ', '.join(assignments)
else:
    on_conflict = f'ON CONFLICT({key_column}) DO NOTHING'
sql = f'INSERT INTO {table} ({", ".join(columns)}) VALUES ({placeholders}) {on_conflict}'
conn.executemany(sql, [[row.get(column) for column in columns] for row in rows])
conn.commit()
qmarks = ','.join('?' for _ in ids)
matched = conn.execute(f'SELECT COUNT(*) FROM {table} WHERE {key_column} IN ({qmarks})', ids).fetchone()[0]
conn.close()
print(json.dumps({'db_path': str(db_path), 'table': table, 'key_column': key_column, 'rows_upserted': len(rows), 'matched_after': matched, 'ids': ids}, ensure_ascii=False, indent=2))
PY
)

if [[ -n "$LOCAL_TARGET" ]]; then
  python3 - <<'PY' "$LOCAL_TARGET" "$PAYLOAD_FILE"
import json
import re
import sqlite3
import sys
from pathlib import Path

def valid_identifier(value: str) -> bool:
    return bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value))

db_path = Path(sys.argv[1])
payload_path = Path(sys.argv[2])
payload = json.loads(payload_path.read_text(encoding='utf-8'))
table = payload['table']
key_column = payload['key_column']
columns = payload['columns']
ids = payload['ids']
rows = payload['rows']
if not valid_identifier(table) or not valid_identifier(key_column) or any(not valid_identifier(column) for column in columns):
    raise SystemExit('안전하지 않은 식별자가 포함되어 있습니다.')
conn = sqlite3.connect(db_path)
remote_columns = [row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()]
if not remote_columns:
    raise SystemExit(f'대상 테이블이 없습니다: {table}')
missing_columns = [column for column in columns if column not in remote_columns]
if missing_columns:
    raise SystemExit(f'대상 테이블에 없는 컬럼: {", ".join(missing_columns)}')
placeholders = ', '.join('?' for _ in columns)
assignments = [f'{column}=excluded.{column}' for column in columns if column != key_column]
if assignments:
    on_conflict = f'ON CONFLICT({key_column}) DO UPDATE SET ' + ', '.join(assignments)
else:
    on_conflict = f'ON CONFLICT({key_column}) DO NOTHING'
sql = f'INSERT INTO {table} ({", ".join(columns)}) VALUES ({placeholders}) {on_conflict}'
conn.executemany(sql, [[row.get(column) for column in columns] for row in rows])
conn.commit()
qmarks = ','.join('?' for _ in ids)
matched = conn.execute(f'SELECT COUNT(*) FROM {table} WHERE {key_column} IN ({qmarks})', ids).fetchone()[0]
conn.close()
print(json.dumps({'db_path': str(db_path), 'table': table, 'key_column': key_column, 'rows_upserted': len(rows), 'matched_after': matched, 'ids': ids}, ensure_ascii=False, indent=2))
PY
  exit 0
fi

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

SCP=(scp -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new)
SSH=(ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new "$REMOTE_USER@$REMOTE_HOST")
"${SCP[@]}" "$PAYLOAD_FILE" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_PAYLOAD"
"${SSH[@]}" "set -euo pipefail
trap 'rm -f '\''$REMOTE_PAYLOAD'\''' EXIT
python3 - '$REMOTE_DB' '$REMOTE_PAYLOAD' <<'PY'
$APPLY_PY
PY"
