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
- Lightsail 배포 스크립트는 기본적으로 로컬 `../wikidocs-ebook`를 묶어서 서버의 `/home/ubuntu/cs-flashcards/wiki_book`으로 함께 배포합니다.
- `CS_FLASHCARDS_WIKI_GITHUB_REPO`가 설정되어 있으면 배포 스크립트가 로컬 위키 대신 해당 GitHub 브랜치 HEAD를 내려받아 서버 `wiki_book`에 반영하고, 서버에도 같은 `CS_FLASHCARDS_WIKI_GITHUB_TOKEN`을 주입해 `/wiki` 수정이 GitHub 원본에 바로 반영되게 합니다. 토큰이 없으면 배포를 중단합니다. 기본값은 5분 주기이며 `CS_FLASHCARDS_WIKI_SYNC_INTERVAL_MINUTES`로 조절할 수 있습니다.
- 따라서 위키 레포에 push만 해도 별도 앱 재배포 없이 `/home/ubuntu/cs-flashcards/wiki_book`가 자동 갱신되고, 서버에서 AI/수정 버튼으로 바꾼 내용도 다음 배포에 덮어써지지 않습니다.
- 다른 위치의 문서를 배포하려면 `CS_FLASHCARDS_WIKI_BOOK_SRC`를 지정합니다.
- 위키 마크다운의 `- [ ]` / `- [x]` 체크리스트는 `/wiki`에서 실제 체크박스로 렌더링됩니다.
- 체크를 누르면 배포된 `wiki_book` 마크다운이 바로 갱신됩니다.
- 문서 상단 `수정` 버튼으로 Markdown 원문을 직접 편집할 수 있고, 저장하면 배포된 `wiki_book`와 현재 문서 화면이 즉시 갱신됩니다.
- 체크 상태와 문서 수정을 GitHub에도 같이 반영하려면 서버 환경변수에 `CS_FLASHCARDS_WIKI_GITHUB_TOKEN`, `CS_FLASHCARDS_WIKI_GITHUB_REPO`(예: `owner/repo`), `CS_FLASHCARDS_WIKI_GITHUB_BRANCH`(기본 `main`)를 설정합니다. 위키가 저장소 하위 경로라면 `CS_FLASHCARDS_WIKI_GITHUB_PATH_PREFIX`도 함께 지정합니다.
- 위키 문서는 제목/출처 파일 기준으로 연결된 플래시카드를 찾아 `대표 카드` 버튼과 관련 카드 칩을 보여줍니다.
- 위키에서 카드를 열면 URL 쿼리로 해당 카드에 바로 점프합니다.


## 데이터 저장 구조

카드 콘텐츠와 학습 진행상태를 모두 SQLite 중심으로 관리합니다.

| 구분 | 저장 위치 | Git 관리 | 배포 시 덮어쓰기 | 용도 |
| --- | --- | --- | --- | --- |
| 카드 콘텐츠 | `state/progress.sqlite`의 `cards` 테이블 | O | O | 용어, 영어명, 카테고리, 요약, 상세설명, 관련개념, 시험포인트, 이미지 URL/alt, 한국은행 출제 여부, 중요도, 난이도 |
| 학습 진행상태 | `state/progress.sqlite`의 `card_progress` 테이블 | O | O | O/X, 마지막 학습 시각, 복습 횟수, 북마크, 메모, 문제풀이 기록 |

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
- 배포 시에는 `state/progress.sqlite`와 필요한 `state/ai_images/` 파일을 함께 반영해야 합니다.
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

