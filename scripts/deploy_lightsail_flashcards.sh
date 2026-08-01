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
WIKI_BOOK_SRC="${CS_FLASHCARDS_WIKI_BOOK_SRC:-$ROOT_DIR/../wikidocs-ebook}"
WIKI_GITHUB_TOKEN="${CS_FLASHCARDS_WIKI_GITHUB_TOKEN:-${GITHUB_TOKEN:-${GH_TOKEN:-}}}"
WIKI_GITHUB_REPO="${CS_FLASHCARDS_WIKI_GITHUB_REPO:-}"
WIKI_GITHUB_BRANCH="${CS_FLASHCARDS_WIKI_GITHUB_BRANCH:-}"
WIKI_GITHUB_PATH_PREFIX="${CS_FLASHCARDS_WIKI_GITHUB_PATH_PREFIX:-}"
FORCE_DB_REPLACE="${CS_FLASHCARDS_FORCE_DB_REPLACE:-0}"
OPENAI_API_KEY_VALUE="${OPENAI_API_KEY:-${CS_FLASHCARDS_OPENAI_API_KEY:-}}"


if ! [[ "$FORCE_DB_REPLACE" =~ ^(0|1)$ ]]; then
  echo "CS_FLASHCARDS_FORCE_DB_REPLACE 는 0 또는 1 이어야 합니다: $FORCE_DB_REPLACE" >&2
  exit 1
fi


if [[ -f "$CHALOG_CONFIG" ]]; then
  # shellcheck disable=SC1090
  source "$CHALOG_CONFIG"
  REMOTE_HOST="${REMOTE_HOST:-${EC2_HOST:-}}"
  REMOTE_USER="${CS_FLASHCARDS_LIGHTSAIL_USER:-${EC2_USER:-ubuntu}}"
  SSH_KEY="${SSH_KEY:-${SSH_KEY_PATH:-${LIGHTSAIL_KEY_PATH:-}}}"
fi

extract_github_repo() {
  local remote_url="${1:-}"
  remote_url="${remote_url%.git}"
  case "$remote_url" in
    https://github.com/*)
      printf '%s\n' "${remote_url#https://github.com/}"
      ;;
    git@github.com:*)
      printf '%s\n' "${remote_url#git@github.com:}"
      ;;
    ssh://git@github.com/*)
      printf '%s\n' "${remote_url#ssh://git@github.com/}"
      ;;
    *)
      return 1
      ;;
  esac
}

if [[ -d "$WIKI_BOOK_SRC/.git" ]]; then
  if [[ -z "$WIKI_GITHUB_REPO" ]]; then
    ORIGIN_URL="$(git -C "$WIKI_BOOK_SRC" remote get-url origin 2>/dev/null || true)"
    if DETECTED_WIKI_GITHUB_REPO="$(extract_github_repo "$ORIGIN_URL")"; then
      WIKI_GITHUB_REPO="$DETECTED_WIKI_GITHUB_REPO"
    fi
  fi
  if [[ -z "$WIKI_GITHUB_BRANCH" ]]; then
    WIKI_GITHUB_BRANCH="$(git -C "$WIKI_BOOK_SRC" branch --show-current 2>/dev/null || true)"
  fi
fi
WIKI_GITHUB_BRANCH="${WIKI_GITHUB_BRANCH:-main}"
if [[ -n "$WIKI_GITHUB_REPO" && -z "$WIKI_GITHUB_TOKEN" ]] && command -v gh >/dev/null 2>&1; then
  WIKI_GITHUB_TOKEN="$(gh auth token 2>/dev/null || true)"
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

echo "개념 이미지: SQLite cards 테이블에 URL/미디어를 기록하고 AI 재생성 이미지는 서버 state/ai_images 에 저장"


chmod 400 "$SSH_KEY" 2>/dev/null || true
SSH=(ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new "$REMOTE_USER@$REMOTE_HOST")
SCP=(scp -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new)

echo "배포 대상: $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
echo "도메인: http://$DOMAIN (443 개방 시 https://$DOMAIN)"
echo "원격 wiki_book 권한: 서버 로컬 원본 유지 (일반 배포에서 덮어쓰지 않음)"
if [[ -n "$WIKI_GITHUB_REPO" && -n "$WIKI_GITHUB_TOKEN" ]]; then
  echo "위키 GitHub 수동 보관 버튼: $WIKI_GITHUB_REPO@$WIKI_GITHUB_BRANCH"
