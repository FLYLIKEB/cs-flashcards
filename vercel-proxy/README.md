# CS Flashcards Vercel HTTPS Proxy

`https://cs.chamung.com`을 Vercel HTTPS로 받고, 실제 FastAPI/CSV 저장은 Lightsail 원본 `http://cs-origin.chamung.com`으로 프록시합니다.

- 공개 도메인: `cs.chamung.com` -> Vercel `A 76.76.21.21`
- 원본 도메인: `cs-origin.chamung.com` -> Lightsail `A 3.39.48.139`
- 원본 서버 CSV: `/home/ubuntu/cs-flashcards/data/CS_encyclopedia_300plus.csv`

재배포:

```bash
vercel --cwd vercel-proxy --prod --yes
```
