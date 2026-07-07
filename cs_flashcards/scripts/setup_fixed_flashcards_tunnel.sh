#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

HOSTNAME="${1:-${CS_FLASHCARDS_PUBLIC_HOSTNAME:-}}"
TUNNEL_NAME="${2:-${CS_FLASHCARDS_TUNNEL_NAME:-cs-flashcards}}"
PID_DIR="$ROOT_DIR/cs_flashcards/.omx"
CONFIG_FILE="$PID_DIR/cs_flashcards_tunnel.env"
PYTHON_BIN="${PYTHON_BIN:-python3}"
USERNAME="${CS_FLASHCARDS_USERNAME:-cs}"
PASSWORD_FILE="$PID_DIR/cs_flashcards_public_password"
DNS_PROVIDER=""
TUNNEL_ID=""
CNAME_TARGET=""

if [[ -z "$HOSTNAME" ]]; then
  cat >&2 <<'EOF'
사용법:
  ./cs_flashcards/scripts/setup_fixed_flashcards_tunnel.sh cards.example.com
  ./cs_flashcards/scripts/setup_chamung_flashcards_tunnel.sh

필수 조건:
  - Cloudflare 계정이 있어야 합니다.
  - 고정주소로 쓸 도메인/서브도메인이 있어야 합니다.
  - Cloudflare DNS면 자동 route dns를 사용합니다.
  - Vercel DNS면 CNAME을 자동 추가하거나 수동 추가 안내를 출력합니다.
EOF
  exit 2
fi

mkdir -p "$PID_DIR"
chmod 700 "$PID_DIR" 2>/dev/null || true

install_cloudflared_if_needed() {
  if command -v cloudflared >/dev/null 2>&1; then
    return 0
  fi
  if command -v brew >/dev/null 2>&1; then
    printf 'cloudflared가 없어 Homebrew로 설치합니다...\n'
    brew install cloudflared
    return 0
  fi
  printf 'cloudflared가 없습니다. 먼저 설치하세요.\n' >&2
  exit 1
}

make_password_if_needed() {
  if [[ -n "${CS_FLASHCARDS_PASSWORD:-}" ]]; then
    printf '%s' "$CS_FLASHCARDS_PASSWORD" > "$PASSWORD_FILE"
    chmod 600 "$PASSWORD_FILE" 2>/dev/null || true
    return 0
  fi
  if [[ -f "$PASSWORD_FILE" ]]; then
    return 0
  fi
  "$PYTHON_BIN" - <<'PY' > "$PASSWORD_FILE"
import secrets
print(secrets.token_urlsafe(12))
PY
  chmod 600 "$PASSWORD_FILE" 2>/dev/null || true
}

base_domain() {
  "$PYTHON_BIN" - "$HOSTNAME" <<'PY'
import sys
host = sys.argv[1].strip('.').lower()
parts = host.split('.')
print('.'.join(parts[-2:]) if len(parts) >= 2 else host)
PY
}

subdomain_part() {
  "$PYTHON_BIN" - "$HOSTNAME" "$(base_domain)" <<'PY'
import sys
host = sys.argv[1].strip('.').lower()
base = sys.argv[2].strip('.').lower()
if host == base:
    print('@')
elif host.endswith('.' + base):
    print(host[:-(len(base)+1)])
else:
    print(host)
PY
}

detect_dns_provider() {
  local base ns
  base="$(base_domain)"
  ns="$(dig +short "$base" NS 2>/dev/null | tr '[:upper:]' '[:lower:]' | tr '\n' ' ')"
  if [[ "$ns" == *cloudflare* ]]; then
    DNS_PROVIDER="cloudflare"
  elif [[ "$ns" == *vercel-dns* ]] || [[ "$ns" == *zeit-world* ]]; then
    DNS_PROVIDER="vercel"
  else
    DNS_PROVIDER="manual"
  fi
}

