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
WIKI_SYNC_INTERVAL_MINUTES="${CS_FLASHCARDS_WIKI_SYNC_INTERVAL_MINUTES:-5}"
if ! [[ "$WIKI_SYNC_INTERVAL_MINUTES" =~ ^[1-9][0-9]*$ ]]; then
  echo "CS_FLASHCARDS_WIKI_SYNC_INTERVAL_MINUTES 는 1 이상의 정수여야 합니다: $WIKI_SYNC_INTERVAL_MINUTES" >&2
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

echo "개념 이미지: CSV concept_image_url 값이 있을 때만 렌더링; 생성 이미지 배포 없음"

chmod 400 "$SSH_KEY" 2>/dev/null || true
SSH=(ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new "$REMOTE_USER@$REMOTE_HOST")
SCP=(scp -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new)

echo "배포 대상: $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
echo "도메인: http://$DOMAIN (443 개방 시 https://$DOMAIN)"
if [[ -n "$WIKI_GITHUB_REPO" ]]; then
  echo "위키 원본 GitHub 자동 동기화: $WIKI_GITHUB_REPO@$WIKI_GITHUB_BRANCH (${WIKI_SYNC_INTERVAL_MINUTES}분 주기)"
else
  echo "위키 원본 GitHub 자동 동기화: 비활성"
fi
if [[ -n "$WIKI_GITHUB_TOKEN" && -n "$WIKI_GITHUB_REPO" ]]; then
  echo "위키 체크리스트 GitHub 동기화: 활성"
else
  echo "위키 체크리스트 GitHub 동기화: 비활성"
fi

TMP_ARCHIVE="$(mktemp -t cs-flashcards.XXXXXX.tar.gz)"
TMP_STAGE="$(mktemp -d -t cs-flashcards-stage.XXXXXX)"
mkdir -p "$TMP_STAGE/data"
cp app.py question_generator.py requirements.txt "$TMP_STAGE/"
cp -R static "$TMP_STAGE/"
cp data/CS_encyclopedia_300plus.csv "$TMP_STAGE/data/"
if [[ -d "$WIKI_BOOK_SRC" ]]; then
  echo "위키 문서 포함: $WIKI_BOOK_SRC"
  mkdir -p "$TMP_STAGE/wiki_book"
  cp "$WIKI_BOOK_SRC/README.md" "$TMP_STAGE/wiki_book/README.md"
  cp "$WIKI_BOOK_SRC/TOC.md" "$TMP_STAGE/wiki_book/TOC.md"
  cp -R "$WIKI_BOOK_SRC/pages" "$TMP_STAGE/wiki_book/"
else
  echo "경고: 위키 문서 디렉터리를 찾지 못해 위키 없이 배포합니다: $WIKI_BOOK_SRC"
fi
COPYFILE_DISABLE=1 tar --no-xattrs -czf "$TMP_ARCHIVE" -C "$TMP_STAGE" .
rm -rf "$TMP_STAGE"


"${SSH[@]}" "mkdir -p '$REMOTE_DIR' '$REMOTE_DIR/backups'"
"${SCP[@]}" "$TMP_ARCHIVE" "$REMOTE_USER@$REMOTE_HOST:/tmp/cs-flashcards.tar.gz"
rm -f "$TMP_ARCHIVE"
WIKI_GITHUB_PATH_PREFIX_ARG="${WIKI_GITHUB_PATH_PREFIX:-__EMPTY__}"

"${SSH[@]}" bash -s -- "$REMOTE_DIR" "$REMOTE_PORT" "$DOMAIN" "$ORIGIN_DOMAIN" "$USERNAME" "$PASSWORD" "$WIKI_GITHUB_REPO" "$WIKI_GITHUB_BRANCH" "$WIKI_GITHUB_TOKEN" "$WIKI_GITHUB_PATH_PREFIX_ARG" "$WIKI_SYNC_INTERVAL_MINUTES" <<'REMOTE'
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
WIKI_SYNC_INTERVAL_MINUTES="${11-5}"
if [[ "$WIKI_GITHUB_PATH_PREFIX" == "__EMPTY__" ]]; then
  WIKI_GITHUB_PATH_PREFIX=""
fi

export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -y >/dev/null
sudo apt-get install -y git python3 python3-venv python3-pip nginx certbot python3-certbot-nginx >/dev/null

mkdir -p "$REMOTE_DIR" "$REMOTE_DIR/state"

