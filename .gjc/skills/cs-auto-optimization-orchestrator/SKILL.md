---
name: cs-auto-optimization-orchestrator
description: cs_flashcards 저장소에서 감사 결과를 매 라운드 GitHub 이슈로 정규화하고, 이미 열린 최적화 이슈가 있으면 그 이슈부터 병렬 서브에이전트·워크트리·PR 흐름으로 처리한 뒤 다음 감사 라운드로 넘어가는 오케스트레이션 스킬입니다.
use_conditions: 저장소 전체 품질을 반복적으로 끌어올리는 자동 최적화 루프를 돌려야 하고, GitHub 이슈/PR/worktree 정리까지 포함한 운영 절차를 한 흐름으로 관리해야 할 때.
---

# CS Auto Optimization Orchestrator

Use this skill to run a repo-wide optimization loop that turns every audit pass into GitHub issues, reuses already-open issues as the execution backlog, and runs issue-scoped subagents in parallel without stepping on already-running work.

## Hard gates

- Never ignore an already-open optimization issue. If it is still valid and has no active PR/worktree attached, pull it into the current execution wave instead of waiting for it to disappear.
- Do not open a duplicate issue for the same concrete finding. Reuse the existing issue, refresh its body or comments with the latest audit evidence, and keep one issue per shippable unit.
- The readiness gate is blocked by active PRs, active review cycles, or conflicting issue worktrees/branches — not by the mere existence of reusable open issues.
- Every audit pass must persist its findings and translate accepted findings into GitHub issues before implementation delegation begins.
- Keep the main agent terse. Put detailed evidence in artifacts, issue bodies, PR bodies, and review comments instead of chat.
- Use separate backend and frontend tracks when both surfaces need work. Frontend review must include UI/UX polish candidates, not only correctness bugs.
- Every implementation track must be issue-scoped and must use its own worktree/branch, its own Korean PR title/body, and its own subagent lane.
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
4. Partition open issues into:
   - reusable backlog issues: still valid, no active PR/worktree, ready for execution now;
   - in-flight issues: already paired with an active PR, review cycle, or worktree and therefore not safe to duplicate;
   - stale or out-of-scope issues: not part of the current optimization wave.
5. If in-flight PR/worktree blockers exist, write a compact status artifact summarizing both the blockers and the reusable backlog. If reusable backlog issues exist with no blockers, skip the wait state and start issue execution immediately.

## Wait loop

A blocked repository is a polling state for active PR/worktree conflicts, not for reusable issue backlog.

1. Run the readiness check immediately when the skill starts.
2. If blockers remain, persist the latest blocker snapshot to `artifacts/auto-optimization-readiness.json`.
3. If reusable backlog issues exist and no conflicting PR/worktree blocks them, leave the wait state immediately and execute those issues first.
4. Otherwise stay alive in the background and re-run the readiness check repeatedly.
5. Keep repeating until the conflicting PR/review/worktree blockers clear.
6. The moment blockers clear, resume with the existing backlog. Run a fresh audit only after the reusable issue backlog is empty.

## Optimization round

Run this only when there is no conflicting PR/worktree blocker.

1. Audit the repository for concrete improvement candidates when the reusable issue backlog is empty, or when a fresh pass is needed after finishing the current backlog.
   - backend: correctness, safety, deploy/runtime risks, data integrity, test gaps, performance hot paths, maintainability.
   - frontend: UX friction, accessibility, state bugs, visual inconsistency, responsiveness, confusing flows.
2. Keep only candidates that are specific, verifiable, and worth shipping.
3. For every accepted finding from the current audit pass, open or reuse a GitHub issue.
   - Search existing open issues first.
   - If a matching issue already exists, update it with the new audit evidence instead of creating a duplicate.
   - Split backend and frontend issues unless one issue is truly cross-cutting and validation-coupled.
   - Use Korean issue titles.
   - Put acceptance criteria, verification notes, and audit evidence in the body.
4. Build the execution queue from:
   - reusable pre-existing open issues; and
   - newly created or refreshed issues from the current audit pass.
5. Create isolated worktrees and branches per queued issue.
6. Spawn bounded issue-based subagents in parallel, one per issue.
   - Backend issue work stays backend-scoped.
   - Frontend issue work must include UI/UX adjustments when justified by the audit evidence.
7. For each branch, verify the exact changed behavior with focused tests or scenario checks.
8. Open Korean PRs linked to the issues.
9. Run review lanes whenever a PR changes.
   - If the diff is not ready, leave a concrete review comment.
   - If the diff is clean, approve it.
10. Merge approved PRs.
11. After merge, delete the finished worktree/branch if safe and close the linked issue.
12. Re-run the readiness check.
13. If reusable backlog issues remain, start the next issue execution wave immediately.
14. If blockers remain again, return to the wait loop and keep polling in the background.
15. If the backlog is empty, run the next audit pass immediately.
16. If no worthwhile candidates remain, stop.

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
- no reusable open optimization issue, no open PR, and no leftover worktree from prior rounds remains;
- focused tests for the last accepted changes are green;
- further work would mostly be speculative polish rather than concrete improvement.

## Suggested artifacts

- `artifacts/auto-optimization-readiness.json`
- `artifacts/auto-optimization-audit-<round>.md`
- `artifacts/auto-optimization-issue-backlog.json`
- `artifacts/auto-optimization-merge-log.jsonl`

## Ultragoal persistence rule

When this skill runs under Ultragoal:

- do not let the run die just because conflicting PR/worktree blockers remain;
- do not treat the wait artifact as terminal success;
- do not complete the Ultragoal while reusable issue backlog, open PRs, or blocking worktrees still mean the next issue execution wave has not fully finished yet;
- keep the aggregate objective active and keep repeating the readiness-check → issue-execution → audit cycle until the 95% completion heuristic is truly satisfied;
- only then create the final completion checkpoint and reconcile the inline goal as complete.

## Self-realization rule

When this skill is invoked by the leader itself:

- run the readiness check immediately;
- if reusable issue backlog exists without blockers, execute that backlog before opening any new issue;
- if blocked by active PR/worktree conflicts, persist the wait evidence, stay in the background wait loop, and keep re-checking until the blockers clear;
- if the backlog is empty and the repo is unblocked, begin with audit → GitHub issue registration → issue-based subagent delegation.
