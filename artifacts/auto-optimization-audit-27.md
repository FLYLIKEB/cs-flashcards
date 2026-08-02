# Auto Optimization Audit 27

- Checked at: 2026-08-02T20:55:11Z
- Base: `origin/main` @ `a65d321`
- Round: 38

## Frontend
### Accepted candidate
- Issue: #190 `문제은행 전용 페이지 URL 동기화가 해시 딥링크를 지우지 않도록 수정`
- Files:
  - `static/question-bank.js`
  - `tests/test_frontend_browser.py`
- Evidence:
  - 전용 `/question-bank` 페이지의 `syncUrl()`이 `history.replaceState` 호출 시 `window.location.hash`를 보존하지 않아 첫 렌더/필터 변경 뒤 fragment가 사라진다.
  - 같은 앱의 `static/app.js` 내 유사 URL 동기화는 hash를 보존하고 있어 동작이 불일치한다.
  - 기존 브라우저 테스트는 search 파라미터 기반 딥링크만 검증해 fragment 소실 회귀를 잡지 못한다.

## Backend
### Accepted candidate
- Issue: #191 `읽기/풀이 요청마다 문제은행 전체 백필을 다시 돌리지 않기`
- Files:
  - `app.py`
  - `tests/test_flashcards.py`
- Evidence:
  - 여러 hot path가 `ensure_progress_db()`를 통해 이미 초기화된 DB에서도 `question_bank` 전체 difficulty/keyword 백필을 반복 실행한다.
  - 이 백필은 전역 스캔 비용이 커서 steady-state read/save 요청에 불필요한 SQLite 작업을 더한다.
  - 현재 테스트는 connection 재사용만 검증하고, 반복 호출에서 전역 백필이 다시 돌지 않는 계약은 지키지 못한다.
