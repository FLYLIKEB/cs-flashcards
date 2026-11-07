# CS 개념 플래시카드

SQLite `state/progress.sqlite`를 카드 콘텐츠와 학습 상태의 단일 저장소로 쓰는 웹앱입니다.

- 카드 콘텐츠/학습 DB: `state/progress.sqlite` 또는 배포 서버의 `/home/ubuntu/cs-flashcards/state/progress.sqlite`

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
- Lightsail 배포 스크립트는 로컬 `../wikidocs-ebook`를 위키 시드로만 묶어 전달하고, 서버의 `/home/ubuntu/cs-flashcards/wiki_book`가 이미 있으면 그대로 보존합니다. 즉 일반 기능 배포가 원격 위키를 덮어쓰지 않습니다.
- 서버 `wiki_book`가 없을 때만 로컬 시드로 최초 부트스트랩합니다. 다른 위치의 시드를 쓰려면 `CS_FLASHCARDS_WIKI_BOOK_SRC`를 지정합니다.
- 위키 마크다운의 `- [ ]` / `- [x]` 체크리스트는 `/wiki`에서 실제 체크박스로 렌더링됩니다.
- 체크를 누르면 서버의 `wiki_book` 마크다운이 바로 갱신됩니다.
- 문서 상단 `수정` 버튼으로 Markdown 원문을 직접 편집할 수 있고, 저장하면 서버의 `wiki_book`와 현재 문서 화면이 즉시 갱신됩니다.
- 위키 AI 이미지 재생성, 체크리스트 저장, 문서 저장도 모두 서버 로컬 위키만 기준으로 동작합니다. GitHub 내용과 비교하거나 GitHub 원본으로 서버 위키를 덮어쓰지 않습니다.
- GitHub는 자동 동기화 원본이 아니라 수동 보관처입니다. 서버 환경변수에 `CS_FLASHCARDS_WIKI_GITHUB_TOKEN`, `CS_FLASHCARDS_WIKI_GITHUB_REPO`(예: `owner/repo`), `CS_FLASHCARDS_WIKI_GITHUB_BRANCH`(기본 `main`)를 설정하면 `/wiki` 문서 하단 `GitHub 보관` 버튼으로 현재 서버 위키 스냅샷을 명시적으로 push할 수 있습니다. 위키가 저장소 하위 경로라면 `CS_FLASHCARDS_WIKI_GITHUB_PATH_PREFIX`도 함께 지정합니다.
- 위키 문서는 제목/출처 파일 기준으로 연결된 플래시카드를 찾아 `대표 카드` 버튼과 관련 카드 칩을 보여줍니다.
- 위키에서 카드를 열면 URL 쿼리로 해당 카드에 바로 점프합니다.


## 데이터 저장 구조

카드 콘텐츠와 학습 진행상태를 모두 SQLite 중심으로 관리합니다.

| 구분 | 저장 위치 | Git 관리 | 일반 배포 시 원격 DB 파일 덮어쓰기 | 용도 |
| --- | --- | --- | --- | --- |
| 카드 콘텐츠 | `state/progress.sqlite`의 `cards` 테이블 | O | X | 용어, 영어명, 카테고리, 요약, 상세설명, 관련개념, 시험포인트, 이미지 URL/alt, 한국은행 출제 여부, 중요도, 난이도 |
| 학습 진행상태 | `state/progress.sqlite`의 `card_progress` 테이블 | O | X | O/X, 마지막 학습 시각, 복습 횟수, 북마크, 메모, 문제풀이 기록 |


앱은 `/api/cards`를 호출할 때 SQLite의 `cards` 테이블을 카드 콘텐츠 정본(source of truth)으로 읽고, 같은 DB의 진행상태·문제풀이 통계를 합쳐 반환합니다. 예전 배포에서 `card_progress`에 남아 있던 AI 설명/이미지 오버레이는 서버 시작 시 `cards` 테이블로 자동 이관한 뒤 비웁니다.



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

