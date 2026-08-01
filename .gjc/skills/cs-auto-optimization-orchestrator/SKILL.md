---
name: cs-auto-optimization-orchestrator
description: cs_flashcards 저장소에서 기존 병렬 이슈·워크트리·PR이 모두 정리된 뒤에만 새 최적화 라운드를 열고, 백엔드/프론트엔드 개선 이슈 생성 → 분리 워크트리 병렬 구현 → 변경 감지형 리뷰 → 승인 PR 머지·워크트리 삭제·이슈 종료를 반복하는 오케스트레이션 스킬입니다.
use_conditions: 저장소 전체 품질을 반복적으로 끌어올리는 자동 최적화 루프를 돌려야 하고, GitHub 이슈/PR/worktree 정리까지 포함한 운영 절차를 한 흐름으로 관리해야 할 때.
---

# CS Auto Optimization Orchestrator

Use this skill to run a repo-wide optimization loop without stepping on already-running work.

## Hard gates

- Never start a new optimization round while any GitHub issue is still open, any GitHub PR is still open, or any issue-train/worktree created for active issue work still exists.
- A blocked readiness check is not completion. It is a background wait state.
- When the gate is closed, record the blocking evidence first and keep waiting in the background. Do not create new issues, branches, worktrees, PRs, or review noise for the next round until the gate opens.
- Keep the main agent terse. Put detailed evidence in artifacts, issue bodies, PR bodies, and review comments instead of chat.
- Use separate backend and frontend tracks when both surfaces need work. Frontend review must include UI/UX polish candidates, not only correctness bugs.
- Every implementation track must use its own worktree/branch and its own Korean PR title/body.
- Review lanes are continuous: when a PR changes, re-check the diff and either leave a blocking review comment or approve it.
- Merge only after approval and passing verification. After merge, remove the finished worktree and close the linked issue.
- Stop the loop only when no meaningful backend or frontend optimization candidate remains and the repository appears at least 95% complete by current standards.

## Readiness check

1. Inspect GitHub open issues.
   ```bash
   gh issue list --state open --limit 100 --json number,title,state,labels,assignees,url
   ```
2. Inspect GitHub open PRs.
   ```bash
   gh pr list --state open --limit 100 --json number,title,headRefName,baseRefName,reviewDecision,mergeStateStatus,isDraft,url
   ```
3. Inspect local worktrees.
   ```bash
   git worktree list --porcelain
   ```
4. If any of the above show in-flight work, write a compact status artifact with the blocker summary and stay in the wait loop instead of treating the round as finished.

## Wait loop

A blocked repository is a polling state, not a terminal state.

1. Run the readiness check immediately when the skill starts.
2. If blockers remain, persist the latest blocker snapshot to `artifacts/auto-optimization-readiness.json`.
3. Stay alive in the background and re-run the readiness check repeatedly.
4. Keep repeating until there are zero blocking open issues, zero blocking open PRs, and zero blocking issue/wave worktrees.
5. The moment the gate opens, start the optimization round automatically without waiting for a new manual trigger.

## Optimization round

Run this only when the readiness check is clean.

1. Audit the repository for concrete improvement candidates.
   - backend: correctness, safety, deploy/runtime risks, data integrity, test gaps, performance hot paths, maintainability.
   - frontend: UX friction, accessibility, state bugs, visual inconsistency, responsiveness, confusing flows.
2. Keep only candidates that are specific, verifiable, and worth shipping.
3. Open GitHub issues for the accepted candidates.
   - Split backend and frontend issues unless one issue is truly cross-cutting and validation-coupled.
   - Use Korean issue titles.
   - Put acceptance criteria and verification notes in the body.
4. Create isolated worktrees and branches per issue.
5. Delegate bounded implementation per issue in parallel.
   - Backend issue work stays backend-scoped.
   - Frontend issue work must include UI/UX adjustments when justified by the audit evidence.
6. For each branch, verify the exact changed behavior with focused tests or scenario checks.
7. Open Korean PRs linked to the issues.
8. Run review lanes whenever a PR changes.
   - If the diff is not ready, leave a concrete review comment.
   - If the diff is clean, approve it.
9. Merge approved PRs.
10. After merge, delete the finished worktree/branch if safe and close the linked issue.
11. Re-run the readiness check.
12. If blockers remain again, return to the wait loop and keep polling in the background.
13. If the gate is still clean, start the next optimization round immediately.
14. If no worthwhile candidates remain, stop.

## Review lane contract

- Reviewer must inspect the actual diff, linked issue acceptance criteria, and focused verification evidence.
- Reviewer output must be one of:
  - block: precise defect/risk plus required fix.
  - approve: explicit approval with any optional follow-up noted separately.
- Do not rubber-stamp because tests passed.
- Do not approve stale diffs after new commits; review the latest head again.

## 95% completion heuristic

Treat the loop as done only when all are true:

- no open optimization-worthy backend defect or refactor candidate is found;
- no open optimization-worthy frontend/UI/UX candidate is found;
- no open PR or leftover worktree from prior rounds remains;
- focused tests for the last accepted changes are green;
- further work would mostly be speculative polish rather than concrete improvement.

## Suggested artifacts

- `artifacts/auto-optimization-readiness.json`
- `artifacts/auto-optimization-audit-<round>.md`
- `artifacts/auto-optimization-merge-log.jsonl`

## Ultragoal persistence rule

When this skill runs under Ultragoal:

- do not let the run die just because the readiness gate is blocked;
- do not treat the wait artifact as terminal success;
- do not complete the Ultragoal while open issues, open PRs, or blocking worktrees still mean the next optimization round has not started yet;
- keep the aggregate objective active and keep repeating the wait-loop → optimization-round cycle until the 95% completion heuristic is truly satisfied;
- only then create the final completion checkpoint and reconcile the inline goal as complete.

## Self-realization rule

When this skill is invoked by the leader itself:

- run the readiness check immediately;
- if blocked, persist the wait evidence, stay in the background wait loop, and keep re-checking until the gate opens;
- if unblocked, begin with issue creation before any implementation delegation.
