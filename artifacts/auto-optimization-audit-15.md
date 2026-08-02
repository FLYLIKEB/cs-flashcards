# Auto Optimization Audit — Round 23

- Checked at: 2026-08-02T13:17:53Z onward
- Gate state at audit start: open
- Scope: `origin/main` after round 22 merges (`#127`, `#128`)

## Accepted backend candidate
- Issue: #129
- Title: 문제풀이 저장 경로를 백엔드 단일 구현으로 통합하고 API 회귀 테스트 추가
- Why: `app.py`의 `save_question_attempt(...)`가 복제 저장 구현을 유지해 재저장 경로에서 정의되지 않은 이름 참조와 `answered_at` 정규화 drift 위험이 있음. 현재 테스트는 앱/API 경로를 직접 잠그지 못함.
- Target files: `app.py`, `tests/test_flashcards.py`
- Focused verification plan:
  - `python3 -m py_compile app.py tests/test_flashcards.py`
  - `.venv/bin/python -m unittest tests.test_flashcards ...question_attempt...`

## Accepted frontend candidate
- Issue: #130
- Title: 문제은행 launch/review helper 중복 정의 제거
- Why: `static/question-bank.js`에 launch helper와 review renderer/binder 블록이 중복 정의되어 있어 마지막 정의가 앞 정의를 덮어쓰는 우연한 상태에 의존함. 다음 수정에서 동작 drift 위험이 큼.
- Target files: `static/question-bank.js`, `tests/test_frontend_browser.py`
- Focused verification plan:
  - `node --check static/question-bank.js`
  - `.venv/bin/python -m unittest tests.test_frontend_browser ...question_bank...`

## Rejected / deferred
- 카드 목록 read path 단일 SQL 집계화는 가치가 있지만 범위가 넓어 이번 라운드에서는 보류.
- question-bank/attempt read path의 `read_cards()` 전체 로드 제거도 후속 라운드 후보로 남김.
