#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

DOMAIN="${CS_FLASHCARDS_DOMAIN:-cs.chamung.com}"
USERNAME="${CS_FLASHCARDS_USERNAME:-${CS_FLASHCARDS_PUBLIC_USERNAME:-cs}}"
PASSWORD_FILE="${CS_FLASHCARDS_PASSWORD_FILE:-$ROOT_DIR/.omx/cs_flashcards_public_password}"
PASSWORD="${CS_FLASHCARDS_PASSWORD:-}"

usage() {
  cat <<'EOF'
Usage: ./scripts/remote_flashcards_api.sh /api/health
       ./scripts/remote_flashcards_api.sh '/api/question-bank?query=리팩토링&limit=1'
       ./scripts/remote_flashcards_api.sh https://cs.chamung.com/api/cards
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -ne 1 ]]; then
  usage >&2
  exit 1
fi

if [[ -z "$PASSWORD" && -f "$PASSWORD_FILE" ]]; then
  PASSWORD="$(cat "$PASSWORD_FILE")"
fi

if [[ -z "$PASSWORD" ]]; then
  echo "CS_FLASHCARDS_PASSWORD 또는 $PASSWORD_FILE 이 필요합니다." >&2
  exit 1
fi

TARGET="$1"
if [[ "$TARGET" =~ ^https?:// ]]; then
  URL="$TARGET"
else
  URL="https://$DOMAIN${TARGET}"
fi

curl --fail-with-body --silent --show-error --user "$USERNAME:$PASSWORD" "$URL"
