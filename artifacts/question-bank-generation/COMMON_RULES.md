# 한국은행 추가 100문항 생성 공통 규칙

각 대주제 파일 하나만 수정한다.

## 목표
- 한국은행 필기 대비용 추가 문제를 만든다.
- 단순 암기형만 늘리지 말고 비교형, 판단형, 계산형, 추론형을 섞는다.
- 앱에 바로 넣을 수 있는 완성형 question_bank row 목록을 만든다.

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

## 값 규칙
- `field_name`: 항상 `한국은행 필기 보강 100제`
- `issuer`: 항상 `한국은행 대비 제작`
- `section`: 항상 `전공필기`
- `session_mode`: 항상 `practice`
- `category`: 기존 허용 카테고리 중 하나만 사용
  - `운영체제`
  - `데이터베이스`
  - `네트워크`
  - `보안`
  - `소프트웨어공학`
  - `자료구조·알고리즘`
  - `클라우드·분산시스템`
  - `인공지능·데이터`
  - `금융IT·신기술`
- `topic`: 대주제명 또는 더 구체적인 소주제명
- `keywords`: 짧은 명사구만 사용, 2~6개 권장
- `card_id`: `card_reference.json`에서 강한 일치가 있을 때만 연결하고, 애매하면 빈 문자열 유지
- `question_bank_id`: 파일의 topic slug를 넣어 일관되게 작성
  - 예: `qb-bokplus-os-001`, `qb-bokplus-db-001`

## 문제 유형 규칙
- `multiple_choice`
  - `choices` 4개 필수
  - `answer_index` 필수
  - `answer`는 정답 선지 텍스트만
  - `body`에는 풀이에 필요한 표/조건/코드/수치만 넣고, 번호 선지를 중복 기입하지 말 것
- `short` / `subjective`
  - `choices=[]`, `answer_index=null`
  - `answer`는 최종 정답만
  - `explanation`에는 이유/계산과정/비교 포인트를 넣을 것

## 한국은행형 보강 규칙
- 각 파일에서 최소 30%는 단순 정의형이 아닌 문제로 만든다.
- 가능하면 아래 유형을 섞는다.
  - 직접 계산: 페이지 교체, 서브넷, 스케줄링, SQL 결과, 시간복잡도, DP 점화식
  - 비교 판단: A vs B 차이, 상황에 따른 선택 기준
  - 응용 설명: 금융 시스템/운영 상황에서 어떤 기술을 써야 하는지
  - 코드/표 해석: 짧은 코드, 실행 순서, 로그/상태표
- 계산형은 `explanation`에 계산 근거를 분명히 적는다.

## 품질 규칙
- `prompt`는 깔끔한 문제 문장만
- `body`는 풀이에 필요한 정보만
- `answer`에는 `정답:` 같은 접두어 금지
- `explanation`은 answer 반복만 하지 말고 근거를 넣을 것
- 마크다운 아티팩트, placeholder, AI 메모 금지
- 같은 파일 내 문제끼리 중복 금지

## 출력 계약
- 각 topic 파일의 `entries` 배열만 채우거나 고친다.
- 유효한 JSON 유지.
- 다른 파일 수정 금지.