한국은행 필기/면접 대비를 위해 `source_files`에 `한국은행`이 포함된 개념은 카드 콘텐츠의 `bok_appeared` 필드에 `O`로 표시합니다. 현재 UI는 해당 카드 앞면과 뒷면 상단에 `한은` 배지를 보여줍니다.


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
| 카테고리 | `cards` 테이블의 `category` |
| 중요도 | `cards` 테이블의 `importance` (`⭐⭐⭐`/`⭐⭐`/`⭐`) |
| 난이도 | `cards` 테이블의 `difficulty` (`▲▲▲`/`▲▲`/`▲`) |
| 한은 | `cards` 테이블의 `bok_appeared`가 `O`인지 여부 |
| O/X/미학습 | SQLite 진행상태의 `known_status` |

헤더의 `전체`, `O`, `X`, `-` 숫자는 전체 카드 기준이 아니라 현재 적용된 필터 결과 기준으로 표시됩니다. 예를 들어 `한은 O`와 `⭐⭐⭐`를 같이 고르면, 헤더 숫자도 “한국은행 기출 표시가 있고 중요도 상인 카드들”만 대상으로 다시 계산됩니다.

## 중요도/난이도 컬럼

`cards` 테이블에는 각 개념별 복습 우선순위를 돕기 위해 아래 콘텐츠 컬럼이 있습니다.

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

## 개념 이미지·동적 미디어

각 카드 뒷면에는 기본적으로 `concept_image_url`, `concept_image_alt` 컬럼을 이용해 개념 이해용 이미지를 표시합니다. 여기에 더해 `concept_media_type`, `concept_media_payload`를 채우면 같은 영역에서 GIF, 비디오, Mermaid 다이어그램, sandbox HTML 위젯까지 렌더링합니다.
- 브라우저 카드 뒷면의 `코드` 버튼으로 `image`/`gif`/`video` URL이나 `mermaid`/`html` 코드를 바로 저장할 수 있습니다.
- `html`은 메인 페이지에 직접 삽입하지 않고 sandbox iframe 안에서만 실행됩니다.
- 브라우저의 작은 `AI` 버튼으로 새 이미지를 만들면 결과는 SQLite `cards` 테이블에 기록되고, 최종 PNG는 서버 `state/ai_images/` 아래에 보관됩니다. AI가 저장한 이미지는 `concept_media_type=image`, `concept_media_payload=/api/ai-images/...`로도 함께 기록됩니다.
- 위키 문서의 각 이미지에도 작은 포맷 선택(`png`/`svg`/`gif`)과 `AI` 버튼이 붙습니다. 누르면 결과가 위키 원본 저장소 `assets/generated-wiki-ai/` 아래에 저장되고 현재 Markdown 이미지 링크도 함께 갱신됩니다. 옆의 작은 `✎` 버튼으로 포맷별 프롬프트를 수정·저장할 수 있고, 저장값은 브라우저 로컬에 유지됩니다.
- 위키의 각 `#`/`##`/`###` 제목에도 같은 방식의 작은 포맷 선택과 `AI` 버튼이 붙습니다. 해당 제목 아래 섹션 전체 내용을 문맥으로 사용해 새 이미지를 생성하고, 생성된 이미지는 해당 제목 바로 아래 Markdown에 자동 삽입됩니다.
- 개별 이미지/섹션 버튼과 문서 일괄 AI는 모두 비동기 작업 큐로 들어갑니다. 버튼을 누르면 즉시 요청 알림만 보이고, 백그라운드 완료 후 현재 문서가 자동 새로고침됩니다. 목차 체크박스로 여러 Markdown 문서를 골라 한 번에 일괄 생성할 수 있습니다.
- 생성 중 이미지는 서버에서 처리되고, 완료되면 현재 화면 메시지와 브라우저 알림으로 알려줍니다.
- 이미지 URL과 동적 미디어 설정은 모두 SQLite `cards` 테이블 정본을 직접 수정합니다.
- 일반 배포는 `state/progress.sqlite`와 `state/ai_images/`를 건드리지 않습니다. 런타임 데이터 반영은 배포와 분리해서 수행합니다.

