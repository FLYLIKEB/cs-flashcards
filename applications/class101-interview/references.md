# 답변 참고 자료

경력 사실은 [최신 이력서](../park_jiwoo_resume.md), [클래스101 공고](../class101_backend_job_posting.md), [소재은행](../application_material_bank.md)을 대조했습니다. 서로 다른 기록은 최신 이력서를 우선했습니다.

아래 문서는 기술 설계 답변을 보완하는 자료이며, 해당 프로젝트에서 실제 사용한 버전이나 구현 방식의 증거는 아닙니다. 공식 문서 확인일: 2026-11-09.

| 문항 | 참고 문서 | 확인할 내용 |
| --- | --- | --- |
| 19 | [Hibernate 6.6 HQL](https://docs.hibernate.org/orm/6.6/querylanguage/html_single/) | 컬렉션 fetch join과 페이지네이션, 복수 to-many 조회의 결과 행 증가 |
| 19 | [MultipleBagFetchException](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/loader/MultipleBagFetchException.html) | 복수 bag 동시 fetch의 제약 |
| 23~28 | [MySQL 8.4 트랜잭션 격리 수준](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html) | 일반 snapshot read와 locking read의 구분 |
| 29 | [Spring @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html) | 프록시 내부 호출과 기본 롤백 규칙 |
| 31~34 | [Stripe 멱등 요청](https://docs.stripe.com/api/idempotent_requests) | 동일 키·다른 요청의 처리와 PG별 계약 확인 |
| 34 | [Stripe 오류 처리](https://docs.stripe.com/error-low-level) | 타임아웃과 미확정 결제 결과의 복구 |
| 35 | [Stripe Webhooks](https://docs.stripe.com/webhooks) | 서명 검증, 중복과 순서 역전 |
| 63~65 | [Spring Batch 핵심 개념](https://docs.spring.io/spring-batch/reference/domain.html) | ExecutionContext와 체크포인트, 외부 효과의 멱등성 |
| 68 | [AWS Transactional outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html) | DB·이벤트 이중 쓰기 문제와 소비자 중복 방지 |
| 71~77 | [Cloudflare Durable Objects 설계 원칙](https://developers.cloudflare.com/durable-objects/best-practices/rules-of-durable-objects/) | storage gate와 외부 비동기 I/O 사이 요청 교차 실행 |

Stripe의 동작은 공급자 사례입니다. 실제 도입한 PG의 멱등 키 범위·보존기간·오류·재시도 정책을 별도로 확인해야 합니다.
