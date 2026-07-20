---
name: cs-remote-ai-batch
description: 이 cs_flashcards 프로젝트의 원격 AI 일괄 변환 워크플로입니다. 공개 사이트의 카드들을 카테고리 단위로 조회해 간단 설명·상세 설명·시험 포인트·개념 이미지를 아직 AI 반영이 안 된 카드만 웨이브 병렬 호출로 생성·저장하고, 저장 결과가 CSV 정본과 이미지 파일에 반영됐는지 검증해야 할 때 사용합니다.
use_conditions: 운영 카드 여러 장의 설명이나 이미지를 한 번에 AI 변환해야 하거나, 특정 카테고리에서 아직 AI가 안 먹은 카드만 골라 원격 API로 저장해야 할 때.
---

# CS Remote AI Batch

Use this skill to batch-apply the flashcard app's remote AI rewrite and AI image workflows safely.

## Core invariants

- Treat `data/CS_encyclopedia_300plus.csv` as the baseline content source for "아직 AI가 안 먹은 카드" 판정에만 사용합니다.
- Treat remote `/api/cards` as the live merged view. 카드 콘텐츠는 CSV가 정본이고, `state/progress.sqlite`는 학습 진행상태만 덧씌웁니다.
- Never edit or commit `state/progress.sqlite`, `state/ai_images/`, `.omx/*password*`, API keys, or Basic Auth credentials.
- Use the public app endpoints with Basic Auth. The default username is `cs`; read the password from `.omx/cs_flashcards_public_password` unless the user gives another credential.
- Verify `/api/health` first. Stop if `ai_rewrite_enabled` is false or `progress_db_exists` is false.
- Run in waves of roughly 3-5 parallel cards. If 502/timeout appears, shrink the next wave or retry the remaining cards sequentially.
- For text fields, only auto-select cards whose remote value still exactly matches the local CSV baseline. For images, only auto-select cards whose live `concept_image_url` is not under `/api/ai-images/`.

## Field mapping

Use these endpoint patterns:

- Text preview: `POST /api/cards/{card_id}/ai-rewrite/preview`
- Text apply: `POST /api/cards/{card_id}/ai-rewrite/apply`
- Image preview: `POST /api/cards/{card_id}/ai-image/preview`
- Image apply: `POST /api/cards/{card_id}/ai-image/apply`
- Image discard on failed apply: `POST /api/cards/{card_id}/ai-image/discard`

Use the same rewrite instructions as the shipped UI:

- `definition`: `현재 카드의 간단 설명만 1~2문장으로 더 명확하고 면접 답변 친화적으로 다듬어 주세요. 다른 필드는 유지해 주세요.`
- `detailed_explanation`: `현재 카드의 상세 설명만 더 이해하기 쉽게 다듬어 주세요. 의미: 와 활용: 구조는 유지하고 다른 필드는 유지해 주세요.`
- `exam_note`: `현재 카드의 시험 포인트만 더 짧고 비교 포인트가 잘 보이게 다듬어 주세요. 다른 필드는 유지해 주세요.`

## Workflow

1. Read `README.md` sections describing `/api/cards`, AI image storage, CSV content persistence, and `state/progress.sqlite` progress persistence.
2. Fetch `/api/health` and `/api/cards` from the remote site with Basic Auth.
3. Load the local CSV and build the target set for the requested category and fields.
   - `definition`/`detailed_explanation`/`exam_note`: select only cards whose live remote field still equals the CSV field.
   - `image`: select only cards whose live `concept_image_url` does not start with `/api/ai-images/`.
4. Execute the target set in waves.
   - For text: preview, extract the requested field only, then apply that field only.
   - For image: preview, then apply with the returned `preview_name`.
   - If image apply fails after preview succeeds, call discard to remove the preview artifact.
5. After each wave, log successes and failures by card ID and term.
6. Retry only the failures. Prefer a smaller wave size or sequential retries after any 502.
7. Re-fetch `/api/cards` and verify the remaining target count is zero for the requested category and fields.

## Verification checklist

Report all of the following:

- target category and fields;
- total targeted card count;
- success count and retry count;
- any failed card IDs after final retry;
- final remaining count per field after re-fetch;
- whether the saved values are now reflected in the canonical content source (text differs from local baseline CSV, images are served from `/api/ai-images/`).

## When not to use this skill

- Do not use it for local CSV rewriting or content curation meant to be committed into the repository. Use the existing local enrichment workflow for that.
- Do not use it when the user wants manual per-card review before saving; the remote AI endpoints save directly.
- Do not use it when health says AI is disabled or persistence is broken; fix the server first.
