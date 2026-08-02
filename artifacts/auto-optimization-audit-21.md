# Auto Optimization Audit 21

- Checked at: 2026-08-02T17:59:39Z
- Base: `origin/main` @ `28d5772`
- Round: 32

## Backend
- Accepted candidates: none
- Reason: latest `app.py` / `tests/test_flashcards.py` audit did not surface a concrete, verifiable backend improvement that was not already addressed in rounds 29-31.

## Frontend
### Accepted candidate
- Issue: #168 `문제은행 뷰 전환·리뷰 필터 버튼에 토글 접근성 상태 추가`
- Files:
  - `static/question-bank.js`
  - `tests/test_frontend_browser.py`
- Evidence:
  - `renderPracticeToggle()` currently maps the practice/list view switch onto `aria-expanded` even though it is not opening a controlled region (`static/question-bank.js:793-800`).
  - Review filter buttons currently expose only the visual `is-active` class with no assistive-tech state (`static/question-bank.js:1111-1114`).
  - Existing browser coverage pins filter-region `aria-expanded` and row-trigger keyboard behavior, but does not assert toggle-state semantics for these controls (`tests/test_frontend_browser.py:1004-1037`, `1067-1160`).
- Why now:
  - The question-bank page has already accumulated keyboard/focus regressions tests; leaving these two control groups without explicit active-state semantics is a clear accessibility gap with a small, bounded fix.
- Focused verification:
  - `node --check static/question-bank.js`
  - `python -m unittest tests.test_frontend_browser.<focused question-bank toggle cases>`