- 프롬프트 입력 UI는 없고, 서버에 고정된 교육용 개념 이미지 프롬프트를 사용합니다.
- AI 이미지 생성에는 서버 환경변수 `OPENAI_API_KEY`가 필요합니다.


## 문제 풀이 모드

햄버거 메뉴(☰)의 `문제 풀이`를 누르면 문제 풀이 박스가 열립니다. `모드`를 `한은`으로 바꾸면 기본값이 `전공필기 8 + 전공논술 1 / 150분`으로 고정되고, 세트 종료 전에는 정답·해설이 잠겨 실제 한국은행식 모의 풀이에 가깝게 쓸 수 있습니다. `생성` 버튼은 현재 검색·카테고리·중요도·난이도·한은·O/X·북마크 필터 결과를 기준으로 문제를 즉석 생성하고, `가져오기` 버튼은 NotebookLM이나 외부 AI가 만든 JSON 문제 세트를 붙여넣어 현재 카드와 매칭한 뒤 모의 세트로 불러옵니다. `문제은행` 버튼을 누르면 DB에 저장된 전체 문제 목록을 번호순 리스트로 열 수 있고, 문제/정답/키워드 검색과 `category`, `topic`, `field_name`, `issuer`, `difficulty`, `section`, `source_location` 필터를 함께 적용해 원하는 묶음만 바로 풀 수 있습니다. 목록의 `키워드` 열에는 저장된 키워드를 `, ` 기준으로 표시하고, 카드와 연결되는 키워드는 눌러서 해당 카드로 바로 이동할 수 있습니다. 제한 시간을 고르면 총 경과시간·문항 시간·남은 시간을 보면서 풀 수 있고, `종료` 버튼으로 현재 세트를 한 번에 저장합니다. `기록` 버튼으로 현재 필터 기준의 맞음/애매함/틀림/모름/미채점 기록을 모아볼 수 있습니다.

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

백엔드 API는 `/api/questions/generate`이며, 생성형 문제는 현재 SQLite `cards` 테이블 콘텐츠를 기준으로 즉석 생성합니다. `/api/question-bank`는 문제은행 저장/조회용 엔드포인트로, 생성/가져오기 문제를 DB에 적재하거나 필터링 조회할 때 사용합니다. `AI 검색` 버튼은 선택한 문제 유형과 문제 수를 바탕으로 현재 필터된 카드 개념명 목록을 Google AI 검색 프롬프트로 열어 외부 AI 퀴즈 생성도 바로 요청할 수 있게 합니다. 객관식/주관식/서술형/논술형 모두 `정답/해설 보기` 뒤 `맞음 저장`/`애매함 저장`/`틀림 저장`/`모름 저장`으로 자가 채점할 수 있고, 오답노트를 남길 수 있으며, 문제 시도 이력은 같은 SQLite DB 안의 별도 테이블에 저장됩니다.


## 내용을 수정하고 반영하기

카드의 용어, 요약, 상세설명, 한국은행 출제 여부, 중요도, 난이도 같은 콘텐츠는 운영 중에는 SQLite `cards` 테이블에서만 읽습니다. `card_progress`는 학습 진행상태 전용입니다.

```text
state/progress.sqlite
```

