# Ingestion Rules

## CSV categories

Use the existing category set unless a strong reason exists:

- 데이터베이스
- 운영체제
- 네트워크
- 자료구조·알고리즘
- 프로그래밍 언어
- 소프트웨어공학
- 컴퓨터구조
- 보안
- 클라우드·분산시스템
- 인공지능·데이터
- 금융IT·신기술

## Content fields

- `definition`: one Korean sentence with purpose/context/distinction.
- `detailed_explanation`: `의미:` section plus `활용:` section.
- `related_concepts`: use `[[개념]]` links when related terms exist or are being added.
- `source_files`: cite the source filename or concise source label.
- `exam_note`: explain the likely written/면접 comparison point.
- `importance`: `상`, `중`, or `하` based on finance/public-enterprise CS relevance.
- `difficulty`: `상`, `중`, or `하` based on explanation complexity.

## Duplicate policy

Prefer updating an existing card over adding a new one when:

- Korean term is identical;
- English term is identical;
- the new source only adds examples to an existing concept;
- the concept is a synonym or narrower wording without exam value.

Add a new row when:

- the concept has a distinct definition or exam comparison point;
- the source introduces a separate technology, algorithm, protocol, attack, metric, or architecture;
- merging would make an existing card too broad.
