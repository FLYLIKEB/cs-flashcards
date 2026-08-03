---
name: cs-study-analytics
description: 이 cs_flashcards 프로젝트의 학습 진행 분석과 복습 계획 워크플로입니다. data/CS_encyclopedia_300plus.csv와 state/progress.sqlite를 읽어 O/X/미학습 상태를 요약하고, 취약 카테고리·고중요도 카드·일일 집중 복습 큐를 만들되 카드 내용은 수정하지 않을 때 사용합니다.
---

# CS Study Analytics

Use this skill to analyze learning progress and make review plans.

## Rules

- Treat SQLite progress as user study data. Read it by default; modify it only when explicitly asked.
- Never infer study progress from CSV progress columns when `state/progress.sqlite` exists.
- Prioritize review by: `known_status=X`, high `review_count`, stale `last_reviewed`, `importance=상`, `difficulty=상`, and BOK appearance.
- Keep recommendations concrete: card IDs, terms, categories, and why they were selected.

## Workflow

1. Read `references/review-strategy.md`.
2. Generate analytics:
   ```bash
   python3 .codex/skills/cs-study-analytics/scripts/progress_report.py \
     --csv data/CS_encyclopedia_300plus.csv \
     --db state/progress.sqlite \
     --format markdown \
     --limit 30
   ```
3. If the DB does not exist, report a cold-start plan using CSV content only.
4. For a requested category, pass `--category`.
5. For machine-readable downstream use, pass `--format json`.

## Output expectations

Include:

- total cards and reviewed ratio;
- O/X/unreviewed counts;
- category weakness table;
- focused review queue with IDs and terms;
- one short next-study recommendation.