#1
수정 후 GitHub에 커밋/푸시하면 원격 사이트 코드 배포가 자동으로 시작됩니다. 하지만 일반 배포는 원격 `state/progress.sqlite`를 절대 덮어쓰지 않으므로, DB 내용 변경은 GitHub push만으로 끝나지 않습니다. `state/progress.sqlite`는 로컬 작업용 상태 DB이며, 라이브 서버 반영은 직접 원격 SQL 실행으로만 처리합니다.
#2
- [ ] DB 내용 변경 시 `./scripts/remote_sqlite_sql.sh`로 필요한 SQL만 직접 실행하고, `./scripts/remote_flashcards_api.sh`로 결과를 확인한다.
- [ ] 배포 후 `/api/health`에서 `progress_db_exists: true`, `progress_db_readable: true`, `content_card_count > 0`를 확인한다.
브라우저에서 바로 AI 초안을 만들려면 서버 환경변수에 `OPENAI_API_KEY`(또는 `CS_FLASHCARDS_OPENAI_API_KEY`)를 넣고, 필요하면 `CS_FLASHCARDS_CODEX_MODEL`로 모델명을 바꿉니다. 간단 설명·상세 설명·시험 포인트 옆의 작은 `AI` 버튼은 각 섹션을 바로 비동기로 생성·저장하고 완료 시 알림합니다. 개념 이미지도 같은 방식으로 바로 생성·저장하며, 최종 파일은 `state/ai_images/`, 카드 내용은 SQLite `cards` 테이블에 기록됩니다. 위키 이미지 AI 재생성도 같은 OpenAI 설정만 있으면 서버 로컬 위키 기준으로 바로 반영됩니다. GitHub 보관이 필요할 때만 `CS_FLASHCARDS_WIKI_GITHUB_REPO`/`CS_FLASHCARDS_WIKI_GITHUB_TOKEN`을 추가로 설정합니다. GIF/비디오/Mermaid/HTML 위젯은 카드 뒷면 `코드` 버튼으로 저장하며, 값은 `concept_media_type`, `concept_media_payload` 필드에 남습니다.



```bash
git add .
git commit -m "Update flashcards"
git push
```

수동으로 즉시 서버에 반영해야 할 때만 아래 명령을 사용합니다.

```bash
CS_FLASHCARDS_PASSWORD="개인용비밀번호" ./scripts/deploy_lightsail_flashcards.sh
```

원격 DB를 바꿔야 할 때는 파일 업로드나 SQLite 파일 교체를 하지 말고, 필요한 `INSERT`/`UPDATE`/`DELETE` SQL만 직접 실행합니다.

```bash
./scripts/remote_sqlite_sql.sh <<'SQL'
UPDATE question_bank
SET difficulty = '중'
WHERE id = 'qb-sample-001';
SQL
```

## 개념 추가/수정/삭제 운영 규칙

### 새 개념 추가

런타임 카드 콘텐츠의 정본은 SQLite `cards` 테이블입니다. 새 개념을 추가하거나 삭제해야 할 때는 `state/progress.sqlite`의 관련 테이블을 직접 갱신합니다.

권장 사항:

- 새 개념은 마지막 번호 다음 `CS-xxx`를 사용합니다.
- `card_progress`의 `known_status`, `last_reviewed`, `review_count`는 콘텐츠 DB가 아니라 학습 진행상태이므로 직접 덮어쓰지 않습니다.
- 기존 개념의 `id`를 유지하면 O/X 상태와 북마크/메모도 그대로 유지됩니다.
- 개념을 삭제하면 SQLite에 남은 진행상태가 고아 데이터가 될 수 있으니, 필요하면 같은 `card_id`의 `card_progress`/`question_attempts`도 함께 정리합니다.

### 개념 ID 변경 또는 재사용 금지

가능하면 하지 말아야 합니다.

- `CS-001`을 `CS-700`으로 바꾸면 기존 O/X와 연결이 끊깁니다.
- 삭제한 `id`를 다른 개념에 재사용하면 예전 O/X가 새 개념에 잘못 붙을 수 있습니다.
- 대량 정리 시에도 `id`는 안정적인 영구 식별자로 취급합니다.

## 배포 후 확인 방법

