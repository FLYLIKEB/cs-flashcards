---
name: cs-flashcards-deploy-guard
description: 이 cs_flashcards FastAPI 앱의 배포 안전 점검 워크플로입니다. Lightsail, Cloudflare Tunnel, cs.chamung.com 배포 전후에 /api/health, /api/cards, 테스트, Basic Auth, state/progress.sqlite 보존, 그리고 원격 DB 직접 SQL 반영 원칙을 확인해야 할 때 사용합니다.
---

# CS Flashcards Deploy Guard

Use this skill to prevent deployments from breaking the flashcard app or resetting study progress.

## Non-negotiable deploy invariants

- `state/progress.sqlite` and remote `/home/ubuntu/cs-flashcards/state/progress.sqlite` are state DBs containing runtime card content, question-bank data, and study progress; content deploys must not overwrite the remote file.
- Remote DB changes must run as direct SQL through `./scripts/remote_sqlite_sql.sh`; payload files, staged row-sync helpers, and whole-file replacement are prohibited.
- `data/CS_encyclopedia_300plus.csv` may be replaced during deploy, but existing `id` values must remain stable.
- Do not commit `.omx/*password*` or credentials.
- Use Basic Auth for public health/card checks when `CS_FLASHCARDS_PASSWORD` is set.

## Preflight workflow

1. Read `references/deploy-checklist.md`.
2. Run local preflight:
   ```bash
   python3 .codex/skills/cs-flashcards-deploy-guard/scripts/deploy_guard.py preflight
   ```
3. Run tests:
   ```bash
   .venv/bin/python -m unittest discover -s tests
   ```
4. If deploying manually, use the project script only after preflight passes:
   ```bash
   CS_FLASHCARDS_PASSWORD="..." ./scripts/deploy_lightsail_flashcards.sh
   ```
5. Verify local or remote health:
   ```bash
   python3 .codex/skills/cs-flashcards-deploy-guard/scripts/deploy_guard.py health --url http://127.0.0.1:8000
   python3 .codex/skills/cs-flashcards-deploy-guard/scripts/deploy_guard.py health --url https://cs.chamung.com --username cs --password "$CS_FLASHCARDS_PASSWORD"
   ```

## Report format

Report:

- preflight command and result;
- test command and result;
- health endpoint status;
- whether `progress_db_exists` is true;
- any skipped check and why.

Stop and fix before deploying if IDs are duplicated, tests fail, or health reports missing CSV/progress DB.
