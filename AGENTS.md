# Project Agent Rules

## Remote sync default

- After completing any user-requested local code, data, or documentation change, validate it, commit the intended scope, and push it to the current `origin` branch by default.
- Do not include unrelated local/untracked files in the commit. Stage explicit paths only when the working tree contains unrelated changes.
- If the user explicitly says not to push, or if pushing is blocked by authentication/remote errors, report the blocker and the local commit/status clearly.
- For destructive, force-push, history-rewrite, or production-impacting operations, ask before proceeding.

## SQLite deployment rule

- Treat `state/progress.sqlite` changes as a two-step delivery: GitHub push and live server DB reflection are separate requirements.
- Ordinary deploys MUST preserve the live remote `state/progress.sqlite`; whole-file replacement paths are prohibited.
- Before intentional local SQLite edits, refresh the workspace copy from the live server with `./scripts/pull_remote_sqlite.sh` unless the task explicitly requires a different baseline.
- For intentional SQLite data changes, execute only targeted remote SQL statements directly against the live DB through `./scripts/remote_sqlite_sql.sh`; file upload, row-payload staging, and whole-file replacement are prohibited, and unrelated remote data MUST remain intact.
- Do not report SQLite work complete until the authenticated live service confirms the change through `./scripts/remote_flashcards_api.sh` plus a focused API spot-check for the affected rows/fields.
- If a deploy leaves the remote SQLite empty, stale, or inconsistent, restore a known-good DB immediately and keep working until the live checks pass.