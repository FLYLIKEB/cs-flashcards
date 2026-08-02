# Auto Optimization Audit 25

- Checked at: 2026-08-02T19:55:22Z
- Base: `origin/main` @ `4b66bf8`
- Round: 36

## Frontend
### Accepted candidate
- Issue: #182 `메인 앱 임베드 문제은행의 동적 select 필터(field/category/issuer) deep-link·reload 복원 누락`
- Files:
  - `static/app.js`
  - `tests/test_frontend_browser.py`
- Evidence:
  - 임베드 문제은행 dynamic select 필터는 옵션 채우기 전에 URL 값을 대입해 first request와 reload에서 값이 탈락함.
  - standalone `/question-bank`는 같은 경로를 이미 보완했지만 임베드 경로는 회귀 테스트가 비어 있음.

## Backend
### Status
- Round 36 backend audit retry running.
