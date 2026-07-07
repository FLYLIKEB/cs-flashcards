# CS 개념 플래시카드

CSV 기반 CS 개념 플래시카드 웹앱입니다.

- GitHub 저장소: https://github.com/FLYLIKEB/cs-flashcards 카드 원본과 O/X 학습 상태는 `cs_flashcards/data/CS_encyclopedia_300plus.csv`에 저장됩니다.

## 폴더 구조

```text
cs_flashcards/
├── app.py                           # FastAPI 앱
├── data/CS_encyclopedia_300plus.csv # 카드 원본/학습상태 CSV
├── static/                          # HTML/CSS/JS UI
├── scripts/                         # 로컬/공개/배포 스크립트
├── vercel-proxy/                    # cs.chamung.com HTTPS 프록시 설정
└── backups/                         # O/X 저장 전 CSV 백업
```

## 로컬 실행

가장 간단한 실행:

```bash
./cs_flashcards/scripts/run_flashcards.sh
```

수동 실행:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r cs_flashcards/requirements.txt
uvicorn cs_flashcards.app:app --reload
```

접속:

```text
http://127.0.0.1:8000
```

## 주요 기능

- CSV row 1개 = 카드 1장
- 카드 클릭 또는 `Space`로 앞/뒤 뒤집기
- `O` / `X` 버튼 또는 키보드로 안다/모른다 체크
- 체크 시 CSV에 `known_status`, `last_reviewed`, `review_count` 기록
- 저장 전 `cs_flashcards/backups/`에 CSV 자동 백업
- 검색, 카테고리 필터, X/O/미학습 필터
- 자동 듣기, 재생 속도, 현재 단어 강조
- 관련 개념 클릭 시 해당 카드로 이동

## iPhone/외부 임시 접속: Cloudflare Tunnel

같은 Wi‑Fi가 아니어도 폰에서 임시 주소로 접속하려면:

```bash
./cs_flashcards/scripts/run_public_flashcards.sh
```

- 로컬 FastAPI 서버를 비밀번호 보호 상태로 실행합니다.
- Cloudflare Tunnel 임시 공개 주소(`https://...trycloudflare.com`)를 생성합니다.
- O/X 체크 결과는 `cs_flashcards/data/CS_encyclopedia_300plus.csv`에 저장됩니다.
- 기본 아이디는 `cs`입니다.
- 비밀번호는 처음 실행 시 `.omx/cs_flashcards_public_password`에 저장됩니다.

직접 지정:

```bash
CS_FLASHCARDS_USERNAME=cs CS_FLASHCARDS_PASSWORD='원하는비밀번호' ./cs_flashcards/scripts/run_public_flashcards.sh
```

## Cloudflare 고정주소 설정

Cloudflare DNS가 관리하는 도메인을 사용할 때만 아래 방식을 사용합니다.

```bash
./cs_flashcards/scripts/setup_fixed_flashcards_tunnel.sh cards.your-domain.com
./cs_flashcards/scripts/run_public_flashcards.sh
```

고정주소 설정을 지우고 임시 주소로 돌아가려면:

```bash
rm .omx/cs_flashcards_tunnel.env
```

## 휴대폰 고정 공개 접속: Lightsail + Vercel HTTPS 프록시

현재 최종 공개 구성은 Cloudflare가 아니라 **Lightsail + Vercel HTTPS 프록시**입니다.
앱과 CSV 저장은 기존 Lightsail 서버에서 처리하고, `cs.chamung.com` HTTPS 접속만 Vercel이 프록시합니다.

- 공개 주소: `https://cs.chamung.com`
- 로그인: `cs` / `az980831`
- 원본 주소: `http://cs-origin.chamung.com` -> Lightsail `3.39.48.139`
- 서버 경로: `/home/ubuntu/cs-flashcards`
- systemd 서비스: `cs-flashcards`
- 서버 CSV: `/home/ubuntu/cs-flashcards/cs_flashcards/data/CS_encyclopedia_300plus.csv`

Lightsail 앱 재배포:

```bash
./cs_flashcards/scripts/deploy_lightsail_flashcards.sh
```

Vercel HTTPS 프록시 재배포:

```bash
vercel --cwd cs_flashcards/vercel-proxy --prod --yes
```

DNS는 `cs.chamung.com -> Vercel(A 76.76.21.21)`, `cs-origin.chamung.com -> Lightsail(A 3.39.48.139)` 구조입니다. 두 레코드를 분리해야 프록시 루프가 생기지 않습니다.

## 다른 CSV로 실행

```bash
CS_FLASHCARD_CSV=/path/to/file.csv uvicorn cs_flashcards.app:app --reload
```