# Preserve learning progress before the content CSV is replaced by deployment.
# Existing SQLite rows win; old CSV progress is imported only for cards not yet in the DB.
python3 - "$REMOTE_DIR/data/CS_encyclopedia_300plus.csv" "$REMOTE_DIR/state/progress.sqlite" <<'PY'
from __future__ import annotations
import csv
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

csv_path = Path(sys.argv[1])
db_path = Path(sys.argv[2])
valid = {"O", "X", ""}

def review_count(value: str | None) -> int:
    try:
        return max(0, int(value or "0"))
    except ValueError:
        return 0

if csv_path.exists():
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS card_progress (
                card_id TEXT PRIMARY KEY,
                known_status TEXT NOT NULL DEFAULT '' CHECK (known_status IN ('O', 'X', '')),
                last_reviewed TEXT NOT NULL DEFAULT '',
                review_count INTEGER NOT NULL DEFAULT 0 CHECK (review_count >= 0),
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_card_progress_status ON card_progress(known_status)")
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        imported = 0
        with csv_path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                card_id = row.get("id") or ""
                status = row.get("known_status") or ""
                if status not in valid:
                    status = ""
                last_reviewed = row.get("last_reviewed") or ""
                count = review_count(row.get("review_count"))
                if not card_id or not (status or last_reviewed or count > 0):
                    continue
                before = conn.total_changes
                conn.execute(
                    """
                    INSERT OR IGNORE INTO card_progress
                        (card_id, known_status, last_reviewed, review_count, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (card_id, status, last_reviewed, count, now),
                )
                imported += conn.total_changes - before
        conn.commit()
        print(f"progress migration: imported {imported} row(s) from existing remote CSV")
    finally:
        conn.close()
else:
    print("progress migration: no existing remote CSV")
PY

# Remove stale pre-flattened layout from older deployments.
rm -rf "$REMOTE_DIR/cs_flashcards"
tar -xzf /tmp/cs-flashcards.tar.gz -C "$REMOTE_DIR"
rm -f /tmp/cs-flashcards.tar.gz
rm -rf "$REMOTE_DIR/static/generated"
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
Environment=CS_FLASHCARD_PROGRESS_DB=$REMOTE_DIR/state/progress.sqlite
Environment=CS_FLASHCARDS_WIKI_BOOK_DIR=$REMOTE_DIR/wiki_book
Environment=CS_FLASHCARDS_WIKI_GITHUB_REPO=$WIKI_GITHUB_REPO
Environment=CS_FLASHCARDS_WIKI_GITHUB_BRANCH=$WIKI_GITHUB_BRANCH
Environment=CS_FLASHCARDS_WIKI_GITHUB_TOKEN=$WIKI_GITHUB_TOKEN
Environment=CS_FLASHCARDS_WIKI_GITHUB_PATH_PREFIX=$WIKI_GITHUB_PATH_PREFIX
ExecStart=$REMOTE_DIR/.venv/bin/uvicorn app:app --host 127.0.0.1 --port $REMOTE_PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

if [[ -n "$WIKI_GITHUB_REPO" ]]; then
  mkdir -p "$REMOTE_DIR/bin"
  tee "$REMOTE_DIR/bin/sync_wiki_book.sh" >/dev/null <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
REMOTE_DIR="${CS_FLASHCARDS_REMOTE_DIR:?}"
WIKI_GITHUB_REPO="${CS_FLASHCARDS_WIKI_GITHUB_REPO:-}"
WIKI_GITHUB_BRANCH="${CS_FLASHCARDS_WIKI_GITHUB_BRANCH:-main}"
WIKI_GITHUB_TOKEN="${CS_FLASHCARDS_WIKI_GITHUB_TOKEN:-}"
WIKI_GITHUB_PATH_PREFIX="${CS_FLASHCARDS_WIKI_GITHUB_PATH_PREFIX:-}"
if [[ -z "$WIKI_GITHUB_REPO" ]]; then
  echo "wiki sync: repo not configured"
  exit 0
fi
REPO_DIR="$REMOTE_DIR/state/wiki_repo"
SOURCE_DIR="$REPO_DIR"
if [[ -n "$WIKI_GITHUB_PATH_PREFIX" ]]; then
  SOURCE_DIR="$REPO_DIR/$WIKI_GITHUB_PATH_PREFIX"
fi
AUTH_URL="https://github.com/${WIKI_GITHUB_REPO}.git"
if [[ -n "$WIKI_GITHUB_TOKEN" ]]; then
  AUTH_URL="https://x-access-token:${WIKI_GITHUB_TOKEN}@github.com/${WIKI_GITHUB_REPO}.git"
fi
PLAIN_URL="https://github.com/${WIKI_GITHUB_REPO}.git"
if [[ ! -d "$REPO_DIR/.git" ]]; then
  rm -rf "$REPO_DIR"
  git clone --depth 1 --branch "$WIKI_GITHUB_BRANCH" "$AUTH_URL" "$REPO_DIR"
else
  git -C "$REPO_DIR" remote set-url origin "$AUTH_URL"
  git -C "$REPO_DIR" fetch --depth 1 origin "$WIKI_GITHUB_BRANCH"
  git -C "$REPO_DIR" checkout -B "$WIKI_GITHUB_BRANCH" "origin/$WIKI_GITHUB_BRANCH"
  git -C "$REPO_DIR" reset --hard "origin/$WIKI_GITHUB_BRANCH"
fi
git -C "$REPO_DIR" remote set-url origin "$PLAIN_URL"
if [[ ! -f "$SOURCE_DIR/README.md" || ! -f "$SOURCE_DIR/TOC.md" || ! -d "$SOURCE_DIR/pages" ]]; then
  echo "wiki sync: expected README.md, TOC.md, pages/ under $SOURCE_DIR" >&2
  exit 1
fi
STAGE_DIR="$(mktemp -d "$REMOTE_DIR/state/wiki_book.stage.XXXXXX")"
trap 'rm -rf "$STAGE_DIR"' EXIT
cp "$SOURCE_DIR/README.md" "$STAGE_DIR/README.md"
cp "$SOURCE_DIR/TOC.md" "$STAGE_DIR/TOC.md"
cp -R "$SOURCE_DIR/pages" "$STAGE_DIR/"
git -C "$REPO_DIR" rev-parse HEAD > "$STAGE_DIR/.source-commit"
PREV_DIR="$REMOTE_DIR/wiki_book.previous"
rm -rf "$PREV_DIR"
if [[ -e "$REMOTE_DIR/wiki_book" ]]; then
  mv "$REMOTE_DIR/wiki_book" "$PREV_DIR"
fi
mv "$STAGE_DIR" "$REMOTE_DIR/wiki_book"
rm -rf "$PREV_DIR"
trap - EXIT
echo "wiki sync: $(cat "$REMOTE_DIR/wiki_book/.source-commit")"
EOF
  chmod 700 "$REMOTE_DIR/bin/sync_wiki_book.sh"

  sudo tee /etc/systemd/system/cs-flashcards-wiki-sync.service >/dev/null <<EOF
[Unit]
Description=Sync CS Flashcards wiki mirror from GitHub
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=$REMOTE_DIR
Environment=CS_FLASHCARDS_REMOTE_DIR=$REMOTE_DIR
Environment=CS_FLASHCARDS_WIKI_GITHUB_REPO=$WIKI_GITHUB_REPO
Environment=CS_FLASHCARDS_WIKI_GITHUB_BRANCH=$WIKI_GITHUB_BRANCH
Environment=CS_FLASHCARDS_WIKI_GITHUB_TOKEN=$WIKI_GITHUB_TOKEN
Environment=CS_FLASHCARDS_WIKI_GITHUB_PATH_PREFIX=$WIKI_GITHUB_PATH_PREFIX
ExecStart=/usr/bin/env bash $REMOTE_DIR/bin/sync_wiki_book.sh
EOF

  sudo tee /etc/systemd/system/cs-flashcards-wiki-sync.timer >/dev/null <<EOF
[Unit]
Description=Periodic wiki mirror sync for CS Flashcards

[Timer]
OnBootSec=2min
OnUnitActiveSec=${WIKI_SYNC_INTERVAL_MINUTES}min
RandomizedDelaySec=30s
Persistent=true
Unit=cs-flashcards-wiki-sync.service

[Install]
WantedBy=timers.target
EOF
else
  sudo systemctl disable --now cs-flashcards-wiki-sync.timer >/dev/null 2>&1 || true
  sudo rm -f /etc/systemd/system/cs-flashcards-wiki-sync.service /etc/systemd/system/cs-flashcards-wiki-sync.timer
  rm -f "$REMOTE_DIR/bin/sync_wiki_book.sh"
fi

sudo systemctl daemon-reload
if [[ -n "$WIKI_GITHUB_REPO" ]]; then
  sudo systemctl enable cs-flashcards-wiki-sync.timer >/dev/null
  sudo systemctl start cs-flashcards-wiki-sync.service
  sudo systemctl restart cs-flashcards-wiki-sync.timer
  sudo systemctl --no-pager --full status cs-flashcards-wiki-sync.timer | sed -n '1,12p'
fi
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
