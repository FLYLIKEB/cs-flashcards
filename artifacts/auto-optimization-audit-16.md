# Auto Optimization Audit — Round 24

- Checked at: 2026-08-02T13:37:10Z onward
- Gate state at audit start: open
- Scope: latest `origin/main` after round 23 completion

## Accepted backend candidate
- Issue: #132
- Title: 문제은행 풀이 저장 시 question_bank_id와 card_id 무결성 강제
- Why: linked question-bank attempt 저장에서 요청 `card_id`와 실제 연결 카드의 불일치가 검증되지 않아 잘못된 카드 통계 오염 위험이 있다.
- Target files: `app.py`, `tests/test_flashcards.py`
- Focused verification plan:
  - `python3 -m py_compile app.py tests/test_flashcards.py`
  - `.venv/bin/python -m unittest tests.test_flashcards ...question_attempt...`

## Accepted frontend candidate
- Issue: #133
- Title: 문제은행 뒤로가기/앞으로가기 복귀 시 열린 풀이 세트 복원
- Why: reload 복원 계약은 있지만 back/forward 복귀에서 열린 practice pane/iframe 복원이 충분히 고정돼 있지 않다.
- Target files: `static/question-bank.js`, `tests/test_frontend_browser.py`
- Focused verification plan:
  - `node --check static/question-bank.js`
  - `.venv/bin/python -m unittest tests.test_frontend_browser ...question_bank...`

## Deferred candidates
- Backend: 문제은행/카드 최신 풀이 조회용 SQLite 복합 인덱스 추가
- Backend: 문제은행 저장·수정 경로에서 전체 카드 카탈로그 로딩 제거
- Frontend: 질문은행 row trigger를 실제 버튼으로 승격하고 키보드 커버리지 추가
- Frontend: 임베드 채점 업데이트에서 전체 테이블 재렌더 제거