else
  echo "위키 GitHub 수동 보관 버튼: 비활성"
fi

TMP_ARCHIVE="$(mktemp -t cs-flashcards.XXXXXX.tar.gz)"
TMP_STAGE="$(mktemp -d -t cs-flashcards-stage.XXXXXX)"
mkdir -p "$TMP_STAGE/data" "$TMP_STAGE/state"
cp app.py question_generator.py requirements.txt "$TMP_STAGE/"
cp -R static "$TMP_STAGE/"
cp data/recruitment_schedule_2026.json "$TMP_STAGE/data/"
if [[ "$FORCE_DB_REPLACE" == "1" ]]; then
  echo "경고: CS_FLASHCARDS_FORCE_DB_REPLACE=1 이므로 원격 state/progress.sqlite 전체를 로컬 파일로 교체합니다."
  cp state/progress.sqlite "$TMP_STAGE/state/"
else
  echo "원격 state/progress.sqlite 보존: 일반 배포에서는 런타임 DB 전체 파일을 덮어쓰지 않습니다."
fi
WIKI_PACKAGE_SRC="$WIKI_BOOK_SRC"
if [[ -d "$WIKI_PACKAGE_SRC" ]]; then
  if [[ ! -f "$WIKI_PACKAGE_SRC/README.md" || ! -f "$WIKI_PACKAGE_SRC/TOC.md" || ! -d "$WIKI_PACKAGE_SRC/pages" ]]; then
    echo "위키 문서 디렉터리 구조가 올바르지 않습니다: $WIKI_PACKAGE_SRC" >&2
    exit 1
  fi
  echo "위키 시드 포함: $WIKI_PACKAGE_SRC"
  mkdir -p "$TMP_STAGE/wiki_book_seed"
  cp "$WIKI_PACKAGE_SRC/README.md" "$TMP_STAGE/wiki_book_seed/README.md"
  cp "$WIKI_PACKAGE_SRC/TOC.md" "$TMP_STAGE/wiki_book_seed/TOC.md"
  cp -R "$WIKI_PACKAGE_SRC/pages" "$TMP_STAGE/wiki_book_seed/"
else
  echo "경고: 위키 문서 디렉터리를 찾지 못해 위키 시드 없이 배포합니다: $WIKI_PACKAGE_SRC"
fi
COPYFILE_DISABLE=1 tar --no-xattrs -czf "$TMP_ARCHIVE" -C "$TMP_STAGE" .
rm -rf "$TMP_STAGE"


"${SSH[@]}" "mkdir -p '$REMOTE_DIR' '$REMOTE_DIR/backups'"
"${SCP[@]}" "$TMP_ARCHIVE" "$REMOTE_USER@$REMOTE_HOST:/tmp/cs-flashcards.tar.gz"
rm -f "$TMP_ARCHIVE"
WIKI_GITHUB_PATH_PREFIX_ARG="${WIKI_GITHUB_PATH_PREFIX:-__EMPTY__}"
WIKI_GITHUB_TOKEN_ARG="${WIKI_GITHUB_TOKEN:-__EMPTY__}"

OPENAI_API_KEY_ARG="${OPENAI_API_KEY_VALUE:-__EMPTY__}"


"${SSH[@]}" bash -s -- "$REMOTE_DIR" "$REMOTE_PORT" "$DOMAIN" "$ORIGIN_DOMAIN" "$USERNAME" "$PASSWORD" "$WIKI_GITHUB_REPO" "$WIKI_GITHUB_BRANCH" "$WIKI_GITHUB_TOKEN_ARG" "$WIKI_GITHUB_PATH_PREFIX_ARG" "$OPENAI_API_KEY_ARG" <<'REMOTE'
set -euo pipefail
REMOTE_DIR="$1"
REMOTE_PORT="$2"
DOMAIN="$3"
ORIGIN_DOMAIN="$4"
USERNAME="$5"
PASSWORD="$6"
WIKI_GITHUB_REPO="${7-}"
WIKI_GITHUB_BRANCH="${8-}"
WIKI_GITHUB_TOKEN="${9-}"
WIKI_GITHUB_PATH_PREFIX="${10-}"
OPENAI_API_KEY_VALUE="${11-}"
if [[ "$WIKI_GITHUB_TOKEN" == "__EMPTY__" ]]; then
  WIKI_GITHUB_TOKEN=""