원격 배포 후 아래가 맞으면 정상입니다. `state/progress.sqlite`가 없거나 `cards` 테이블이 비어 있으면 `/api/health`는 503으로 실패해야 합니다.

```bash
./scripts/remote_flashcards_api.sh /api/health
```

성공 응답에는 아래 값이 포함되어야 합니다.

```json
{
  "ok": true,
  "content_db_exists": true,
  "content_card_count": 1 이상,
  "progress_db_exists": true,
  "progress_db_readable": true,
  "progress_db_path": "/home/ubuntu/cs-flashcards/state/progress.sqlite",
  "wiki_book_exists": true,
  "wiki_book_dir": "/home/ubuntu/cs-flashcards/wiki_book",
  "wiki_book_configured_dir": "/home/ubuntu/cs-flashcards/wiki_book",
  "wiki_checklist_sync_target": "local",
  "wiki_archive_enabled": true 또는 false
}
```

카드 수와 진행상태 요약은 아래 API에서 확인합니다.

```bash
./scripts/remote_flashcards_api.sh /api/cards
```

문제은행/런타임 DB를 건드렸다면 여기서 끝내면 안 됩니다.

- `state/progress.sqlite` 변경은 **GitHub push**와 **실서버 반영 확인**을 둘 다 끝내야 완료입니다.
- 일반 배포는 원격 `state/progress.sqlite`를 **보존**해야 하며, 코드 배포로 전체 DB 파일을 덮어쓰는 경로는 제거되었습니다.
- DB 내용 수정은 변경한 row/field만 원격에 반영해야 합니다. 변경과 무관한 원격 데이터는 그대로 유지되어야 합니다.
- 같은 row/field를 누군가 원격에서 동시에 수정하면 마지막 반영이 이깁니다. 충돌 가능성이 있으면 먼저 원격 DB를 다시 pull 받아 기준을 맞춥니다.
- 원격 반영은 `./scripts/remote_sqlite_sql.sh`로 필요한 SQL만 직접 실행합니다. 파일 업로드, row payload 생성, SQLite 파일 교체는 금지됩니다.
- 배포 후에는 `/api/health`만 보지 말고, 변경한 레코드를 `/api/question-bank`, `/api/cards` 같은 인증된 API로 직접 조회해 값이 맞는지 확인합니다.
- 원격 DB가 비어 있거나 오래된 값이면 즉시 원인 범위의 레코드만 직접 SQL로 복구하고 서비스를 다시 검증합니다.
- 원격 DB 경로를 다른 파일로 바꾸는 옵션과 전체 파일 교체 경로는 모두 제거되었습니다.




### 권장 SQLite 작업 순서

```bash
# 1) 작업 시작 전 live DB를 로컬로 당김
./scripts/pull_remote_sqlite.sh

# 2) 로컬에서 필요한 row만 수정
#    예: state/progress.sqlite 안의 question_bank / cards row 수정

# 3) 필요한 SQL만 원격에 직접 실행
./scripts/remote_sqlite_sql.sh <<'SQL'
UPDATE question_bank
SET answer = '...', explanation = '...', answer_guide = '...'
WHERE id = 'qb-011b1c688f53bb3974beb2e3';

UPDATE cards
SET term = '...', definition = '...', detailed_explanation = '...'
WHERE card_id = 'CS-001';
SQL


# 4) 인증된 API로 실제 서비스 값을 확인
./scripts/remote_flashcards_api.sh '/api/question-bank?query=리팩토링&limit=1'
```

## O/X 원복 방지 체크리스트

콘텐츠를 수정하거나 개념을 추가하기 전후로 아래만 지키면 됩니다.