read_tunnel_id() {
  TUNNEL_ID="$(cloudflared tunnel list --name "$TUNNEL_NAME" --output json 2>/dev/null | "$PYTHON_BIN" -c 'import json,sys; data=json.load(sys.stdin); data=data.get("tunnels", data.get("result", [])) if isinstance(data, dict) else data; print((data[0].get("id") or data[0].get("ID") or "") if data else "")' 2>/dev/null || true)"
  if [[ -z "$TUNNEL_ID" ]]; then
    TUNNEL_ID="$(find "$HOME/.cloudflared" -maxdepth 1 -name '*.json' -type f -print 2>/dev/null | while read -r f; do "$PYTHON_BIN" - "$f" "$TUNNEL_NAME" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
name = sys.argv[2]
try:
    data = json.loads(path.read_text())
except Exception:
    data = {}
if data.get('TunnelName') == name and data.get('TunnelID'):
    print(data['TunnelID'])
PY
done | head -n 1)"
  fi
  if [[ -z "$TUNNEL_ID" ]]; then
    printf 'Tunnel UUID를 확인하지 못했습니다. cloudflared tunnel list를 확인하세요.\n' >&2
    exit 1
  fi
  CNAME_TARGET="${TUNNEL_ID}.cfargotunnel.com"
}

configure_dns() {
  detect_dns_provider
  read_tunnel_id
  case "$DNS_PROVIDER" in
    cloudflare)
      printf 'Cloudflare DNS 라우팅 설정: %s -> %s\n' "$HOSTNAME" "$TUNNEL_NAME"
      cloudflared tunnel route dns --overwrite-dns "$TUNNEL_NAME" "$HOSTNAME"
      ;;
    vercel)
      local base sub
      base="$(base_domain)"
      sub="$(subdomain_part)"
      cat <<EOF

❌ Vercel DNS에서는 Cloudflare Tunnel 고정주소를 직접 연결할 수 없습니다.

감지된 DNS: Vercel DNS ($base)
요청 주소: $HOSTNAME
필요 CNAME처럼 보이는 값: $CNAME_TARGET

하지만 Cloudflare 공식 문서상 cfargotunnel.com 대상은 같은 Cloudflare 계정의 DNS 레코드에서만 프록시됩니다.
따라서 아래 중 하나가 필요합니다.

1) chamung.com 네임서버를 Cloudflare로 이전한 뒤 다시 실행
   ./cs_flashcards/scripts/setup_chamung_flashcards_tunnel.sh $HOSTNAME

2) Cloudflare가 DNS를 관리하는 다른 도메인/서브도메인 사용
   ./cs_flashcards/scripts/setup_fixed_flashcards_tunnel.sh cards.your-cloudflare-domain.com

3) 고정주소를 포기하고 임시 주소 사용
   rm -f cs_flashcards/.omx/cs_flashcards_tunnel.env
   ./cs_flashcards/scripts/run_public_flashcards.sh
EOF
      exit 1
      ;;
    *)
      cat <<EOF

⚠️ DNS 제공자를 자동 인식하지 못했습니다. DNS 관리자에서 직접 CNAME을 추가하세요.
Type: CNAME
Name: $HOSTNAME
Value: $CNAME_TARGET
EOF
      ;;
  esac
}

install_cloudflared_if_needed
make_password_if_needed

if [[ ! -f "$HOME/.cloudflared/cert.pem" ]]; then
  printf 'Cloudflare 로그인이 필요합니다. 브라우저에서 도메인을 선택하세요.\n'
  cloudflared tunnel login
fi

if cloudflared tunnel info "$TUNNEL_NAME" >/dev/null 2>&1; then
  printf '기존 Tunnel 사용: %s\n' "$TUNNEL_NAME"
else
  printf '새 Tunnel 생성: %s\n' "$TUNNEL_NAME"
  cloudflared tunnel create "$TUNNEL_NAME"
fi

configure_dns

cat > "$CONFIG_FILE" <<EOF
CS_FLASHCARDS_PUBLIC_HOSTNAME="$HOSTNAME"
CS_FLASHCARDS_TUNNEL_NAME="$TUNNEL_NAME"
CS_FLASHCARDS_PUBLIC_USERNAME="$USERNAME"
EOF
chmod 600 "$CONFIG_FILE" 2>/dev/null || true

cat <<EOF

✅ 고정주소 설정 완료

주소: https://$HOSTNAME
아이디: $USERNAME
비밀번호: $(cat "$PASSWORD_FILE")
Tunnel: $TUNNEL_NAME
DNS: $DNS_PROVIDER
CNAME: ${CNAME_TARGET:-Cloudflare route dns}
설정파일: $CONFIG_FILE

앞으로는 아래 명령만 실행하면 같은 주소로 열립니다:
  ./cs_flashcards/scripts/run_public_flashcards.sh
EOF
