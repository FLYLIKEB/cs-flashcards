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

## 학습 위키 문서 열기

- 헤더의 `위키` 버튼과 카드 뒷면 `출처 파일` 링크는 `/wiki` UI로 연결됩니다.
- 앱은 위키 문서를 아래 순서로 찾습니다.
  1. `CS_FLASHCARDS_WIKI_BOOK_DIR`
  2. 프로젝트 내부 `wiki_book/`
  3. 기존 로컬 개발 경로 `../wikidocs-ebook`
- Lightsail 배포 스크립트는 기본적으로 로컬 `../wikidocs-ebook`를 묶어서 서버의 `/home/ubuntu/cs-flashcards/wiki_book`으로 함께 배포합니다.
- `CS_FLASHCARDS_WIKI_GITHUB_REPO`가 설정되어 있으면 서버에 위키 자동 동기화 타이머도 같이 설치됩니다. 기본값은 5분 주기이며 `CS_FLASHCARDS_WIKI_SYNC_INTERVAL_MINUTES`로 조절할 수 있습니다.
- 따라서 위키 레포에 push만 해도 별도 앱 재배포 없이 `/home/ubuntu/cs-flashcards/wiki_book`가 자동 갱신됩니다.
- 다른 위치의 문서를 배포하려면 `CS_FLASHCARDS_WIKI_BOOK_SRC`를 지정합니다.
- 위키 마크다운의 `- [ ]` / `- [x]` 체크리스트는 `/wiki`에서 실제 체크박스로 렌더링됩니다.
- 체크를 누르면 배포된 `wiki_book` 마크다운이 바로 갱신됩니다.
- 문서 상단 `수정` 버튼으로 Markdown 원문을 직접 편집할 수 있고, 저장하면 배포된 `wiki_book`와 현재 문서 화면이 즉시 갱신됩니다.
- 체크 상태와 문서 수정을 GitHub에도 같이 반영하려면 서버 환경변수에 `CS_FLASHCARDS_WIKI_GITHUB_TOKEN`, `CS_FLASHCARDS_WIKI_GITHUB_REPO`(예: `owner/repo`), `CS_FLASHCARDS_WIKI_GITHUB_BRANCH`(기본 `main`)를 설정합니다. 위키가 저장소 하위 경로라면 `CS_FLASHCARDS_WIKI_GITHUB_PATH_PREFIX`도 함께 지정합니다.
- 위키 문서는 제목/출처 파일 기준으로 연결된 플래시카드를 찾아 `대표 카드` 버튼과 관련 카드 칩을 보여줍니다.
- 위키에서 카드를 열면 URL 쿼리로 해당 카드에 바로 점프합니다.


## 데이터 저장 구조

카드 콘텐츠와 학습 진행상태를 분리해서 관리합니다.

| 구분 | 저장 위치 | Git 관리 | 배포 시 덮어쓰기 | 용도 |
| --- | --- | --- | --- | --- |
| 카드 콘텐츠 | `data/CS_encyclopedia_300plus.csv` | O | O | 용어, 영어명, 카테고리, 요약, 상세설명, 관련개념, 시험포인트, 한국은행 출제 여부, 중요도, 난이도 |
| 학습 진행상태 | `state/progress.sqlite` | X | X | O/X, 마지막 학습 시각, 복습 횟수 |

앱은 `/api/cards`를 호출할 때 CSV의 카드 콘텐츠와 SQLite의 진행상태를 `id` 기준으로 합쳐서 내려줍니다. 따라서 설명/상세설명/AI 이미지처럼 운영 중 바뀌는 값은 `state/progress.sqlite` 오버레이가 우선하고, CSV를 다시 배포해도 기존 O/X 상태와 AI 수정 내용이 유지됩니다.


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

## 한국은행 기출 표시

한국은행 필기/면접 대비를 위해 `source_files`에 `한국은행`이 포함된 개념은 CSV의 `bok_appeared` 컬럼에 `O`로 표시합니다. 현재 UI는 해당 카드 앞면과 뒷면 상단에 `한은` 배지를 보여줍니다.

