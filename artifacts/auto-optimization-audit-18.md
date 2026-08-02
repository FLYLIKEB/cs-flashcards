# Auto Optimization Audit 18

- Checked `origin/main` after PR #138/#139 merge (`d03ecd5`).
- Accepted backend candidate: issue #140 `연결 카드 없는 문제은행 풀이가 빈 진행 행을 만들지 않도록 정리`
  - Evidence: `app.py` question-attempt persistence still had empty-card sentinel handling risk; legacy schema kept `question_attempts.card_id TEXT NOT NULL`.
  - Verification plan: focused `tests.test_flashcards` on linked/unlinked saves plus legacy schema migration.
- Accepted frontend candidate: issue #141 `문제은행 숨김 풀이 세트가 필터 변경 뒤 다른 문제로 보이는 상태 꼬임 수정`
  - Evidence: hidden practice session could survive in iframe while outer header/status/selection switched to the filtered row.
  - Verification plan: focused browser regression for hide → filter change → reopen, plus existing reload/session persistence checks.
- Deferred for later rounds
  - backend: question-bank upsert path still reloads full card dashboard data
  - frontend: embedded question-bank filter controls still need accessibility-name parity with the standalone page
