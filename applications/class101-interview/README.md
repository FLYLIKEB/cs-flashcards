# 클래스101 면접 질문 로컬 사이트

`questions.md`에 질문 원문 100개, `answers.md`에 질문별 답변 초안을 분야별로 정리했습니다. `index.html`을 브라우저로 직접 열거나, 저장소 루트에서 다음 명령으로 로컬 서버를 실행합니다.

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory applications/class101-interview
```

주소: <http://127.0.0.1:8765>

- 접힌 상태에서 질문을 읽고, 클릭하거나 키보드 Enter/Space로 답변을 펼칩니다.
- 분야별 바로가기, 모두 펼치기·접기, 질문 및 답변 Markdown 다운로드를 제공합니다.
- 답변 편집 원본은 `answers-01-30.md`, `answers-31-60.md`, `answers-61-100.md`입니다. 수정한 뒤 `python3 scripts/build_class101_interview.py`로 `index.html`과 통합 `answers.md`를 다시 생성합니다. 생성기는 10개 분야, 분야별 10문항, 1~100번 순서와 답변 누락·중복을 검증합니다.
- 답변은 최신 이력서와 소재은행에 근거한 면접 연습용 초안입니다. 실제 경험과 제안 설계를 구분했으며, 확인되지 않은 당시 설정·수치의 측정 방식·개인적 동기는 각 문항의 확인 메모와 대조해야 합니다.
- 기술 개념을 복습할 공식 문서는 [참고 자료](references.md)에 모았습니다.
- 별도 설치나 외부 네트워크 요청 없이 동작합니다.
