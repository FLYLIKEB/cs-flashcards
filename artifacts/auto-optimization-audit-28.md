# Auto Optimization Audit 28

- Checked at: 2026-08-02T21:13:44Z
- Base: `origin/main` @ `a56c19f`
- Round: 39

## Backend
### Accepted candidate
- Issue: #194 `카드별 문제 시도 히스토리 조회에 복합 인덱스가 없어 누적 데이터에서 정렬 비용이 커짐`
- Files:
  - `app.py`
  - `tests/test_flashcards.py`
- Evidence:
  - 카드별 문제 시도 히스토리 조회와 최신 오답 메모 조회가 모두 `card_id` 필터 뒤에 최신순 정렬 패턴을 반복한다.
  - 현재는 `question_bank_id` 쪽 최신순 복합 인덱스만 있고 카드 히스토리 쪽에는 대응 인덱스가 없다.
  - 관련 회귀 테스트도 카드용 복합 인덱스 계약은 잠그지 못한다.

## Frontend
### Accepted candidate
- Issue: #195 `접힌 듣기 설정 패널이 키보드 포커스와 스크린리더에서 숨겨지지 않음`
- Files:
  - `static/app.js`
  - `static/index.html`
  - `tests/test_frontend_browser.py`
- Evidence:
  - 듣기 설정 패널 collapse는 시각적 상태와 `aria-expanded`만 바꾸고 DOM 수준 숨김을 하지 않아, 접힌 뒤에도 상세 컨트롤이 탭 순서와 접근성 트리에 남는다.
  - 같은 화면의 다른 패널은 `hidden` 기반 실제 숨김을 써서 동작이 불일치한다.
  - 메인 controls collapse에 대한 접근성/포커스 회귀 테스트도 현재 비어 있다.