fi
if [[ "$WIKI_GITHUB_PATH_PREFIX" == "__EMPTY__" ]]; then
  WIKI_GITHUB_PATH_PREFIX=""
fi
if [[ "$OPENAI_API_KEY_VALUE" == "__EMPTY__" ]]; then
  OPENAI_API_KEY_VALUE=""
fi


export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -y >/dev/null
sudo apt-get install -y git python3 python3-venv python3-pip nginx certbot python3-certbot-nginx >/dev/null

mkdir -p "$REMOTE_DIR" "$REMOTE_DIR/state"

# Remove stale pre-flattened layout from older deployments.
rm -rf "$REMOTE_DIR/cs_flashcards"
tar -xzf /tmp/cs-flashcards.tar.gz -C "$REMOTE_DIR"
rm -f /tmp/cs-flashcards.tar.gz
rm -rf "$REMOTE_DIR/static/generated"
if [[ -d "$REMOTE_DIR/wiki_book_seed/pages" ]]; then
  if [[ -d "$REMOTE_DIR/wiki_book/pages" ]]; then
    echo "원격 wiki_book 보존: 기존 서버 위키를 그대로 유지합니다."
  else
    echo "원격 wiki_book 부트스트랩: 로컬 시드로 초기화합니다."
    mv "$REMOTE_DIR/wiki_book_seed" "$REMOTE_DIR/wiki_book"
  fi
fi
rm -rf "$REMOTE_DIR/wiki_book_seed"
cd "$REMOTE_DIR"
python3 -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt
.venv/bin/python - <<'PY'
import json
import app
cards, _ = app.read_card_content(app.PROGRESS_DB_PATH)
print("SQLite card db:", json.dumps({
    "count": len(cards),
    "path": str(app.PROGRESS_DB_PATH),
}, ensure_ascii=False))
PY
if [[ -d "$REMOTE_DIR/wiki_book/pages" ]]; then
  .venv/bin/python - <<'PY'
import json
import app
fin_corp = app.sync_fin_corp_question_bank_entries(app.wiki_book_dir(), app.PROGRESS_DB_PATH)
print("239 question-bank sync:", json.dumps({
    "pages": fin_corp.get("pages", 0),
    "cleared": fin_corp.get("cleared", 0),
    "count": fin_corp.get("count", 0),
}, ensure_ascii=False))
bok = app.sync_bok_question_bank_entries(app.wiki_book_dir(), app.PROGRESS_DB_PATH)
print("BOK question-bank sync:", json.dumps({
    "pages": bok.get("pages", 0),
    "cleared": bok.get("cleared", 0),
    "count": bok.get("count", 0),
}, ensure_ascii=False))
PY
fi

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
Environment=CS_FLASHCARD_BACKUP_DIR=$REMOTE_DIR/backups
Environment=CS_FLASHCARD_PROGRESS_DB=$REMOTE_DIR/state/progress.sqlite
Environment=CS_FLASHCARDS_WIKI_BOOK_DIR=$REMOTE_DIR/wiki_book
Environment=CS_FLASHCARDS_WIKI_GITHUB_REPO=$WIKI_GITHUB_REPO
Environment=CS_FLASHCARDS_WIKI_GITHUB_BRANCH=$WIKI_GITHUB_BRANCH
Environment=CS_FLASHCARDS_WIKI_GITHUB_TOKEN=$WIKI_GITHUB_TOKEN
Environment=CS_FLASHCARDS_WIKI_GITHUB_PATH_PREFIX=$WIKI_GITHUB_PATH_PREFIX
Environment=OPENAI_API_KEY=$OPENAI_API_KEY_VALUE
ExecStart=$REMOTE_DIR/.venv/bin/uvicorn app:app --host 127.0.0.1 --port $REMOTE_PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl disable --now cs-flashcards-wiki-sync.timer >/dev/null 2>&1 || true
sudo rm -f /etc/systemd/system/cs-flashcards-wiki-sync.service /etc/systemd/system/cs-flashcards-wiki-sync.timer
rm -f "$REMOTE_DIR/bin/sync_wiki_book.sh"
rm -rf "$REMOTE_DIR/state/wiki_repo"

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
