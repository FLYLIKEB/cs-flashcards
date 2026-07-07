#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

HOST="${CS_FLASHCARDS_HOST:-127.0.0.1}"
PORT="${CS_FLASHCARDS_PORT:-8010}"
URL="http://${HOST}:${PORT}"
VENV_DIR="${CS_FLASHCARDS_VENV:-.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
STATE_DIR="$ROOT_DIR/.omx"
LOG_DIR="$STATE_DIR/logs"
PID_DIR="$STATE_DIR"
APP_LOG="$LOG_DIR/cs_flashcards_public_app.log"
TUNNEL_LOG="$LOG_DIR/cs_flashcards_cloudflare_tunnel.log"
APP_PID_FILE="$PID_DIR/cs_flashcards_public.pid"
TUNNEL_PID_FILE="$PID_DIR/cs_flashcards_cloudflare_tunnel.pid"
PASSWORD_FILE="$PID_DIR/cs_flashcards_public_password"
CONFIG_FILE="$PID_DIR/cs_flashcards_tunnel.env"
if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
fi
USERNAME="${CS_FLASHCARDS_USERNAME:-${CS_FLASHCARDS_PUBLIC_USERNAME:-cs}}"
PUBLIC_HOSTNAME="${CS_FLASHCARDS_PUBLIC_HOSTNAME:-${CS_FLASHCARDS_HOSTNAME:-}}"
TUNNEL_NAME="${CS_FLASHCARDS_TUNNEL_NAME:-cs-flashcards}"

mkdir -p "$LOG_DIR" "$PID_DIR"

make_password() {
  if [[ -n "${CS_FLASHCARDS_PASSWORD:-}" ]]; then
    printf '%s' "$CS_FLASHCARDS_PASSWORD"
    return 0
  fi
  if [[ -f "$PASSWORD_FILE" ]]; then
    cat "$PASSWORD_FILE"
    return 0
  fi
  local generated
  generated="$($PYTHON_BIN - <<'PY'
import secrets
print(secrets.token_urlsafe(12))
PY
)"
  chmod 700 "$PID_DIR" 2>/dev/null || true
  printf '%s' "$generated" > "$PASSWORD_FILE"
  chmod 600 "$PASSWORD_FILE" 2>/dev/null || true
  printf '%s' "$generated"
}

PASSWORD="$(make_password)"
AUTH_HEADER="$($PYTHON_BIN - <<PY
import base64
print('Basic ' + base64.b64encode('${USERNAME}:${PASSWORD}'.encode()).decode())
PY
)"

is_running() {
  "$PYTHON_BIN" - <<PY >/dev/null 2>&1
from urllib.request import Request, urlopen
url = "${URL}/api/health"
req = Request(url, headers={"Authorization": "${AUTH_HEADER}"})
try:
    with urlopen(req, timeout=1.5) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
}

install_cloudflared_if_needed() {
  if command -v cloudflared >/dev/null 2>&1; then
    return 0
  fi
  if command -v brew >/dev/null 2>&1; then
    printf 'cloudflared가 없어 Homebrew로 설치합니다...\n'
    brew install cloudflared
    return 0
  fi
  cat >&2 <<'EOF'
cloudflared 명령을 찾을 수 없습니다.
macOS에서는 Homebrew 설치 후 아래 명령을 실행하세요:
  brew install cloudflared
EOF
  exit 1
}

cleanup() {
  if [[ -f "$TUNNEL_PID_FILE" ]]; then
    local tunnel_pid
    tunnel_pid="$(cat "$TUNNEL_PID_FILE" 2>/dev/null || true)"
    if [[ -n "$tunnel_pid" ]] && kill -0 "$tunnel_pid" >/dev/null 2>&1; then
      kill "$tunnel_pid" >/dev/null 2>&1 || true
    fi
  fi
}
trap cleanup EXIT INT TERM

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  printf '가상환경 생성 중: %s\n' "$VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

printf '의존성 확인/설치 중...\n'
"$VENV_DIR/bin/python" -m pip install -q --upgrade pip
"$VENV_DIR/bin/python" -m pip install -q -r requirements.txt

