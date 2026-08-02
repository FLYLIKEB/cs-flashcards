# Auto Optimization Audit 23

- Checked at: 2026-08-02T18:44:29Z
- Base: `origin/main` @ `0ea8b9d`
- Round: 34

## Frontend
### Accepted candidate
- Issue: #174 `메인 필터·기록 토글 버튼에 선택 상태 접근성 노출 추가`
- Files:
  - `static/app.js`
  - `tests/test_frontend_browser.py`
- Evidence:
  - 북마크 필터, 상태 필터, 문제 기록 필터 버튼은 `active` 클래스만 토글되고 pressed semantics 가 없음 (`static/app.js:3294-3296`, `4556-4558`, `7281-7283`).
  - 같은 파일의 다른 토글은 이미 `aria-pressed` 를 사용하고 있어 일관성 차이가 분명함 (`static/app.js:2948-2949`, `7186-7194`).

## Backend
### Accepted candidate
- Issue: #175 `카드 mark·bookmark·memo 단건 갱신 경로 SQLite 연결 재사용`
- Files:
  - `app.py`
  - `tests/test_flashcards.py`
- Evidence:
  - `mark_card()`, `set_bookmark()`, `save_memo()` 는 각각 단건 존재 확인 `read_card()` 이후 별도 write connection 을 열고, 완료 후 다시 `read_card()` 로 응답 카드를 재조회함 (`app.py:1983-2014`, `2031-2047`, `2055-2073`).
  - 관련 테스트는 전체 카드 materialization 방지만 고정하고 있고, reduced-connection regression 은 아직 없음 (`tests/test_flashcards.py`).
