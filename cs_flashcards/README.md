# CS 개념 플래시카드

CS 개념 CSV를 카드로 학습하고, O/X 학습 상태를 CSV에 저장하는 웹앱입니다.

- CSV: `cs_flashcards/data/CS_encyclopedia_300plus.csv`
- 공개 URL: https://cs.chamung.com

## 로컬 실행

```bash
./cs_flashcards/scripts/run_flashcards.sh
```

브라우저 접속:

```text
http://127.0.0.1:8000
```

수동 실행이 필요하면:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r cs_flashcards/requirements.txt
uvicorn cs_flashcards.app:app --reload
```

## 원격 실행

현재 원격 운영은 Lightsail 서버 + Vercel HTTPS 프록시 구조입니다.

- 접속: https://cs.chamung.com
- 아이디: `cs`
- 비밀번호: `az980831`
- 원본 서버: `http://cs-origin.chamung.com`

원격 서버에 최신 파일을 배포하려면:

```bash
./cs_flashcards/scripts/deploy_lightsail_flashcards.sh
```

Vercel 프록시만 다시 배포하려면:

```bash
vercel --cwd cs_flashcards/vercel-proxy --prod --yes
```
