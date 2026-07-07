#!/usr/bin/env bash
set -euo pipefail

# chamung.com은 현재 Vercel DNS를 사용합니다.
# 기본 고정주소는 cs.chamung.com 입니다.
HOSTNAME="${1:-cs.chamung.com}"
TUNNEL_NAME="${2:-cs-flashcards}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/setup_fixed_flashcards_tunnel.sh" "$HOSTNAME" "$TUNNEL_NAME"
