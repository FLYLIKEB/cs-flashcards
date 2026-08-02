# Auto Optimization Audit 26

- Checked at: 2026-08-02T20:50:02Z
- Base: `origin/main` @ `20d6637`
- Round: 37

## Frontend
### Accepted candidate
- Issue: #186 `헤더 메뉴의 북마크 필터 토글 후 포커스 복귀 누락`
- Files:
  - `static/app.js`
  - `tests/test_frontend_browser.py`
- Evidence:
  - 헤더 메뉴 내부 북마크 필터 토글은 메뉴를 닫지만 포커스 복구 경로를 타지 않는다.
  - 기존 테스트는 Escape 복귀와 pressed state만 확인해 숨겨진 메뉴 항목 포커스 잔류를 잡지 못한다.

## Backend
### Accepted candidate
- Issue: #187 `save_question_attempt 초기 스키마 보장에서 남아 있는 중복 SQLite 재연결 제거`
- Files:
  - `app.py`
  - `tests/test_flashcards.py`
- Evidence:
  - `save_question_attempt`가 스키마 보장과 실제 저장/응답 조회 사이에 별도 SQLite 연결을 다시 연다.
  - 저장 직후 카드 응답 재조회까지 같은 연결로 수렴 가능하고, 회귀 테스트도 그 연결 수를 직접 검증하도록 좁힐 수 있다.

## Closeout
- Merged PRs: #188, #189
- Round 37 gate reopened after merge cleanup.