운영 규칙:

- 기존 한국은행 기출/면접 자료에서 확인된 개념이면 `bok_appeared`를 `O`로 둡니다.
- 해당하지 않으면 빈 값으로 둡니다.
- `source_files`에 한국은행 자료명을 추가하면 `bok_appeared`도 함께 확인합니다.
- 검색창에서 `한국은행`, `한은`, `BOK`로 검색하면 표시된 개념을 찾을 수 있습니다.

## 필터와 헤더 개수

상단 필터는 모두 동시에 적용됩니다.

| 필터 | 기준 |
| --- | --- |
| 검색창 | ID, 용어, 영어명, 카테고리, 설명, 상세설명, 관련개념, 시험포인트, 중요도, 난이도, 한국은행 표시 검색어 |
| 카테고리 | CSV의 `category` |
| 중요도 | CSV의 `importance` (`⭐⭐⭐`/`⭐⭐`/`⭐`) |
| 난이도 | CSV의 `difficulty` (`▲▲▲`/`▲▲`/`▲`) |
| 한은 | CSV의 `bok_appeared`가 `O`인지 여부 |
| O/X/미학습 | SQLite 진행상태의 `known_status` |

헤더의 `전체`, `O`, `X`, `-` 숫자는 전체 CSV 기준이 아니라 현재 적용된 필터 결과 기준으로 표시됩니다. 예를 들어 `한은 O`와 `⭐⭐⭐`를 같이 고르면, 헤더 숫자도 “한국은행 기출 표시가 있고 중요도 상인 카드들”만 대상으로 다시 계산됩니다.

## 중요도/난이도 컬럼

CSV에는 각 개념별 복습 우선순위를 돕기 위해 아래 콘텐츠 컬럼이 있습니다.

| 컬럼 | 값 | 의미 |
| --- | --- | --- |
| `bok_appeared` | `O` 또는 빈 값 | 기존 한국은행 필기/면접 자료의 `source_files`에 등장한 개념 여부 |
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
- 현재 UI는 카드 앞면과 뒷면 상단 배지에 중요도는 `⭐⭐⭐`/`⭐⭐`/`⭐`, 난이도는 `▲▲▲`/`▲▲`/`▲`처럼 표시합니다. 툴팁에는 원래 값인 `중요도 상`, `난이도 중`이 표시됩니다.

## 개념 이미지

각 카드 뒷면에는 `concept_image_url`, `concept_image_alt` 컬럼을 이용해 개념 이해용 이미지를 표시합니다. 기존처럼 CSV에 직접 넣은 원격 이미지 URL도 그대로 쓸 수 있고, 카드 이미지 오른쪽 위의 작은 `AI` 버튼으로 현재 카드 내용을 바탕으로 새 이미지를 바로 생성·저장할 수도 있습니다.

- 생성 중 이미지는 서버에서 처리되고, 완료되면 현재 화면 메시지와 브라우저 알림으로 알려줍니다.
- 저장된 최종 PNG는 서버 `state/ai_images/` 아래에 보관됩니다.
- 이미지 URL/alt와 AI가 바꾼 설명/상세/시험포인트는 CSV가 아니라 `state/progress.sqlite` 오버레이에 즉시 저장되므로 재배포나 서비스 재시작 뒤에도 유지됩니다.
- 프롬프트 입력 UI는 없고, 서버에 고정된 교육용 개념 이미지 프롬프트를 사용합니다.
- AI 이미지 생성에는 서버 환경변수 `OPENAI_API_KEY`가 필요합니다.


기존 배치 스크립트로 로컬 경로 이미지를 재생성해 CSV를 갱신하는 흐름도 계속 쓸 수 있습니다:

```bash
python3 scripts/generate_concept_images.py --write-csv
```

S3에 업로드하고 CSV를 원격 이미지 URL로 갱신:

