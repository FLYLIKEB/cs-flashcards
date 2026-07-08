# CS 개념 플래시카드

CS 개념 CSV를 카드로 학습하고, O/X 학습 상태는 별도 SQLite에 저장하는 웹앱입니다.

- 카드 콘텐츠 CSV: `data/CS_encyclopedia_300plus.csv`
- 학습 상태 DB: `state/progress.sqlite` 또는 배포 서버의 `/home/ubuntu/cs-flashcards/state/progress.sqlite`
- 공개 주소: https://cs.chamung.com

## 바로 사용하기

폰이나 다른 기기에서 공개 주소로 접속합니다.

```text
https://cs.chamung.com
```

로그인 정보는 README에 보관하지 않습니다. 개인용 계정 정보로 접속합니다.

## 내 Mac에서 실행하기

```bash
./scripts/run_flashcards.sh
```

실행 후 브라우저에서 엽니다.

```text
http://127.0.0.1:8000
```

## 데이터 저장 구조

카드 콘텐츠와 학습 진행상태를 분리해서 관리합니다.

| 구분 | 저장 위치 | Git 관리 | 배포 시 덮어쓰기 | 용도 |
| --- | --- | --- | --- | --- |
| 카드 콘텐츠 | `data/CS_encyclopedia_300plus.csv` | O | O | 용어, 영어명, 카테고리, 요약, 상세설명, 관련개념, 시험포인트, 중요도, 난이도 |
| 학습 진행상태 | `state/progress.sqlite` | X | X | O/X, 마지막 학습 시각, 복습 횟수 |

앱은 `/api/cards`를 호출할 때 CSV의 카드 콘텐츠와 SQLite의 진행상태를 `id` 기준으로 합쳐서 내려줍니다. 따라서 설명/상세설명을 수정하거나 CSV를 다시 배포해도 기존 O/X 상태는 유지됩니다.

진행상태 SQLite 테이블의 핵심 구조는 다음과 같습니다.

```sql
CREATE TABLE card_progress (
  card_id TEXT PRIMARY KEY,
  known_status TEXT NOT NULL DEFAULT '',
  last_reviewed TEXT NOT NULL DEFAULT '',
  review_count INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);
```


## 중요도/난이도 컬럼

CSV에는 각 개념별 복습 우선순위를 돕기 위해 아래 콘텐츠 컬럼이 있습니다.

| 컬럼 | 값 | 의미 |
| --- | --- | --- |
| `importance` | `상` / `중` / `하` | 금융공기업 CS 필기·면접에서의 출제 가능성, 기반성, 비교 설명 가치 |
| `difficulty` | `상` / `중` / `하` | 처음 학습할 때와 면접 답변으로 구조화할 때의 설명 난도 |

판정 기준:

- 중요도 `상`: 여러 영역의 기반이거나 자주 묻히는 핵심 개념. 예: 트랜잭션, 인덱스, 프로세스, TCP, 인증/인가, 시간 복잡도.
- 중요도 `중`: 실무·시험에 유용하지만 핵심 기반 개념보다는 보조/응용 성격인 개념.
- 중요도 `하`: 특정 맥락의 세부 개념이거나 출제 우선순위가 상대적으로 낮은 개념.
- 난이도 `상`: 내부 동작, 장애/복구, 동시성, 수식, 암호, 분산 합의, 알고리즘 분석처럼 설명 구조가 복잡한 개념.
- 난이도 `중`: 정의는 익숙하지만 비교, 장단점, 적용 조건까지 설명해야 하는 개념.
- 난이도 `하`: 정의와 대표 예시 중심으로 빠르게 이해 가능한 개념.

운영 규칙:

- 새 개념을 추가할 때 `importance`, `difficulty`도 함께 채웁니다.
- 값은 반드시 `상`, `중`, `하` 중 하나만 사용합니다.
- 중요도와 난이도는 독립입니다. 예를 들어 매우 중요하지만 난이도는 낮을 수 있고, 중요도는 중간이지만 난이도는 높을 수 있습니다.
- 현재 UI는 카드 앞면과 뒷면 상단 배지에 `중요 상`, `난이도 중`처럼 표시합니다.

## 내용을 수정하고 반영하기

카드의 용어, 요약, 상세설명, 중요도, 난이도 같은 콘텐츠는 아래 CSV에 있습니다. O/X, 마지막 학습 시각, 복습 횟수는 SQLite 진행상태 DB에 따로 저장되므로 CSV를 수정/배포해도 학습 상태가 원복되지 않습니다.

