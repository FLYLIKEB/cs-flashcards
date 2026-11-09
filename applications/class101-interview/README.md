# 클래스101 면접 질문 로컬 사이트

`questions.md`에 질문 원문 100개를 분야별로 정리했습니다. `index.html`을 브라우저로 직접 열거나, 저장소 루트에서 다음 명령으로 로컬 서버를 실행합니다.

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory applications/class101-interview
```

주소: <http://127.0.0.1:8765>

- 각 질문을 클릭하거나 키보드 Enter/Space로 펼치고 접습니다.
- 분야별 바로가기, 모두 펼치기·접기, Markdown 다운로드를 제공합니다.
- 원문을 수정한 뒤 `python3 scripts/build_class101_interview.py`로 페이지를 다시 생성합니다. 생성기는 10개 분야, 분야별 10문항, 1~100번 순서를 검증합니다.
- 별도 설치나 외부 네트워크 요청 없이 동작합니다.