if ! is_running; then
  if [[ -f "$APP_PID_FILE" ]]; then
    old_pid="$(cat "$APP_PID_FILE" 2>/dev/null || true)"
    if [[ -n "${old_pid:-}" ]] && kill -0 "$old_pid" >/dev/null 2>&1; then
      kill "$old_pid" >/dev/null 2>&1 || true
      sleep 0.3
    fi
  fi
  printf '비밀번호 보호 서버 시작 중: %s\n' "$URL"
  CS_FLASHCARDS_USERNAME="$USERNAME" \
  CS_FLASHCARDS_PASSWORD="$PASSWORD" \
  nohup "$VENV_DIR/bin/uvicorn" app:app --host "$HOST" --port "$PORT" >"$APP_LOG" 2>&1 &
  echo $! > "$APP_PID_FILE"
  for _ in {1..50}; do
    if is_running; then
      break
    fi
    sleep 0.2
  done
fi

if ! is_running; then
  printf '서버 시작 확인에 실패했습니다. 로그: %s\n' "$APP_LOG" >&2
  exit 1
fi

install_cloudflared_if_needed
: > "$TUNNEL_LOG"

if [[ -n "$PUBLIC_HOSTNAME" ]]; then
  PUBLIC_URL="https://${PUBLIC_HOSTNAME}"
  printf 'Cloudflare 고정 Tunnel 시작 중: %s -> %s\n' "$PUBLIC_URL" "$URL"
  cloudflared tunnel run --url "$URL" "$TUNNEL_NAME" >"$TUNNEL_LOG" 2>&1 &
  echo $! > "$TUNNEL_PID_FILE"
  for _ in {1..80}; do
    if grep -Eiq 'Registered tunnel connection|Connection.*registered|Starting tunnel' "$TUNNEL_LOG"; then
      break
    fi
    if ! kill -0 "$(cat "$TUNNEL_PID_FILE")" >/dev/null 2>&1; then
      printf 'Cloudflare 고정 Tunnel 실행에 실패했습니다. 로그: %s\n' "$TUNNEL_LOG" >&2
      cat "$TUNNEL_LOG" >&2 || true
      exit 1
    fi
    sleep 0.25
  done
else
  printf 'Cloudflare 임시 Tunnel 시작 중...\n'
  cloudflared tunnel --url "$URL" >"$TUNNEL_LOG" 2>&1 &
  echo $! > "$TUNNEL_PID_FILE"

  PUBLIC_URL=""
  for _ in {1..80}; do
    PUBLIC_URL="$(grep -Eo 'https://[-a-zA-Z0-9.]+\.trycloudflare\.com' "$TUNNEL_LOG" | tail -n 1 || true)"
    if [[ -n "$PUBLIC_URL" ]]; then
      break
    fi
    if ! kill -0 "$(cat "$TUNNEL_PID_FILE")" >/dev/null 2>&1; then
      printf 'Cloudflare 임시 Tunnel 실행에 실패했습니다. 로그: %s\n' "$TUNNEL_LOG" >&2
      cat "$TUNNEL_LOG" >&2 || true
      exit 1
    fi
    sleep 0.25
  done

  if [[ -z "$PUBLIC_URL" ]]; then
    printf '공개 URL을 찾지 못했습니다. 로그: %s\n' "$TUNNEL_LOG" >&2
    cat "$TUNNEL_LOG" >&2 || true
    exit 1
  fi
fi

cat <<EOF

✅ 폰 접속용 공개 주소가 준비됐습니다.

주소: $PUBLIC_URL
아이디: $USERNAME
비밀번호: $PASSWORD

- iPhone Safari/Chrome에서 위 주소를 열면 됩니다.
- 이 터미널을 닫으면 공개 접속도 종료됩니다.
- O/X 체크는 이 Mac의 CSV에 저장됩니다.
- 고정주소 설정 파일: ${CONFIG_FILE}
- 앱 로그: $APP_LOG
- 터널 로그: $TUNNEL_LOG
EOF

if command -v open >/dev/null 2>&1 && [[ "${CS_FLASHCARDS_NO_OPEN:-0}" != "1" ]]; then
  open "$PUBLIC_URL" || true
fi

wait "$(cat "$TUNNEL_PID_FILE")"