- [ ] 기존 개념의 `id`를 바꾸지 않는다.
- [ ] 삭제한 `id`를 새 개념에 재사용하지 않는다.
- [ ] 새 개념에는 새 `CS-xxx`를 부여한다.
- [ ] `card_progress`의 `known_status`, `last_reviewed`, `review_count`를 콘텐츠 수정용으로 직접 관리하지 않는다.
- [ ] 일반 배포로 원격 `state/progress.sqlite` 전체를 덮어쓰지 않는다.
- [ ] 작업 전에 `./scripts/pull_remote_sqlite.sh`로 live 기준본을 가져온다.
#1
수정 후 GitHub에 커밋/푸시하면 원격 사이트 코드 배포가 자동으로 시작됩니다. 하지만 일반 배포는 원격 `state/progress.sqlite`를 절대 덮어쓰지 않으므로, DB 내용 변경은 GitHub push만으로 끝나지 않습니다. `state/progress.sqlite`는 로컬 작업용 상태 DB이며, 라이브 서버 반영은 직접 원격 SQL 실행으로만 처리합니다.
#2
- [ ] DB 내용 변경 시 `./scripts/remote_sqlite_sql.sh`로 필요한 SQL만 직접 실행하고, `./scripts/remote_flashcards_api.sh`로 결과를 확인한다.
- [ ] 배포 후 `/api/health`에서 `progress_db_exists: true`, `progress_db_readable: true`, `content_card_count > 0`를 확인한다.

## 48시간 코테 훈련 · 30문제

로컬 앱 실행 후 `http://127.0.0.1:8000/coding`에 접속하거나 홈 메뉴의 **48시간 코테 훈련**을 선택합니다.

