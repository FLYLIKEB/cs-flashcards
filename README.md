# CS 개념 플래시카드

CS 개념 CSV를 카드로 학습하고, O/X 학습 상태를 CSV에 저장하는 웹앱입니다.

- CSV: `cs_flashcards/data/CS_encyclopedia_300plus.csv`
- 공개 주소: https://cs.chamung.com

## 바로 사용하기

폰이나 다른 기기에서 공개 주소로 접속합니다.

```text
https://cs.chamung.com
```

로그인 정보는 README에 보관하지 않습니다. 개인용 계정 정보로 접속합니다.

## 내 Mac에서 실행하기

```bash
./cs_flashcards/scripts/run_flashcards.sh
```

실행 후 브라우저에서 엽니다.

```text
http://127.0.0.1:8000
```

## 내용을 수정하고 반영하기

카드 데이터는 아래 CSV에 있습니다.

```text
cs_flashcards/data/CS_encyclopedia_300plus.csv
```

수정 후 GitHub에 커밋/푸시하면 원격 사이트에 자동 반영됩니다.

```bash
git add .
git commit -m "Update flashcards"
git push
```

수동으로 즉시 서버에 반영해야 할 때만 아래 명령을 사용합니다.

```bash
CS_FLASHCARDS_PASSWORD="개인용비밀번호" ./cs_flashcards/scripts/deploy_lightsail_flashcards.sh
```
