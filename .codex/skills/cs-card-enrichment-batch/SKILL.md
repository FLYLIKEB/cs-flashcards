---
name: cs-card-enrichment-batch
description: 이 cs_flashcards 프로젝트의 대량 카드 내용 고도화 워크플로입니다. data/CS_encyclopedia_300plus.csv의 여러 플래시카드 정의와 상세설명을 카테고리 단위, JSONL 보강 파일, 독립 리뷰, CSV 반영 흐름으로 개선·재작성·검증·적용해야 할 때 사용하며 카드 ID와 학습 진행상태를 보존합니다.
---

# CS Card Enrichment Batch

Use this skill to run safe multi-card content enrichment for `data/CS_encyclopedia_300plus.csv`.

## Project invariants

- Treat `id` as a permanent key. Never renumber, reuse, or change existing `CS-xxx` IDs.
- Do not edit progress fields for content work: `known_status`, `last_reviewed`, `review_count`.
- Keep `definition` as one Korean sentence where possible.
- Keep `detailed_explanation` in this form: `의미: ... 활용: ...`.
- Prefer friendly, learner-facing explanations over compressed encyclopedia summaries: explain why the concept is needed, how it works, what limits or variants matter, and where it is used.
- Use only `상`, `중`, `하` for `importance` and `difficulty`.
- Set `bok_appeared` to `O` only when source evidence indicates Korean Bank/BOK appearance; otherwise leave blank.

## Fast workflow

1. Read `references/enrichment-rubric.md` before generating or judging content.
2. Inspect target rows from `data/CS_encyclopedia_300plus.csv`.
3. Export a JSONL workset when batching:
   ```bash
   python3 .codex/skills/cs-card-enrichment-batch/scripts/enrichment_workflow.py export \
     --csv data/CS_encyclopedia_300plus.csv \
     --category 데이터베이스 \
     --out .omx/enrichment/db_input.jsonl
   ```
4. Produce output JSONL with exactly one line per input row and keys:
   `id`, `definition`, `detailed_explanation`, `review_passed`, `review_notes`.
   Write `detailed_explanation` in the friendly study style from the rubric: a clear first explanation, a simple example when useful, core mechanism, limits/variants, and practical use/precautions.
5. Validate the output before applying:
   ```bash
   python3 .codex/skills/cs-card-enrichment-batch/scripts/enrichment_workflow.py validate \
     --csv data/CS_encyclopedia_300plus.csv \
     --input .omx/enrichment/db_input.jsonl \
     --output .omx/enrichment/db_output.jsonl
   ```
6. Apply only after validation passes:
   ```bash
   python3 .codex/skills/cs-card-enrichment-batch/scripts/enrichment_workflow.py apply \
     --csv data/CS_encyclopedia_300plus.csv \
     --output .omx/enrichment/db_output.jsonl
   ```
7. Run project tests after applying:
   ```bash
   .venv/bin/python -m unittest discover -s tests
   ```

## Review expectations

- Include a short review note for each batch under `.omx/enrichment/*_review.md` when the batch is large.
- Report changed ID count, validation command output, and remaining content risks.
- If an output is incomplete, repetitive, or fails structure checks, fix the JSONL rather than patching the CSV manually.
