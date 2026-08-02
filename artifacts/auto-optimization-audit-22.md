# Auto Optimization Audit 22

- Checked at: 2026-08-02T18:19:41Z
- Base: `origin/main` @ `fc5e6a1`
- Round: 33

## Frontend
### Accepted candidate
- Issue: #170 `문제 풀이 선지·채점 버튼에 선택 상태 접근성 노출 추가`
- Files:
  - `static/app.js`
  - `tests/test_frontend_browser.py`
- Evidence:
  - 객관식 선지 버튼은 `selected`/`answer`/`selected-wrong` 시각 클래스만 바뀌고 접근성 상태는 노출하지 않음 (`static/app.js:6324-6336`).
  - 채점 결과 버튼도 `active` 클래스만 있고 pressed/selected semantics 가 없음 (`static/app.js:6388-6393`).
  - 현재 브라우저 테스트는 question frame 진입과 저장 흐름은 다루지만, 선지/채점 버튼의 활성 상태 자체는 고정하지 않음 (`tests/test_frontend_browser.py`).

## Backend
### Accepted candidate
- Issue: #171 `단건 카드 수정 helper의 중복 SQLite 연결 축소`
- Files:
  - `app.py`
  - `tests/test_flashcards.py`
- Evidence:
  - `update_card_content_fields()` 가 `ensure_progress_db()` → `sync_ai_image_files_to_db()` → `read_card()` → backup → write로 단건 수정 한 번에 여러 SQLite 연결을 연속 사용함 (`app.py:1914-1936`).
  - 이 helper 는 `update_card_ai_content()`, `update_card_concept_media()`, `apply_ai_concept_image()` 의 공통 hot path 라서 단건 카드 편집 전반에 영향을 줌 (`app.py:2345-2567`).
  - 관련 테스트는 이미 single-card helper 가 전체 카드 materialization 을 피하는지만 고정하고 있어, connection reuse regression 을 추가할 여지가 명확함 (`tests/test_flashcards.py:651-689`).
