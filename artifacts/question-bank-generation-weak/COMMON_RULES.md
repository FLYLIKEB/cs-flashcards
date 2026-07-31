# 한국은행 취약분야 보강 60문항 공통 규칙

각 대주제 파일 하나만 수정한다.

## 목표
- 현재 문제은행에서 상대적으로 약한 분야를 보강한다.
- 한은 필기 스타일에 맞게 정의형만이 아니라 계산형, 비교형, 상황판단형을 충분히 섞는다.
- 앱에 바로 넣을 수 있는 완성형 question_bank row를 만든다.

## 공통 형식
각 항목은 아래 키를 모두 가진 JSON 객체여야 한다.
- `question_bank_id`
- `card_id`
- `question_type`
- `prompt`
- `body`
- `answer`
- `explanation`
- `rubric`
- `choices`
- `answer_index`
- `topic`
- `field_name`
- `category`
- `keywords`
- `difficulty`
- `issuer`
- `source_location`
- `section`
- `points`
- `expected_time_seconds`
- `answer_guide`
- `session_mode`

## 고정 값
- `field_name`: 항상 `한국은행 취약분야 보강 60제`
- `issuer`: 항상 `한국은행 대비 제작`
- `section`: 항상 `전공필기`
- `session_mode`: 항상 `practice`

## 허용 카테고리
- `컴퓨터구조`
- `클라우드·분산시스템`
- `프로그래밍 언어`
- `인공지능·데이터`
- `금융IT·신기술`

## 값 규칙
- `topic`은 해당 분야의 세부 소주제명까지 드러나게 구체적으로 적는다.
- `keywords`는 2~6개, 짧은 명사구만 사용한다.
- `card_id`는 `artifacts/question-bank-generation/card_reference.json` 기준으로 강한 일치가 있을 때만 연결하고, 애매하면 빈 문자열로 둔다.
- `question_bank_id`는 파일 slug를 반영해 일관되게 작성한다.
  - 예: `qb-bokweak-arch-001`, `qb-bokweak-cloud-001`

## 문제 유형 규칙
- `multiple_choice`
  - `choices` 4개 필수
  - `answer_index` 필수
  - `answer`는 정답 선지 텍스트만 넣는다.
  - `body`에는 풀이에 필요한 코드/표/로그/조건/수치만 넣는다.
- `short` / `subjective`
  - `choices=[]`, `answer_index=null`
  - `answer`에는 최종 정답만
  - `explanation`에는 계산 근거 또는 판단 이유를 분명히 적는다.

## 보강 방향
- 단순 암기형 비중을 낮춘다.
- 각 파일에서 최소 40%는 계산형, 추론형, 비교형, 시나리오형 중 하나여야 한다.
- 특히 다음을 우선한다.
  - 컴퓨터구조: 캐시, 파이프라인, CPI, 인터럽트/DMA, 메모리 계층
  - 클라우드·분산시스템: CAP, 샤딩/복제, HA, RPO/RTO, 배포 전략, 관측성
  - 프로그래밍 언어: 코드 읽기, 오버로딩/오버라이딩, 스코프, 예외 흐름, 재귀
  - 인공지능·데이터: confusion matrix, precision/recall/F1, 과적합, CV, 데이터 저장 전략
  - 금융IT·신기술: RTGS/DNS, CBDC, FDS, 대사, 계정계/정보계/채널계, BCP/DR

## 품질 규칙
- `prompt`는 깔끔한 문제 문장만
- `body`는 풀이에 필요한 정보만
- `answer`에 `정답:` 접두어 금지
- `explanation`은 answer 반복이 아니라 근거/계산과정을 포함
- placeholder, AI 메모, 중복 선지, 불필요한 마크다운 금지

## 출력 계약
- 각 topic 파일의 `entries` 배열만 채우거나 고친다.
- 유효한 JSON 유지.
- 다른 파일 수정 금지.