수정 후 GitHub에 커밋/푸시하면 원격 사이트에 자동 반영됩니다. 배포 스크립트는 저장소의 `state/progress.sqlite`를 서버에 그대로 반영합니다.
브라우저에서 바로 AI 초안을 만들려면 서버 환경변수에 `OPENAI_API_KEY`(또는 `CS_FLASHCARDS_OPENAI_API_KEY`)를 넣고, 필요하면 `CS_FLASHCARDS_CODEX_MODEL`로 모델명을 바꿉니다. 간단 설명·상세 설명·시험 포인트 옆의 작은 `AI` 버튼은 각 섹션을 바로 비동기로 생성·저장하고 완료 시 알림합니다. 개념 이미지도 같은 방식으로 바로 생성·저장하며, 최종 파일은 `state/ai_images/`, 카드 내용은 SQLite `cards` 테이블에 기록됩니다. 위키 이미지 AI 재생성은 같은 OpenAI 설정을 쓰고, 원격까지 반영하려면 `CS_FLASHCARDS_WIKI_GITHUB_REPO`/`CS_FLASHCARDS_WIKI_GITHUB_TOKEN` 구성이 필요합니다. GIF/비디오/Mermaid/HTML 위젯은 카드 뒷면 `코드` 버튼으로 저장하며, 값은 `concept_media_type`, `concept_media_payload` 필드에 남습니다.



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

원격 배포 후 아래가 맞으면 정상입니다.

```bash
./scripts/remote_flashcards_api.sh /api/health
```

응답에 아래 값이 포함되어야 합니다.

```json
{
  "ok": true,
  "content_db_exists": true,
  "progress_db_exists": true,
  "progress_db_path": "/home/ubuntu/cs-flashcards/state/progress.sqlite",
  "wiki_book_exists": true,
  "wiki_book_dir": "/home/ubuntu/cs-flashcards/wiki_book",
  "wiki_book_configured_dir": "/home/ubuntu/cs-flashcards/wiki_book",
  "wiki_checklist_sync_target": "local 또는 github"
}
```

카드 수와 진행상태 요약은 아래 API에서 확인합니다.

```bash
./scripts/remote_flashcards_api.sh /api/cards
```

문제은행/런타임 DB를 건드렸다면 여기서 끝내면 안 됩니다.

- `state/progress.sqlite` 변경은 **GitHub push**와 **실서버 반영 확인**을 둘 다 끝내야 완료입니다.
- 일반 배포는 원격 `state/progress.sqlite`를 **보존**해야 하며, 코드 배포로 전체 DB 파일을 덮어쓰면 안 됩니다.
- DB 내용 수정은 변경한 row/field만 원격에 반영해야 합니다. 변경과 무관한 원격 데이터는 그대로 유지되어야 합니다.
- 같은 row/field를 누군가 원격에서 동시에 수정하면 마지막 반영이 이깁니다. 충돌 가능성이 있으면 먼저 원격 DB를 다시 pull 받아 기준을 맞춥니다.
- 배포 후에는 `/api/health`만 보지 말고, 변경한 레코드를 `/api/question-bank`, `/api/cards` 같은 인증된 API로 직접 조회해 값이 맞는지 확인합니다.
- 원격 DB가 비어 있거나 오래된 값이면 즉시 로컬의 정상 `state/progress.sqlite`를 서버로 복구하고 서비스를 재시작한 뒤 다시 검증합니다.
- 정말로 전체 DB 복구가 필요한 재해 복구 상황이 아니면 `CS_FLASHCARDS_FORCE_DB_REPLACE=1` 같은 전체 교체 경로를 사용하지 않습니다.

### 권장 SQLite 작업 순서

```bash
# 1) 작업 시작 전 live DB를 로컬로 당김
./scripts/pull_remote_sqlite.sh

# 2) 로컬에서 필요한 row만 수정
#    예: state/progress.sqlite 안의 question_bank / cards row 수정

# 3) 바뀐 row만 원격에 반영
./scripts/sync_remote_sqlite_rows.sh question_bank qb-011b1c688f53bb3974beb2e3
./scripts/sync_remote_sqlite_rows.sh cards CS-001

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
- [ ] DB 내용 변경 시 `./scripts/sync_remote_sqlite_rows.sh`로 바뀐 row/field만 반영하고, `./scripts/remote_flashcards_api.sh`로 결과를 확인한다.
- [ ] 배포 후 `/api/health`에서 `progress_db_exists: true`를 확인한다.
