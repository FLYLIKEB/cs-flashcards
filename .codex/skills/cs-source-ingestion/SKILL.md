---
name: cs-source-ingestion
description: 이 cs_flashcards 프로젝트의 새 자료 카드화 워크플로입니다. CS 노트, 기출 자료, 면접 질문, 한국은행·금융공기업 자료, 마크다운·텍스트·PDF 추출물, 사용자가 제공한 용어를 중복 검사·다음 CS ID 배정·카테고리·중요도·난이도·bok_appeared 판정까지 포함해 data/CS_encyclopedia_300plus.csv에 추가할 안전한 후보 행으로 변환해야 할 때 사용합니다.
---

# CS Source Ingestion

Use this skill to add new cards from source material without corrupting existing content or progress.

## Safe ingestion rules

- Check duplicates before creating new rows. Match by Korean `term`, English `english`, and close semantic overlap.
- Assign new IDs after the current maximum `CS-xxx` in the CSV.
- Never reuse deleted or existing IDs.
- Fill all content columns required by the CSV.
- Leave progress columns empty except `review_count` may be `0`.
- Mark `bok_appeared=O` only when the source clearly indicates Korean Bank/BOK material.

## Workflow

1. Read `references/ingestion-rules.md`.
2. Inspect source material and existing CSV terms.
3. Draft candidate JSONL with keys:
   `term`, `english`, `category`, `definition`, `detailed_explanation`, `related_concepts`, `source_files`, `exam_note`, `bok_appeared`, `importance`, `difficulty`.
4. Validate and assign IDs:
   ```bash
   python3 .codex/skills/cs-source-ingestion/scripts/ingest_candidates.py validate \
     --csv data/CS_encyclopedia_300plus.csv \
     --candidates /path/to/candidates.jsonl
   ```
5. Append only after validation passes and the user asked to modify the CSV:
   ```bash
   python3 .codex/skills/cs-source-ingestion/scripts/ingest_candidates.py append \
     --csv data/CS_encyclopedia_300plus.csv \
     --candidates /path/to/candidates.jsonl
   ```
6. Run quality/deploy checks if available:
   ```bash
   python3 .codex/skills/cs-flashcards-deploy-guard/scripts/deploy_guard.py preflight
   .venv/bin/python -m unittest discover -s tests
   ```

## Output expectations

When proposing additions, list:

- candidate count;
- duplicate/near-duplicate findings;
- assigned IDs if appended;
- categories and high-importance/BOK counts;
- validation evidence.
