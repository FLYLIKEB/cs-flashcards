# Auto Optimization Audit 26

- Checked at: 2026-08-02T20:24:30Z
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
### Status
- Round 37 backend audit retry running.