```text
data/CS_encyclopedia_300plus.csv
```

수정 후 GitHub에 커밋/푸시하면 원격 사이트에 자동 반영됩니다. 배포 스크립트는 기존 원격 CSV에 남아 있던 진행상태를 최초 1회 SQLite로 이관한 뒤 새 CSV를 반영합니다.

```bash
git add .
git commit -m "Update flashcards"
git push
```

수동으로 즉시 서버에 반영해야 할 때만 아래 명령을 사용합니다.

```bash
CS_FLASHCARDS_PASSWORD="개인용비밀번호" ./scripts/deploy_lightsail_flashcards.sh
```

## 개념 추가/수정/삭제 운영 규칙

### 새 개념 추가

CSV에 새 행을 추가하고, 기존에 사용하지 않은 새 `id`를 부여합니다.

```csv
id,term,english,category,alphabet_index,korean_initial,definition,detailed_explanation,related_concepts,source_files,exam_note,known_status,last_reviewed,review_count
CS-617,새 개념,New Concept,운영체제,#,ㅅ,요약...,의미: ... 활용: ...,"[[관련 개념]]",보강 개념(페이지 직접 언급 없음),시험 포인트..., , ,0
```

권장 사항:

- 새 개념은 마지막 번호 다음 `CS-xxx`를 사용합니다.
- 새 행의 `known_status`, `last_reviewed`, `review_count`는 비워 두거나 `review_count`만 `0`으로 둡니다.
- 원격 SQLite에 해당 `card_id`가 없으면 앱에서 자동으로 미학습 상태로 보입니다.
- 카드 순서나 카테고리는 자유롭게 바꿔도 됩니다. 진행상태는 행 번호가 아니라 `id`에 연결됩니다.

### 기존 개념 수정

기존 개념의 설명, 상세설명, 관련개념, 카테고리, 영어명은 수정해도 됩니다.

중요 규칙:

- 기존 개념의 `id`는 유지합니다.
- `id`를 유지하면 O/X 상태도 그대로 유지됩니다.
- 예: `CS-001`의 용어명이나 설명을 바꿔도 SQLite의 `CS-001` 진행상태가 계속 붙습니다.

### 개념 삭제

CSV에서 행을 삭제하면 화면/API에는 더 이상 보이지 않습니다.

주의 사항:

- SQLite에는 삭제된 `card_id`의 진행상태가 남을 수 있습니다.
- 남아 있어도 앱에는 표시되지 않으므로 일반 운영에는 문제가 없습니다.
- 나중에 필요하면 CSV에 없는 `card_id`를 SQLite에서 정리하는 별도 스크립트를 만들면 됩니다.

### 개념 ID 변경 또는 재사용 금지

가능하면 하지 말아야 합니다.

- `CS-001`을 `CS-700`으로 바꾸면 기존 O/X와 연결이 끊깁니다.
- 삭제한 `id`를 다른 개념에 재사용하면 예전 O/X가 새 개념에 잘못 붙을 수 있습니다.
- 대량 정리 시에도 `id`는 안정적인 영구 식별자로 취급합니다.

## 배포 후 확인 방법

원격 배포 후 아래가 맞으면 정상입니다.

```bash
curl --user "cs:비밀번호" https://cs.chamung.com/api/health
```

응답에 아래 값이 포함되어야 합니다.

```json
{
  "ok": true,
  "csv_exists": true,
  "progress_db_exists": true,
  "progress_db_path": "/home/ubuntu/cs-flashcards/state/progress.sqlite"
}
```

카드 수와 진행상태 요약은 아래 API에서 확인합니다.

```bash
curl --user "cs:비밀번호" https://cs.chamung.com/api/cards
```

## O/X 원복 방지 체크리스트

콘텐츠를 수정하거나 개념을 추가하기 전후로 아래만 지키면 됩니다.

- [ ] 기존 개념의 `id`를 바꾸지 않는다.
- [ ] 삭제한 `id`를 새 개념에 재사용하지 않는다.
- [ ] 새 개념에는 새 `CS-xxx`를 부여한다.
- [ ] CSV의 `known_status`, `last_reviewed`, `review_count`를 직접 관리하지 않는다.
- [ ] `state/progress.sqlite`는 Git에 커밋하지 않는다.
- [ ] 배포 후 `/api/health`에서 `progress_db_exists: true`를 확인한다.
