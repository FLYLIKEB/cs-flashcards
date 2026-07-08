# Project Agent Rules

## Remote sync default

- After completing any user-requested local code, data, or documentation change, validate it, commit the intended scope, and push it to the current `origin` branch by default.
- Do not include unrelated local/untracked files in the commit. Stage explicit paths only when the working tree contains unrelated changes.
- If the user explicitly says not to push, or if pushing is blocked by authentication/remote errors, report the blocker and the local commit/status clearly.
- For destructive, force-push, history-rewrite, or production-impacting operations, ask before proceeding.