- Java 17 기준 자체 제작 알고리즘 30문제입니다. 1일차 기본 15문제, 2일차 응용 15문제이며 마지막 3문제는 힌트 없이 모의 면접처럼 풉니다. 실제 기업 기출이나 출제 예측 자료는 아닙니다.
- 기본 화면은 **보고 듣기**입니다. 큰 소개 영역 없이 현재 강의·예제·재생을 먼저 보여주며, 배속·반복·자동 넘김은 **재생 설정**에서 조절합니다. **집중 화면**은 목록과 학습 방식 전환을 숨기고 현재 강의만 남깁니다. 설정은 저장되며 **집중 끝내기**나 Esc로 돌아올 수 있습니다. 빈 화면에서 Space로 재생·일시정지할 수 있고, 입력 중에는 단축키가 동작하지 않습니다.
- 30문제마다 다섯 장면의 코드 기반 슬라이드와 한국어 음성 설명이 있습니다. **소리 켜고 재생**을 누르면 예제 진행·Java 핵심 코드·요약이 설명과 함께 이어집니다. 영상 파일이 아닌 웹 슬라이드이며, 음성은 실제 MP3 파일입니다.
- 모든 강의의 첫 장면은 입력·구할 결과·중요 조건을 쉬운 말로 읽는 **문제 소개**로 시작합니다. 소개 중에는 코드를 숨기고 설명을 가운데 크게 보여준 뒤 기존 풀이로 이어집니다. 재생 설정의 **문제 소개부터 듣기**로 다시 들을 수 있습니다. 새 소개는 로컬 Yuna 음성이며 기존 AI 풀이 음성은 보존합니다.
- 각 문제는 음성에 맞춰 값·포인터·연결·결과가 변하는 **애니메이션 풀이**로 보여줍니다. 재생 막대를 움직여 해당 장면을 되돌려 볼 수 있으며, 정지·배속·탐색 시 그림과 자막도 함께 맞춰집니다. 기기의 동작 줄이기 설정에서는 이동 대신 즉시 상태를 바꿉니다.
- 설명마다 **연결된 Java 코드와 줄 번호**를 함께 표시합니다. 재생·되감기·배속에 맞춰 현재 줄과 짧은 역할 설명이 바뀝니다. **전체 코드에서 보기**를 펼쳐도 같은 줄이 강조되며, 코드 창 안에서만 해당 위치를 따라갑니다. 코드 도움을 본 기록은 독립 풀이 완료와 구분됩니다.
- **재생 설정 → AI 목소리 미리 듣기**에서 첫 장면의 기존 Yuna 음성과 ElevenLabs Yun 샘플을 비교할 수 있습니다. 실제 웹 생성 MP3를 사용하며, 전환한 장면에는 음성 제공자를 표시합니다. 무료 한도에서 생성한 음원만 가져오며, 재생 중 외부 음성 API를 호출하지 않습니다.
- AI 음성 적용: **1~5번 ElevenLabs Yun**, **9~25번 CLOVA Dubbing 아라**. 6~8번·26~30번은 기존 Yuna입니다. 무료 생성 범위에서 전환했으며, 클로바는 프로젝트당 30분 제한으로 25번을 별도 프로젝트에 생성했습니다.
- **자막은 기본으로 켜져 있습니다.** 음성과 같은 뜻의 문장이 예제 아래에 나오며, 숫자·문자·코드는 `4`, `b`, `HashSet`처럼 원래 표기로 보여줍니다. 음성용 읽기와 표시용 문장을 따로 관리하고, 문장별 실제 음성 길이에 맞춰 자막이 바뀝니다. 일시정지·배속·다시 듣기에도 함께 움직입니다. 상단 **자막 켜짐/꺼짐** 버튼으로 전환하고, 설정은 이 브라우저에 저장됩니다.
- 이전/다음 장면, 이 장면 다시 듣기, 0.85~1.5배속, 자동 다음 장면 끄기를 지원합니다. 브라우저 탭·학습 방식·문제를 바꾸면 음성이 멈춥니다. 마지막 장면 위치는 저장되며 새로고침 후 자동으로 소리가 나지 않습니다. 기기 음량이 꺼져 있으면 소리를 들을 수 없습니다.
- 강의를 본 기록은 독립 풀이 완료와 다릅니다. 강의 도움을 받은 문제는 빈 코드로 재풀이한 뒤 완료할 수 있습니다. **직접 풀기**를 선택하면 기존의 **읽기 → 코드 쓰기 → 확인·설명** 흐름을 사용할 수 있습니다. 전체 30문제와 진행률은 접힌 목록에서 확인하며 단계는 자유롭게 오갈 수 있습니다.
- 집중 타이머는 선택 사항입니다. **시간 설정**에서 5·10·15분을 고르거나 숫자를 숨길 수 있습니다. 종료되어도 코드·단계는 유지되고 자동 제출하지 않습니다. 다시 시작하면 새 구간을 시작합니다. 권장 문제 풀이 시간과 집중 구간은 별개입니다.
- **다시 돌아왔을 때 할 일 한 줄**을 적고 **잠깐 쉬기**를 누르면 타이머가 멈춥니다. 새로고침해도 쉬는 상태와 작성 코드를 보존하며 **이어서 하기**를 누른 후 타이머는 수동으로 재개합니다. 힌트가 필요하면 하나씩 펼쳐보고, 다음 시도에 독립 풀이를 연습하세요.
- 문제마다 제약·입출력·예제·제공 테스트·3단계 힌트·Java 풀이·복잡도·설명 질문이 있습니다. 내 풀이를 작성한 후 **테스트 포함 Main.java 저장**을 누르고 JDK 17 이상에서 `javac -encoding UTF-8 Main.java && java Main`으로 실행하세요. 편집기에는 `class Solution`과 `static solve`를 작성하며 `java.util.*` import와 테스트 main은 다운로드 시 포함됩니다. 제공 테스트 통과는 전체 정답 보장이 아니므로 추가 경계값도 확인합니다.
- 브라우저에서는 코드를 실행하지 않습니다. 독립 풀이 완료는 테스트 실행과 설명 체크리스트를 마친 뒤 직접 기록합니다. 힌트나 해설을 본 시도는 완료 처리할 수 없으며 **빈 코드로 재풀이** 후 도움 없이 풀어야 합니다.
- 도움받거나 막힌 문제는 30분 뒤 추천 큐의 우선순위가 올라갑니다. 다음 날 남은 복습 문제부터 다시 풀어보세요.
- 코드·메모·체크리스트·타이머·학습 상태는 브라우저 `localStorage`에 저장합니다. SQLite 학습 DB와는 별도이며 기기 간 자동 동기화되지 않습니다. **학습 기록 백업 / 복원**으로 이동할 수 있습니다.
- Java 진행 기록은 `csCoding48:java:v1`에 저장합니다. 기존 Python 기록(`csCoding48:v1`)은 덮어쓰지 않으며, 이전 코드·메모·상태는 문제별 **이전 Python 풀이 기록**에서 확인할 수 있습니다. Java는 새 코드·새 완료 상태로 시작하고 메모는 이어받습니다. 백업에는 이전 Python 기록도 포함됩니다.
- 합계·누적 개수·경로 비용이 `int` 범위를 넘는 문제는 `long`을 사용합니다. 문제에 표시된 매개변수와 반환형을 유지하세요.

