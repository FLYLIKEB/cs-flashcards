#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

DOMAIN="${CS_FLASHCARDS_DOMAIN:-cs.chamung.com}"
ORIGIN_DOMAIN="${CS_FLASHCARDS_ORIGIN_DOMAIN:-cs-origin.chamung.com}"
REMOTE_HOST="${CS_FLASHCARDS_LIGHTSAIL_HOST:-}"
REMOTE_USER="${CS_FLASHCARDS_LIGHTSAIL_USER:-ubuntu}"
SSH_KEY="${CS_FLASHCARDS_LIGHTSAIL_KEY:-}"
REMOTE_DIR="${CS_FLASHCARDS_REMOTE_DIR:-/home/ubuntu/cs-flashcards}"
REMOTE_PORT="${CS_FLASHCARDS_REMOTE_PORT:-8010}"
USERNAME="${CS_FLASHCARDS_USERNAME:-cs}"
PASSWORD="${CS_FLASHCARDS_PASSWORD:-}"
STATE_DIR="$ROOT_DIR/.omx"
PASSWORD_FILE="$STATE_DIR/cs_flashcards_public_password"
CHALOG_CONFIG="/Users/jwp/Developer/ChaLog/.ec2-config"

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
if [[ -z "$PASSWORD" && -f "$PASSWORD_FILE" ]]; then
  PASSWORD="$(cat "$PASSWORD_FILE")"
fi
if [[ -z "$PASSWORD" ]]; then
  echo "CS_FLASHCARDS_PASSWORD 또는 $PASSWORD_FILE 이 필요합니다." >&2
  exit 1
fi

if [[ -z "${REMOTE_HOST:-}" || ! -f "${SSH_KEY:-}" ]]; then
  echo "Lightsail 접속 정보가 없습니다. CS_FLASHCARDS_LIGHTSAIL_HOST / CS_FLASHCARDS_LIGHTSAIL_KEY를 지정하세요." >&2
  exit 1
fi

chmod 400 "$SSH_KEY" 2>/dev/null || true
SSH=(ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new "$REMOTE_USER@$REMOTE_HOST")
SCP=(scp -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new)

echo "배포 대상: $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
echo "도메인: http://$DOMAIN (443 개방 시 https://$DOMAIN)"

TMP_ARCHIVE="$(mktemp -t cs-flashcards.XXXXXX.tar.gz)"
COPYFILE_DISABLE=1 tar --no-xattrs -czf "$TMP_ARCHIVE" \
  app.py \
  requirements.txt \
  static \
  data/CS_encyclopedia_300plus.csv

"${SSH[@]}" "mkdir -p '$REMOTE_DIR' '$REMOTE_DIR/backups'"
"${SCP[@]}" "$TMP_ARCHIVE" "$REMOTE_USER@$REMOTE_HOST:/tmp/cs-flashcards.tar.gz"
rm -f "$TMP_ARCHIVE"

"${SSH[@]}" bash -s -- "$REMOTE_DIR" "$REMOTE_PORT" "$DOMAIN" "$ORIGIN_DOMAIN" "$USERNAME" "$PASSWORD" <<'REMOTE'
set -euo pipefail
REMOTE_DIR="$1"
REMOTE_PORT="$2"
DOMAIN="$3"
ORIGIN_DOMAIN="$4"
USERNAME="$5"
PASSWORD="$6"

export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -y >/dev/null
sudo apt-get install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx >/dev/null

mkdir -p "$REMOTE_DIR"
tar -xzf /tmp/cs-flashcards.tar.gz -C "$REMOTE_DIR"
rm -f /tmp/cs-flashcards.tar.gz
cd "$REMOTE_DIR"
python3 -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt

sudo tee /etc/systemd/system/cs-flashcards.service >/dev/null <<EOF
[Unit]
Description=CS Flashcards FastAPI
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$REMOTE_DIR
Environment=CS_FLASHCARDS_USERNAME=$USERNAME
Environment=CS_FLASHCARDS_PASSWORD=$PASSWORD
Environment=CS_FLASHCARD_CSV=$REMOTE_DIR/data/CS_encyclopedia_300plus.csv
Environment=CS_FLASHCARD_BACKUP_DIR=$REMOTE_DIR/backups
ExecStart=$REMOTE_DIR/.venv/bin/uvicorn app:app --host 127.0.0.1 --port $REMOTE_PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable cs-flashcards >/dev/null
sudo systemctl restart cs-flashcards
sleep 1
sudo systemctl --no-pager --full status cs-flashcards | sed -n '1,18p'

write_nginx_http() {
  sudo tee /etc/nginx/sites-available/cs-flashcards >/dev/null <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN $ORIGIN_DOMAIN;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:$REMOTE_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF
}

write_nginx_http
sudo ln -sf /etc/nginx/sites-available/cs-flashcards /etc/nginx/sites-enabled/cs-flashcards
sudo nginx -t
sudo systemctl reload nginx

if command -v certbot >/dev/null 2>&1; then
  # HTTPS 인증서는 발급하되, Lightsail 외부 방화벽에서 443이 닫혀 있을 수 있으므로
  # HTTP를 강제 HTTPS로 리다이렉트하지 않습니다. 443이 열린 환경에서는 HTTPS도 동작합니다.
  sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email "admin@$DOMAIN" --no-redirect || true
  write_nginx_http
  if [[ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" && -f "/etc/letsencrypt/live/$DOMAIN/privkey.pem" ]]; then
    sudo tee -a /etc/nginx/sites-available/cs-flashcards >/dev/null <<EOF

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name $DOMAIN $ORIGIN_DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:$REMOTE_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF
  fi
  sudo nginx -t && sudo systemctl reload nginx
fi

curl -sS -H "Authorization: Basic $(python3 - <<PY
import base64
print(base64.b64encode(b'$USERNAME:$PASSWORD').decode())
PY
)" "http://127.0.0.1:$REMOTE_PORT/api/health" || true
REMOTE

echo
echo "✅ Lightsail 배포 완료"
echo "주소: http://$DOMAIN"
echo "HTTPS: https://$DOMAIN (Lightsail 네트워크 방화벽 443 개방 시)"
echo "아이디: $USERNAME"
