# Auto Optimization Audit — Round 25

- Checked at: 2026-08-02T14:31:10Z onward
- Gate state at audit start: open
- Scope: latest `origin/main` after round 24 completion

## Accepted backend candidate
- Issue: #136
- Title: 문제은행 attempt 상태 판정을 is_correct fallback까지 일관화
- Why: question-bank 목록 경로와 attempts 조회 경로가 레거시 행의 상태 판정 규칙을 다르게 해 같은 시도가 한쪽에서는 미응시, 다른 쪽에서는 정답/오답처럼 보일 수 있다.
- Target files: `app.py`, `tests/test_flashcards.py`
- Focused verification plan:
  - `python3 -m py_compile app.py tests/test_flashcards.py`
  - `.venv/bin/python -m unittest tests.test_flashcards ...question_bank...`

## Accepted frontend candidate
- Issue: #137
- Title: 문제은행 row trigger를 버튼 semantics로 승격하고 키보드 접근성 고정
- Why: 전용 question-bank 페이지의 row trigger가 아직 inert div semantics에 의존하고 있어 Tab/Enter/Space 기반 접근성 계약이 비어 있다.
- Target files: `static/question-bank.js`, `tests/test_frontend_browser.py`
- Focused verification plan:
  - `node --check static/question-bank.js`
  - `.venv/bin/python -m unittest tests.test_frontend_browser ...question_bank...`

## Deferred candidates
- Backend: 문제은행 목록 조회를 인덱스 친화적으로 재구성하기
- Backend: 연결되지 않은 문제은행 시도에서 빈 `card_progress` 행 생성을 막기
- Frontend: 임베드 채점 업데이트에서 전체 테이블 재렌더 제거