검증: `.venv/bin/python -m unittest tests.test_coding_practice`

### 강의 음성 다시 만들기

원고는 `static/coding-lessons.json`, 음성은 `static/coding-audio/`입니다. 기존 Yuna 음원을 다시 만들려면 macOS의 한국어 Yuna 음성과 FFmpeg가 있는 환경에서 다음 명령을 사용합니다. 이 명령으로 AI 음성 장면까지 재생성하면 해당 장면이 Yuna로 교체되므로 주의하세요. 웹으로 듣는 데는 이 도구들이 필요하지 않습니다.

```bash
.venv/bin/python scripts/render_coding_lesson_audio.py
# 특정 문제만 다시 생성
.venv/bin/python scripts/render_coding_lesson_audio.py --ids 1 --force
```

음성·슬라이드 검증: `.venv/bin/python -m unittest tests.test_coding_lessons`

AI 음원 가져오기 도구는 `scripts/import_coding_ai_audio.py`, `scripts/import_coding_eleven_lesson.py`, `scripts/import_coding_clova_zip.py`입니다. 기본값은 검증만 수행하며 `--apply`로 반영합니다. ElevenLabs는 원문과 일치하는 생성 기록의 문자 시작 시각을, CLOVA Dubbing은 문장별 MP3의 실제 PCM 길이를 사용해 표시용 자막을 연결합니다. 생성 기록과 다운로드 ZIP은 저장소에 포함하지 않습니다.

문제 소개 원고는 `static/coding-intros.json`입니다. `.venv/bin/python scripts/prepend_coding_intros.py`로 대상 확인 후 `--apply`로 음원·자막·애니메이션 연결을 함께 반영합니다. 이미 같은 소개가 있으면 다시 붙이지 않습니다.

강의를 재생하면 가사·드럼 없는 전자피아노와 패드 BGM이 기본 16%로 함께 재생됩니다. **재생 설정 → 잔잔한 피아노 BGM**에서 끄거나 크기를 조절할 수 있으며 설정은 기기에 저장됩니다. 강의 정지·버퍼링·탭 전환 때 함께 멈추며, 새로고침만으로 자동재생하지 않습니다. 외부 서비스 없이 직접 만든 60초 반복 연주 음원이며 `scripts/render_coding_ambience.py`로 재생성할 수 있습니다.

강의 화면은 따뜻한 회백색과 낮은 채도의 청록색을 사용합니다. 자막·소개·코드 설명 문장은 음성 시각에 맞춰 짧게 타이핑되며, **재생 설정 → 글자 타이핑**에서 끌 수 있습니다. 기기의 동작 줄이기 설정에서도 즉시 전체 문장을 표시합니다. 코드와 배열 값은 타이핑하지 않습니다. 큐·배열 등 도식의 배치는 공통 컴포넌트가 담당하며, 설명 라벨은 별도 영역에 배치합니다.