```bash
CS_FLASHCARD_IMAGE_S3_BUCKET="버킷명" \
CS_FLASHCARD_IMAGE_S3_PREFIX="cs-flashcards/concepts" \
CS_FLASHCARD_IMAGE_PUBLIC_BASE_URL="https://이미지-도메인/선택경로" \
python3 scripts/generate_concept_images.py --write-csv
```

`CS_FLASHCARD_IMAGE_PUBLIC_BASE_URL`을 생략하면 스크립트는 `https://<bucket>.s3.<region>.amazonaws.com/<prefix>` 형식의 URL을 사용합니다. GitHub Actions 배포에서도 같은 이름의 secret/variable을 설정하면 배포 전 이미지 생성·S3 업로드·CSV URL 갱신을 자동 수행합니다.


## 문제 풀이 모드

햄버거 메뉴(☰)의 `문제 풀이`를 누르면 문제 풀이 박스가 열립니다. `모드`를 `한은`으로 바꾸면 기본값이 `전공필기 8 + 전공논술 1 / 150분`으로 고정되고, 세트 종료 전에는 정답·해설이 잠겨 실제 한국은행식 모의 풀이에 가깝게 쓸 수 있습니다. `생성` 버튼은 현재 검색·카테고리·중요도·난이도·한은·O/X·북마크 필터 결과를 기준으로 문제를 즉석 생성하고, `가져오기` 버튼은 NotebookLM이나 외부 AI가 만든 JSON 문제 세트를 붙여넣어 현재 카드와 매칭한 뒤 모의 세트로 불러옵니다. `문제은행` 버튼을 누르면 DB에 저장된 전체 문제 목록을 번호순 리스트로 열 수 있고, 문제/정답/키워드 검색과 `topic`, `field_name`, `issuer`, `difficulty`, `section`, `source_location` 필터를 함께 적용해 원하는 묶음만 바로 풀 수 있습니다. 제한 시간을 고르면 총 경과시간·문항 시간·남은 시간을 보면서 풀 수 있고, `종료` 버튼으로 현재 세트를 한 번에 저장합니다. `기록` 버튼으로 현재 필터 기준의 맞음/애매함/틀림/모름/미채점 기록을 모아볼 수 있습니다.

지원 유형:

| 유형 | 생성 기준 | 용도 |
| --- | --- | --- |
| 주관식 | `definition`을 보고 `term` 맞히기 | 개념명 회상 |
| 객관식 | 정답 카드 1개와 관련/동일 카테고리 오답 3개 | 빠른 확인 |
| 서술형 | `definition`, `detailed_explanation`, `exam_note` | 면접식 설명 연습 |
| 논술형 | 관련 개념 비교와 채점 포인트 포함 | 긴 답안 구조화 |

가져오기 형식은 JSON 배열 또는 `{"questions": [...]}` 객체입니다. 각 문항에는 최소 `question_type`, `prompt`, 그리고 현재 카드와 연결될 `card_id` 또는 `concept_term`/`term`이 필요합니다. 한은형 세트는 최상위 `session_mode: "bok"`와 문항별 `section`, `points`, `expected_time_minutes`, `answer_guide`를 함께 넣으면 화면과 기록에 그대로 반영됩니다. 이제 가져온 문제와 생성 문제는 모두 같은 SQLite DB 안의 `question_bank` 테이블에도 저장되며, 문제 본문/정답 외에 `topic`(예: 데이터베이스), `field_name`(예: 전산학술), `keywords`, `difficulty`, `issuer`, `source_location` 같은 출제 메타데이터를 함께 보존합니다. 문제 본문과 정답/해설은 Markdown 형식으로 저장되며, 이미지(`![](...)`), 표, 목록도 화면에서 그대로 렌더링됩니다. 예시는 다음과 같습니다.

