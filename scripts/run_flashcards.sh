#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

HOST="${CS_FLASHCARDS_HOST:-127.0.0.1}"
PORT="${CS_FLASHCARDS_PORT:-8000}"
URL="http://${HOST}:${PORT}"
VENV_DIR="${CS_FLASHCARDS_VENV:-.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
STATE_DIR="$ROOT_DIR/.omx"
LOG_DIR="$STATE_DIR/logs"
LOG_FILE="$LOG_DIR/cs_flashcards.log"
PID_FILE="$STATE_DIR/cs_flashcards.pid"

mkdir -p "$LOG_DIR"

is_running() {
  "$PYTHON_BIN" - <<PY >/dev/null 2>&1
from urllib.request import urlopen
url = "${URL}/api/health"
try:
    with urlopen(url, timeout=1.5) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
}

open_browser() {
  if [[ "${CS_FLASHCARDS_NO_OPEN:-0}" == "1" ]]; then
    return 0
  fi
  if command -v open >/dev/null 2>&1; then
    open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 &
  else
    printf '브라우저를 자동으로 열 수 없습니다. 아래 주소로 접속하세요:\n%s\n' "$URL"
  fi
}

if is_running; then
  printf 'CS 플래시카드가 이미 실행 중입니다: %s\n' "$URL"
  open_browser
  exit 0
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  printf '가상환경 생성 중: %s\n' "$VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

printf '의존성 확인/설치 중...\n'
"$VENV_DIR/bin/python" -m pip install -q --upgrade pip
"$VENV_DIR/bin/python" -m pip install -q -r requirements.txt

printf 'CS 플래시카드 서버 시작 중: %s\n' "$URL"
nohup "$VENV_DIR/bin/uvicorn" app:app --host "$HOST" --port "$PORT" >"$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

for _ in {1..40}; do
  if is_running; then
    printf '실행 완료: %s\n' "$URL"
    printf '로그: %s\n' "$LOG_FILE"
    open_browser
    exit 0
  fi
  sleep 0.25
done

printf '서버 시작 확인에 실패했습니다. 로그를 확인하세요: %s\n' "$LOG_FILE" >&2
exit 1
