# Auto Optimization Audit 24

- Checked at: 2026-08-02T19:06:35Z
- Base: `origin/main` @ `f896474`
- Round: 35

## Frontend
### Accepted candidate
- Issue: #178 `카드 상태 토글 버튼에 선택 상태 접근성 노출 추가`
- Files:
  - `static/app.js`
  - `tests/test_frontend_browser.py`
- Evidence:
  - 카드 목록 상태 버튼과 문제 풀이 하단 상태 버튼은 `active` 클래스만 사용하고 pressed semantics 가 없음 (`static/app.js:154`, `6318-6320`).
  - 같은 파일의 다른 토글은 이미 `aria-pressed` 를 사용하고 있어 일관성 차이가 분명함 (`static/app.js:2949`, `3296`, `4560`, `7190`, `7197`).

## Backend
### Accepted candidate
- Issue: #179 `카드 상태 갱신 API summary 재조회 연결 축소`
- Files:
  - `app.py`
  - `tests/test_flashcards.py`
- Evidence:
  - `api_mark`, `api_bookmark`, `api_memo` 는 mutation helper 이후 `read_card_mutation_summary()` 를 별도 연결로 다시 호출함 (`app.py:9065-9092`).
  - helper 내부 reduced-connection 최적화는 이미 끝났지만, API 응답 summary 경로는 아직 전체 집계 재조회 비용이 남아 있음.