```json
{
  "title": "한국은행 OS/DB 모의 세트 1",
  "session_mode": "bok",
  "time_limit_minutes": 150,
  "questions": [
    {
      "concept_term": "교착상태",
      "question_type": "subjective",
      "topic": "운영체제",
      "field_name": "전공필기",
      "keywords": ["교착상태", "상호배제", "환형대기"],
      "difficulty": "중",
      "issuer": "한국은행",
      "source_location": "2013년 학술파트 1",
      "section": "전공필기",
      "points": 10,
      "expected_time_minutes": 12,
      "answer_guide": "정의 → 발생 조건 → 예방/회피 차이 → 금융IT 적용 순으로 5~7문장",
      "prompt": "교착상태의 발생 조건을 설명하시오.",
      "body": "운영체제 관점에서 답하시오.\n\n![개념 그림](/static/favicon.svg)",
      "answer": "상호배제, 점유와 대기, 비선점, 환형대기가 모두 성립할 때 발생할 수 있다.",
      "rubric": ["상호배제", "점유와 대기", "비선점", "환형대기"]
    }
  ]
}
```

백엔드 API는 `/api/questions/generate`이며, 생성형 문제는 CSV 원본을 수정하지 않고 즉석 생성합니다. `/api/question-bank`는 문제은행 저장/조회용 엔드포인트로, 생성/가져오기 문제를 DB에 적재하거나 필터링 조회할 때 사용합니다. `AI 검색` 버튼은 선택한 문제 유형과 문제 수를 바탕으로 현재 필터된 카드 개념명 목록을 Google AI 검색 프롬프트로 열어 외부 AI 퀴즈 생성도 바로 요청할 수 있게 합니다. 객관식/주관식/서술형/논술형 모두 `정답/해설 보기` 뒤 `맞음 저장`/`애매함 저장`/`틀림 저장`/`모름 저장`으로 자가 채점할 수 있고, 오답노트를 남길 수 있으며, 문제 시도 이력은 같은 SQLite DB 안의 별도 테이블에 저장됩니다.

## 내용을 수정하고 반영하기

카드의 용어, 요약, 상세설명, 한국은행 출제 여부, 중요도, 난이도 같은 콘텐츠는 아래 CSV에 있습니다. O/X, 마지막 학습 시각, 복습 횟수는 SQLite 진행상태 DB에 따로 저장되므로 CSV를 수정/배포해도 학습 상태가 원복되지 않습니다.

```text
data/CS_encyclopedia_300plus.csv
```

수정 후 GitHub에 커밋/푸시하면 원격 사이트에 자동 반영됩니다. 배포 스크립트는 기존 원격 CSV에 남아 있던 진행상태와 AI 이미지 오버레이를 먼저 SQLite로 보존한 뒤 새 CSV를 반영합니다.
브라우저에서 바로 AI 초안을 만들려면 서버 환경변수에 `OPENAI_API_KEY`(또는 `CS_FLASHCARDS_OPENAI_API_KEY`)를 넣고, 필요하면 `CS_FLASHCARDS_CODEX_MODEL`로 모델명을 바꿉니다. 간단 설명·상세 설명·시험 포인트 옆의 작은 `AI` 버튼은 각 섹션을 바로 비동기로 생성·저장하고 완료 시 알림합니다. 개념 이미지도 같은 방식으로 바로 생성·저장하며, 최종 파일은 `state/ai_images/`, 오버레이 값은 `state/progress.sqlite`에 기록됩니다.


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
id,term,english,category,alphabet_index,korean_initial,definition,detailed_explanation,related_concepts,source_files,exam_note,bok_appeared,importance,difficulty,known_status,last_reviewed,review_count
CS-617,새 개념,New Concept,운영체제,#,ㅅ,요약...,의미: ... 활용: ...,"[[관련 개념]]",보강 개념(페이지 직접 언급 없음),시험 포인트...,,중,중,,,0
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

{
  "ok": true,
  "csv_exists": true,
  "progress_db_exists": true,
  "progress_db_path": "/home/ubuntu/cs-flashcards/state/progress.sqlite",
  "wiki_book_exists": true,
  "wiki_book_dir": "/home/ubuntu/cs-flashcards/wiki_book",
  "wiki_book_configured_dir": "/home/ubuntu/cs-flashcards/wiki_book",
  "wiki_checklist_sync_target": "github"
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
