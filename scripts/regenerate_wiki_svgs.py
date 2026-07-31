from __future__ import annotations

import html
import re
import textwrap
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
WIKI_DIR = (ROOT / "../wikidocs-ebook/pages").resolve()
ASSET_DIR = ROOT / "static" / "wiki-assets"
ASSET_DIR.mkdir(parents=True, exist_ok=True)

PAGE_RE = re.compile(r"^[0-1][0-9]-.*\.md$")
IMAGE_BLOCK_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<url>https://cs\.chamung\.com/public/wiki-assets/[^)]+\.svg)\)\n"
    r"> 그림:.*\n> 출처:.*(?:\n)?",
    re.M,
)
TITLE_PREFIX_RE = re.compile(r"^\d{2}(?:[-.]\d{1,2})*(?:-\d{2})?\.\s*")
LINK_TITLE_RE = re.compile(r"\[(?P<title>[^\]]+)\]\([^)]+\)")
STOP_WORDS = {
    "핵심", "핵심 개념", "학습 목적", "기출 연결", "복습 포인트", "연결 핵심정리", "실무 연결 및 팁",
    "실무 적용 팁", "쉽게 이해하기", "주의점 요약", "대표 지표", "약어 풀이", "비교", "요약", "정리",
    "추가 시각 자료", "문서 핵심 개념", "실전 포인트", "판단 기준", "하위 페이지 링크", "시험 답안용 핵심 개념",
}
PALETTES = {
    "06": ("#2563eb", "#8b5cf6", "#dbeafe", "#eef2ff", "#0f172a"),
    "07": ("#0f766e", "#14b8a6", "#ccfbf1", "#ecfeff", "#0f172a"),
    "08": ("#0284c7", "#06b6d4", "#cffafe", "#ecfeff", "#0f172a"),
    "09": ("#4f46e5", "#7c3aed", "#e0e7ff", "#f3e8ff", "#0f172a"),
    "10": ("#b91c1c", "#f59e0b", "#fee2e2", "#fff7ed", "#0f172a"),
    "11": ("#7c3aed", "#ec4899", "#f3e8ff", "#fdf2f8", "#0f172a"),
    "12": ("#1d4ed8", "#0ea5e9", "#dbeafe", "#f0f9ff", "#0f172a"),
    "13": ("#0891b2", "#22c55e", "#cffafe", "#f0fdf4", "#0f172a"),
    "14": ("#1f2937", "#2563eb", "#e5e7eb", "#dbeafe", "#0f172a"),
    "15": ("#0f766e", "#ca8a04", "#ccfbf1", "#fefce8", "#0f172a"),
    "16": ("#9333ea", "#3b82f6", "#f3e8ff", "#eff6ff", "#0f172a"),
    "17": ("#0f766e", "#6366f1", "#d1fae5", "#e0e7ff", "#0f172a"),
}

FIXED_STEPS = {
    "SELECT-WHERE-GROUP-BY": ["FROM/JOIN", "WHERE", "GROUP BY", "HAVING", "SELECT", "ORDER BY"],
    "JOIN-서브쿼리": ["기준 테이블", "JOIN", "조건 필터", "서브쿼리", "집계", "결과"],
    "SQL 기본": ["SELECT", "FROM", "WHERE", "GROUP", "HAVING", "ORDER"],
    "3-Way-Handshake": ["SYN", "SYN-ACK", "ACK"],
    "HTTP-DNS-TLS": ["DNS 조회", "TCP 연결", "TLS 협상", "HTTP 요청", "응답 처리"],
    "결제 인프라": ["고객 요청", "승인", "청산", "결제", "통지"],
    "학습-검증-전처리": ["수집", "전처리", "학습", "검증", "배포"],
}

FIXED_COMPARE = {
    "FCFS-SJF-HRN-RR": ["FCFS", "SJF", "HRN", "RR"],
    "선점형과-비선점형": ["비선점형", "실행 유지", "선점형", "도착 시 교체"],
    "TCP와-UDP": ["TCP", "연결형", "UDP", "비연결형"],
    "블랙박스와-화이트박스": ["블랙박스", "입출력 중심", "화이트박스", "코드 경로 중심"],
    "단위-통합-인수테스트": ["단위", "통합", "시스템", "인수"],
}

FIXED_LAYERS = {
    "OSI와-TCP-IP": ["응용", "전송", "인터넷", "링크", "물리"],
    "메모리와-가상메모리": ["레지스터", "캐시", "메인 메모리", "가상 메모리", "디스크"],
    "클라우드 기초": ["SaaS", "PaaS", "IaaS", "가상화", "인프라"],
    "컴퓨터구조 심화": ["명령어", "CPU", "캐시", "메모리", "I/O"],
}

FIXED_MATRIX = {
    "평가 지표와-혼동행렬": ["TP", "FP", "FN", "TN"],
}

FIXED_NETWORK = {
    "마이크로서비스": ["API Gateway", "Service A", "Service B", "Event Bus", "DB"],
    "메시지 큐": ["Producer", "Broker", "Topic/Queue", "Consumer", "Retry"],
    "분산 시스템 이론": ["Client", "Leader", "Replica 1", "Replica 2", "Consensus"],
    "컨테이너": ["Source", "Image", "Container", "Pod", "Cluster"],
}

FIXED_FINANCE = {
    "핀테크-오픈뱅킹-마이데이터": ["고객 동의", "API 호출", "계좌 조회", "데이터 결합", "서비스"],
    "결제 인프라": ["지급 지시", "승인", "청산", "결제", "통지"],
    "CBDC-심화": ["중앙은행", "중개기관", "지갑", "거래 검증", "기록"],
    "금융-규제-프레임워크": ["규제", "정책", "감사", "보고", "통제"],
    "디지털자산": ["지갑", "거래소", "수탁", "원장", "규제"],
}

FIXED_AI = {
    "AI-ML-DL-기본": ["AI", "ML", "DL", "지도학습", "비지도학습"],
    "학습-검증-전처리": ["수집", "정제", "학습", "검증", "배포"],
    "평가-지표와-혼동행렬": ["TP", "FP", "FN", "TN", "F1"],
    "주요-모델과-딥러닝": ["선형모델", "트리", "SVM", "CNN", "Transformer"],
    "금융권-적용과-모델-리스크": ["입력 데이터", "모델", "모니터링", "드리프트", "설명가능성"],
}


def clean(text: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    return " ".join(text.replace("|", " ").replace("·", " ").replace("—", " ").split())


def strip_prefix(title: str) -> str:
    return TITLE_PREFIX_RE.sub("", title).strip()


def wrap(text: str, width: int) -> list[str]:
    raw = clean(text)
    if not raw:
        return [""]
    return textwrap.wrap(raw, width=width, break_long_words=False, break_on_hyphens=False) or [raw]


def tspan_lines(lines: list[str], x: int, y: int, cls: str, anchor: str = "start", line_h: int = 18) -> str:
    out = [f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">']
    for i, line in enumerate(lines):
        dy = "0" if i == 0 else str(line_h)
        out.append(f'<tspan x="{x}" dy="{dy}">{html.escape(line)}</tspan>')
    out.append('</text>')
    return "".join(out)


def short(value: str, limit: int = 18) -> str:
    value = clean(value).strip(" .")
    if len(value) <= limit:
        return value
    tokens = value.split()
    current = []
    size = 0
    for token in tokens:
        if size + len(token) + len(current) > limit:
            break
        current.append(token)
        size += len(token)
    return " ".join(current) or value[:limit]


def page_files() -> list[Path]:
    files = []
    for path in sorted(WIKI_DIR.glob("*.md")):
        if not PAGE_RE.match(path.name):
            continue
        subject = int(path.name[:2])
        if 6 <= subject <= 17:
            files.append(path)
    return files


def page_level(stem: str) -> int:
    return stem.count("-")


def read_meta(page: Path) -> dict:
    text = page.read_text(encoding="utf-8")
    title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), page.stem)
    subtitle = strip_prefix(title)
    headings = [clean(line[3:].strip()) for line in text.splitlines() if line.startswith("## ")]
    bullets = [clean(line[2:].strip()) for line in text.splitlines() if line.startswith("- ")]
    quotes = [clean(line[1:].strip()) for line in text.splitlines() if line.startswith(">")]
    links = [m.group("title") for m in LINK_TITLE_RE.finditer(text)]
    first_paras = []
    for line in text.splitlines()[1:25]:
        s = line.strip()
        if not s or s.startswith(("#", "!", ">", "-", "|")):
            continue
        first_paras.append(clean(s))
        if len(first_paras) >= 3:
            break
    image_match = IMAGE_BLOCK_RE.search(text)
    asset_url = image_match.group("url") if image_match else f"https://cs.chamung.com/public/wiki-assets/{page.stem}-infographic.svg"
    asset_name = Path(urlparse(asset_url).path).name
    return {
        "page": page,
        "text": text,
        "title": title,
        "subtitle": subtitle,
        "stem": page.stem,
        "subject": page.stem[:2],
        "headings": headings,
        "bullets": bullets,
        "quotes": quotes,
        "links": links,
        "paras": first_paras,
        "asset_url": asset_url,
        "asset_name": asset_name,
        "level": page_level(page.stem),
    }


def pick_terms(meta: dict, count: int = 5) -> list[str]:
    items: list[str] = []
    sources = [meta["subtitle"]] + meta["headings"] + meta["bullets"] + meta["paras"] + meta["links"]
    for source in sources:
        for part in re.split(r"[,/:()]+", clean(source)):
            piece = short(part.strip(), 18)
            if len(piece) < 2 or piece in STOP_WORDS:
                continue
            if piece not in items:
                items.append(piece)
            if len(items) >= count:
                return items
    return items or [meta["subtitle"]]


def detect_family(meta: dict) -> str:
    stem = meta["stem"]
    title = meta["subtitle"]
    text = meta["text"]
    if meta["level"] == 1:
        return "subject_hub"
    if any(key in stem for key in ["평가-지표와-혼동행렬"]):
        return "matrix"
    if any(key in stem for key in ["OSI와-TCP-IP", "메모리와-가상메모리", "클라우드-기초", "컴퓨터구조-심화"]):
        return "layers"
    if any(key in stem for key in ["프로세스-상태와-PCB", "동기화와-교착상태"]):
        return "state"
    if any(key in stem for key in ["프로세스와-스레드", "스레드와-멀티스레딩"]):
        return "split"
    if any(key in stem for key in ["CPU-스케줄링", "FCFS-SJF-HRN-RR", "선점형과-비선점형", "3-Way-Handshake", "결제-인프라"]):
        return "timeline"
    if any(key in stem for key in ["관계형-데이터베이스-기본", "릴레이션-튜플-속성", "키와-무결성", "SQL-기본", "JOIN-서브쿼리", "SELECT-WHERE-GROUP-BY"]):
        return "schema"
    if any(key in stem for key in ["정규화", "함수종속", "1NF-2NF-3NF"]):
        return "tree"
    if any(key in stem for key in ["트랜잭션과-회복", "형상관리와-비용산정", "학습-검증-전처리"]):
        return "pipeline"
    if any(key in stem for key in ["인덱스와-동시성", "트리와-그래프", "이진트리-힙-B트리"]):
        return "graph"
    if any(key in stem for key in ["TCP와-UDP", "블랙박스와-화이트박스", "단위-통합-인수테스트", "개발방법론"]):
        return "compare"
    if any(key in stem for key in ["HTTP-DNS-TLS", "라우팅과-서브넷", "마이크로서비스", "메시지-큐", "분산-시스템-이론", "컨테이너"]):
        return "network"
    if any(key in stem for key in ["선형-자료구조", "스택과-큐", "연결리스트", "정렬과-탐색", "구현", "빈출-코드-출력-문제"]):
        return "pipeline"
    if any(key in stem for key in ["DFS-BFS", "BFS-DFS", "최단경로", "동적계획법과-재귀"]):
        return "graph"
    if any(key in stem for key in ["암호화와-해시", "인증-인가-접근통제", "웹-네트워크-공격", "XSS", "SQL-Injection", "DDoS", "IDS-IPS-로그-감사"]):
        return "security"
    if any(key in stem for key in ["테스트", "설계-결합도-응집도"]):
        return "compare"
    if any(key in stem for key in ["의사소통", "수리", "문제해결", "실전-오답노트", "NCS"]):
        return "ncs"
    if any(key in stem for key in ["CPU-설계", "캐시와-메모리-계층", "명령어-세트", "입출력-시스템"]):
        return "layers"
    if any(key in stem for key in ["핀테크", "오픈뱅킹", "마이데이터", "CBDC", "규제", "디지털자산", "금융-도메인-지식"]):
        return "finance"
    if any(key in stem for key in ["AI-ML-DL", "학습", "전처리", "평가-지표", "모델", "리스크"]):
        return "ai"
    if any(key in stem for key in ["클라우드", "분산", "컨테이너", "메시지", "마이크로서비스"]):
        return "network"
    if "표" in text and "|" in text:
        return "schema"
    return "pipeline"


def family_payload(meta: dict, family: str) -> tuple[list[str], str]:
    stem = meta["stem"]
    subtitle = meta["subtitle"]
    terms = pick_terms(meta, 6)
    if family == "subject_hub":
        modules = [strip_prefix(t) for t in meta["links"] if t.startswith(meta["subject"])]
        labels = [short(m, 16) for m in modules[:4]] or terms[:4]
        caption = f"{subtitle}의 하위 학습 축을 중앙 개념에서 바깥으로 연결한 SVG 인포그래픽."
        return labels[:4], caption
    if family == "timeline":
        for key, values in FIXED_STEPS.items():
            if key in stem or key in subtitle:
                return values, f"{subtitle}의 시간 흐름과 상태 변화를 좌→우 타임라인으로 보여주는 SVG 인포그래픽."
        if "선점형과-비선점형" in stem:
            return FIXED_COMPARE["선점형과-비선점형"], f"{subtitle}의 실행 중단 여부와 응답 차이를 비교하는 SVG 인포그래픽."
        return terms[:5], f"{subtitle}의 처리 순서를 단계별로 보여주는 SVG 인포그래픽."
    if family == "layers":
        for key, values in FIXED_LAYERS.items():
            if key in stem or key in subtitle:
                return values, f"{subtitle}의 계층 구조를 위→아래로 쌓아 역할 경계를 보여주는 SVG 인포그래픽."
        return terms[:5], f"{subtitle}의 계층과 의존 관계를 쌓아 보여주는 SVG 인포그래픽."
    if family == "schema":
        if "SELECT-WHERE-GROUP-BY" in stem:
            return FIXED_STEPS["SELECT-WHERE-GROUP-BY"], f"{subtitle}의 실행 순서를 파이프라인으로 보여주는 SVG 인포그래픽."
        if "JOIN-서브쿼리" in stem:
            return FIXED_STEPS["JOIN-서브쿼리"], f"{subtitle}에서 테이블 결합과 서브쿼리 흐름을 보여주는 SVG 인포그래픽."
        if "SQL-기본" in stem or subtitle == "SQL":
            return FIXED_STEPS["SQL 기본"], f"{subtitle}에서 조회 문이 어떻게 평가되는지 단계별로 보여주는 SVG 인포그래픽."
        if "키와-무결성" in stem:
            return ["기본키", "후보키", "외래키", "참조 무결성"], f"{subtitle}의 키 종류와 무결성 연결을 보여주는 SVG 인포그래픽."
        return terms[:4], f"{subtitle}의 테이블 구조와 관계를 정리한 SVG 인포그래픽."
    if family == "tree":
        if any(key in stem for key in ["정규화", "1NF-2NF-3NF"]):
            labels = ["비정규형", "1NF", "2NF", "3NF", "BCNF"]
            return labels, f"{subtitle}의 분해 단계를 트리처럼 펼쳐 보여주는 SVG 인포그래픽."
        return terms[:5], f"{subtitle}의 분기 구조와 포함 관계를 보여주는 SVG 인포그래픽."
    if family == "graph":
        if any(key in stem for key in ["DFS-BFS", "BFS-DFS", "최단경로"]):
            return ["시작", "방문", "큐/스택", "거리 갱신", "도착"], f"{subtitle}의 그래프 탐색 순서와 최단경로 갱신을 보여주는 SVG 인포그래픽."
        if "동적계획법과-재귀" in stem:
            return ["재귀 호출", "중복 부분 문제", "메모이제이션", "탭뷸레이션"], f"{subtitle}에서 호출 트리와 DP 테이블 전환을 보여주는 SVG 인포그래픽."
        return terms[:5], f"{subtitle}의 노드 연결과 탐색 관점을 보여주는 SVG 인포그래픽."
    if family == "compare":
        for key, values in FIXED_COMPARE.items():
            if key in stem:
                return values, f"{subtitle}의 핵심 차이를 나란히 비교하는 SVG 인포그래픽."
        if "개발방법론" in stem:
            return ["폭포수", "애자일", "나선형", "스크럼"], f"{subtitle}의 방법론 차이를 비교하는 SVG 인포그래픽."
        if "테스트" in stem:
            return ["단위", "통합", "시스템", "인수"], f"{subtitle}의 테스트 수준과 목적을 비교하는 SVG 인포그래픽."
        if "설계-결합도-응집도" in stem:
            return ["낮은 결합도", "높은 응집도", "모듈 분리", "변경 영향"], f"{subtitle}의 좋은 모듈 조건을 비교하는 SVG 인포그래픽."
        return terms[:4], f"{subtitle}의 핵심 축을 비교하는 SVG 인포그래픽."
    if family == "network":
        for key, values in FIXED_NETWORK.items():
            if key in stem:
                return values, f"{subtitle}의 네트워크 경로와 노드 역할을 보여주는 SVG 인포그래픽."
        if "HTTP-DNS-TLS" in stem:
            return FIXED_STEPS["HTTP-DNS-TLS"], f"{subtitle}의 웹 요청 흐름을 단계별로 보여주는 SVG 인포그래픽."
        if "라우팅과-서브넷" in stem:
            return ["CIDR", "서브넷", "라우터", "경로 선택", "패킷 전달"], f"{subtitle}의 주소 분할과 라우팅 흐름을 보여주는 SVG 인포그래픽."
        return terms[:5], f"{subtitle}의 노드 간 통신 흐름을 보여주는 SVG 인포그래픽."
    if family == "state":
        if "프로세스-상태와-PCB" in stem:
            return ["NEW", "READY", "RUNNING", "WAIT", "TERMINATED", "PCB"], f"{subtitle}의 상태 전이와 PCB 역할을 함께 보여주는 SVG 인포그래픽."
        return ["Lock", "Wait", "Critical Section", "Deadlock", "Recovery"], f"{subtitle}의 상태 변화와 교착 구조를 보여주는 SVG 인포그래픽."
    if family == "split":
        if "프로세스와-스레드" in stem:
            return ["프로세스", "독립 메모리", "스레드", "공유 자원"], f"{subtitle}에서 프로세스와 스레드의 차이를 나눠 보여주는 SVG 인포그래픽."
        return ["메인 스레드", "워커 스레드", "공유 힙", "문맥 전환"], f"{subtitle}의 병렬 실행 구조를 나눠 보여주는 SVG 인포그래픽."
    if family == "security":
        if "암호화와-해시" in stem:
            return ["평문", "암호화", "복호화", "해시", "검증"], f"{subtitle}의 기밀성·무결성 흐름을 보여주는 SVG 인포그래픽."
        if "인증-인가-접근통제" in stem:
            return ["사용자", "인증", "권한", "정책", "리소스"], f"{subtitle}의 인증·인가 경로를 보여주는 SVG 인포그래픽."
        if "IDS-IPS-로그-감사" in stem:
            return ["수집", "탐지", "차단", "로그", "감사"], f"{subtitle}의 탐지·차단·감사 흐름을 보여주는 SVG 인포그래픽."
        return ["공격", "입력", "검증", "차단", "모니터링"], f"{subtitle}의 공격면과 방어 지점을 보여주는 SVG 인포그래픽."
    if family == "ncs":
        if "의사소통" in stem:
            return ["문장 구조", "핵심어", "조건 확인", "선지 제거"], f"{subtitle}의 독해 판단 순서를 보여주는 SVG 인포그래픽."
        if "수리" in stem:
            return ["정보 추출", "식 세우기", "계산", "검산"], f"{subtitle}의 계산 절차를 보여주는 SVG 인포그래픽."
        if "문제해결" in stem:
            return ["상황 파악", "조건 분기", "대안 비교", "결론"], f"{subtitle}의 문제해결 단계를 보여주는 SVG 인포그래픽."
        return ["오답 분류", "원인 기록", "재풀이", "재검증"], f"{subtitle}의 오답 관리 루프를 보여주는 SVG 인포그래픽."
    if family == "finance":
        for key, values in FIXED_FINANCE.items():
            if key in stem:
                return values, f"{subtitle}의 금융 업무 흐름과 통제 지점을 보여주는 SVG 인포그래픽."
        return ["요청", "검증", "청산", "결제", "보고"], f"{subtitle}의 금융 인프라 흐름을 보여주는 SVG 인포그래픽."
    if family == "ai":
        for key, values in FIXED_AI.items():
            if key in stem:
                return values, f"{subtitle}의 데이터·모델·평가 흐름을 보여주는 SVG 인포그래픽."
        return ["데이터", "특성", "학습", "평가", "운영"], f"{subtitle}의 AI 파이프라인을 보여주는 SVG 인포그래픽."
    if family == "matrix":
        return FIXED_MATRIX["평가 지표와-혼동행렬"], f"{subtitle}의 TP·FP·FN·TN과 주요 지표를 정리한 SVG 인포그래픽."
    if family == "pipeline":
        for key, values in FIXED_STEPS.items():
            if key in stem:
                return values, f"{subtitle}의 단계별 처리 흐름을 보여주는 SVG 인포그래픽."
        return terms[:5], f"{subtitle}의 처리 단계를 순서대로 보여주는 SVG 인포그래픽."
    return terms[:5], f"{subtitle}의 핵심 개념 관계를 정리한 SVG 인포그래픽."


def base_svg(meta: dict, body: str) -> str:
    a, b, pale1, pale2, ink = PALETTES[meta["subject"]]
    title_lines = wrap(meta["title"], 28)[:2]
    intro = meta["paras"][0] if meta["paras"] else meta["bullets"][0] if meta["bullets"] else meta["subtitle"]
    subtitle_lines = wrap(intro, 46)[:2]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720" role="img" aria-labelledby="title desc">
  <title id="title">{html.escape(meta['title'])} SVG 인포그래픽</title>
  <desc id="desc">{html.escape(meta['subtitle'])}</desc>
  <defs>
    <linearGradient id="grad-{meta['asset_name']}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{pale1}" />
      <stop offset="100%" stop-color="{pale2}" />
    </linearGradient>
    <linearGradient id="line-{meta['asset_name']}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{a}" />
      <stop offset="100%" stop-color="{b}" />
    </linearGradient>
    <style>
      .title {{ font: 700 34px 'Pretendard','Noto Sans KR',sans-serif; fill: {ink}; }}
      .subtitle {{ font: 500 17px 'Pretendard','Noto Sans KR',sans-serif; fill: #334155; }}
      .label {{ font: 700 17px 'Pretendard','Noto Sans KR',sans-serif; fill: {ink}; }}
      .body {{ font: 500 16px 'Pretendard','Noto Sans KR',sans-serif; fill: #334155; }}
      .small {{ font: 600 13px 'Pretendard','Noto Sans KR',sans-serif; fill: #475569; }}
      .cap {{ font: 700 14px 'Pretendard','Noto Sans KR',sans-serif; fill: {ink}; }}
    </style>
  </defs>
  <rect width="1200" height="720" fill="#f8fafc"/>
  <rect x="32" y="30" width="1136" height="660" rx="30" fill="url(#grad-{meta['asset_name']})" opacity="0.9"/>
  <rect x="48" y="46" width="1104" height="628" rx="28" fill="white"/>
  <rect x="48" y="46" width="1104" height="628" rx="28" fill="url(#grad-{meta['asset_name']})" opacity="0.14"/>
  <text class="small" x="84" y="86">금융공기업 IT · 페이지 맞춤 SVG</text>
  {tspan_lines(title_lines, 84, 118, 'title', line_h=36)}
  {tspan_lines(subtitle_lines, 84, 180, 'subtitle', line_h=24)}
  {body}
  <text class="small" x="84" y="654">{html.escape(meta['asset_name'])}</text>
</svg>'''


def box(x: int, y: int, w: int, h: int, title: str, lines: list[str], fill: str, stroke: str, title_fill: str = "#0f172a") -> str:
    title_lines = wrap(title, max(8, w // 18))[:2]
    body_lines: list[str] = []
    for line in lines[:3]:
        body_lines.extend(wrap(line, max(10, w // 15))[:2])
    body_lines = body_lines[:4]
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
        + tspan_lines(title_lines, x + w // 2, y + 34, 'label', anchor='middle', line_h=18).replace('fill: #0f172a;', f'fill: {title_fill};')
        + tspan_lines(body_lines, x + 18, y + 70, 'body', line_h=18)
    )


def arrow(x1: int, y1: int, x2: int, y2: int, stroke: str, animated: bool = True) -> str:
    mid = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="4" stroke-linecap="round" marker-end="url(#arrow)"/>'
    if animated:
        dash = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="2" stroke-linecap="round" stroke-dasharray="10 8" opacity="0.5"><animate attributeName="stroke-dashoffset" from="0" to="-72" dur="4s" repeatCount="indefinite"/></line>'
        return mid + dash
    return mid


def markers(meta: dict) -> str:
    a, b, *_ = PALETTES[meta["subject"]]
    return (
        '<defs>'
        f'<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{b}"/></marker>'
        '</defs>'
    )


def render_subject_hub(meta: dict, labels: list[str]) -> str:
    a, b, pale1, pale2, _ = PALETTES[meta["subject"]]
    pos = [(170, 260), (690, 260), (170, 470), (690, 470)]
    cards = []
    for (x, y), label in zip(pos, labels + ["", "", "", ""]):
        if not label:
            continue
        cards.append(box(x, y, 320, 110, label, [], pale1 if x < 500 else pale2, a))
    arrows = ''.join([
        arrow(600, 360, 490, 315, b), arrow(600, 360, 710, 315, b),
        arrow(600, 360, 490, 525, b), arrow(600, 360, 710, 525, b),
    ])
    center = box(440, 290, 320, 150, meta['subtitle'], [pick_terms(meta, 2)[0]], '#ffffff', b)
    return markers(meta) + center + ''.join(cards) + arrows


def render_timeline(meta: dict, labels: list[str]) -> str:
    a, b, pale1, pale2, _ = PALETTES[meta['subject']]
    xs = [110, 300, 490, 680, 870, 1060]
    items = labels[:6]
    pieces = ['<line x1="110" y1="390" x2="1060" y2="390" stroke="%s" stroke-width="8" stroke-linecap="round" opacity="0.25"/>' % a]
    pieces.append('<line x1="110" y1="390" x2="760" y2="390" stroke="%s" stroke-width="8" stroke-linecap="round"><animate attributeName="x2" values="240;1060;240" dur="7s" repeatCount="indefinite"/></line>' % b)
    for i, label in enumerate(items):
        x = xs[i]
        fill = pale1 if i % 2 == 0 else pale2
        pieces.append(f'<circle cx="{x}" cy="390" r="22" fill="white" stroke="{b}" stroke-width="4"/>')
        pieces.append(tspan_lines(wrap(label, 10)[:2], x, 342, 'label', anchor='middle', line_h=18))
        pieces.append(f'<circle cx="{x}" cy="390" r="8" fill="{a}"><animate attributeName="opacity" values="1;.4;1" dur="{2.5 + i * 0.4}s" repeatCount="indefinite"/></circle>')
        if i < len(items) - 1:
            pieces.append(arrow(x + 24, 390, xs[i + 1] - 24, 390, b))
        pieces.append(f'<rect x="{x-55}" y="430" width="110" height="52" rx="18" fill="{fill}" stroke="{a}" stroke-width="1.5"/>')
        pieces.append(tspan_lines(wrap(label, 10)[:2], x, 462, 'body', anchor='middle', line_h=18))
    return markers(meta) + ''.join(pieces)


def render_layers(meta: dict, labels: list[str]) -> str:
    a, b, pale1, pale2, _ = PALETTES[meta['subject']]
    top = 240
    pieces = []
    for i, label in enumerate(labels[:5]):
        y = top + i * 74
        fill = pale1 if i % 2 == 0 else pale2
        pieces.append(f'<rect x="280" y="{y}" width="640" height="56" rx="18" fill="{fill}" stroke="{a}" stroke-width="2"/>')
        pieces.append(tspan_lines(wrap(label, 30)[:1], 600, y + 34, 'label', anchor='middle'))
        if i < 4:
            pieces.append(f'<line x1="600" y1="{y+56}" x2="600" y2="{y+74}" stroke="{b}" stroke-width="4" stroke-dasharray="8 8"><animate attributeName="stroke-dashoffset" from="0" to="-40" dur="4s" repeatCount="indefinite"/></line>')
    pieces.append(box(96, 296, 150, 160, '입력', [labels[0] if labels else meta['subtitle']], '#ffffff', b))
    pieces.append(box(954, 296, 150, 160, '출력', [labels[-1] if labels else meta['subtitle']], '#ffffff', b))
    pieces.append(arrow(246, 376, 280, 376, b, False))
    pieces.append(arrow(920, 376, 954, 376, b, False))
    return ''.join(pieces)


def render_schema(meta: dict, labels: list[str]) -> str:
    a, b, pale1, pale2, _ = PALETTES[meta['subject']]
    left = box(92, 248, 250, 250, labels[0] if labels else '입력', labels[1:3], pale1, a)
    center = box(420, 222, 360, 302, meta['subtitle'], labels[2:5], '#ffffff', b)
    right = box(858, 248, 250, 250, labels[-1] if labels else '결과', labels[:2], pale2, a)
    bottom = box(330, 552, 540, 82, '핵심 규칙', labels[:4], '#f8fafc', a)
    lines = markers(meta) + left + center + right + bottom
    lines += arrow(342, 372, 420, 372, b) + arrow(780, 372, 858, 372, b) + arrow(600, 524, 600, 552, b)
    return lines


def render_tree(meta: dict, labels: list[str]) -> str:
    a, b, pale1, pale2, _ = PALETTES[meta['subject']]
    items = labels[:5]
    while len(items) < 5:
        items.append('단계')
    pieces = [box(420, 170, 360, 90, items[0], [], '#ffffff', b)]
    coords = [(210, 350), (430, 350), (650, 350), (870, 350)]
    for idx, (x, y) in enumerate(coords, start=1):
        fill = pale1 if idx % 2 else pale2
        pieces.append(box(x, y, 120, 82, items[idx], [], fill, a))
        pieces.append(arrow(600, 260, x + 60, y, b, False))
    pieces.append('<line x1="600" y1="516" x2="600" y2="612" stroke="%s" stroke-width="3" stroke-dasharray="8 8"><animate attributeName="stroke-dashoffset" from="0" to="-40" dur="4s" repeatCount="indefinite"/></line>' % b)
    pieces.append(box(390, 612, 420, 60, '분해 기준', items[1:5], '#f8fafc', a))
    return markers(meta) + ''.join(pieces)


def render_graph(meta: dict, labels: list[str]) -> str:
    a, b, pale1, pale2, _ = PALETTES[meta['subject']]
    coords = [(220, 360), (420, 250), (420, 470), (660, 250), (660, 470), (900, 360)]
    items = labels[:6]
    while len(items) < 6:
        items.append('노드')
    edges = [(0,1), (0,2), (1,3), (2,4), (3,5), (4,5), (1,2), (3,4)]
    pieces = markers(meta)
    for s, e in edges:
        x1, y1 = coords[s]
        x2, y2 = coords[e]
        pieces += f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{b}" stroke-width="3" stroke-dasharray="10 8" opacity="0.55"><animate attributeName="stroke-dashoffset" from="0" to="-72" dur="5s" repeatCount="indefinite"/></line>'
    for i, (x, y) in enumerate(coords):
        fill = pale1 if i % 2 == 0 else pale2
        pieces += f'<circle cx="{x}" cy="{y}" r="56" fill="white" stroke="{a}" stroke-width="3"/>'
        pieces += f'<circle cx="{x}" cy="{y}" r="46" fill="{fill}" opacity="0.95"/>'
        pieces += tspan_lines(wrap(items[i], 10)[:2], x, y-6, 'label', anchor='middle', line_h=18)
    pieces += box(360, 578, 480, 66, '탐색 포인트', labels[:4], '#ffffff', b)
    return pieces


def render_compare(meta: dict, labels: list[str]) -> str:
    a, b, pale1, pale2, _ = PALETTES[meta['subject']]
    items = labels[:4]
    while len(items) < 4:
        items.append('비교')
    pieces = []
    for i in range(4):
        x = 92 + i * 256
        fill = pale1 if i % 2 == 0 else pale2
        pieces.append(box(x, 250, 220, 280, items[i], [], fill, a))
    pieces.append('<line x1="200" y1="572" x2="1000" y2="572" stroke="%s" stroke-width="4" opacity="0.3"/>' % a)
    pieces.append('<line x1="200" y1="572" x2="760" y2="572" stroke="%s" stroke-width="4"><animate attributeName="x2" values="360;1000;360" dur="7s" repeatCount="indefinite"/></line>' % b)
    pieces.append(tspan_lines(wrap(meta['subtitle'], 44)[:2], 600, 620, 'body', anchor='middle', line_h=20))
    return ''.join(pieces)


def render_network(meta: dict, labels: list[str]) -> str:
    a, b, pale1, pale2, _ = PALETTES[meta['subject']]
    items = labels[:5]
    while len(items) < 5:
        items.append('서비스')
    pieces = markers(meta)
    pieces += box(460, 130, 280, 90, items[0], [], '#ffffff', b)
    xs = [120, 330, 540, 750, 960]
    for i, x in enumerate(xs):
        fill = pale1 if i % 2 == 0 else pale2
        pieces += box(x, 340, 120, 100, items[i], [], fill, a)
        pieces += arrow(600, 220, x + 60, 340, b, False)
    pieces += '<rect x="120" y="512" width="960" height="84" rx="24" fill="#ffffff" stroke="%s" stroke-width="2"/>' % a
    pieces += tspan_lines(wrap(' · '.join(items[1:]), 60)[:2], 600, 560, 'body', anchor='middle', line_h=20)
    pieces += '<line x1="120" y1="300" x2="1080" y2="300" stroke="%s" stroke-width="2" stroke-dasharray="12 10" opacity="0.35"><animate attributeName="stroke-dashoffset" from="0" to="-60" dur="4s" repeatCount="indefinite"/></line>' % b
    return pieces


def render_state(meta: dict, labels: list[str]) -> str:
    a, b, pale1, pale2, _ = PALETTES[meta['subject']]
    items = labels[:6]
    while len(items) < 6:
        items.append('상태')
    coords = [(170, 360), (370, 220), (600, 220), (830, 220), (1030, 360), (600, 520)]
    pieces = markers(meta)
    for i, (x, y) in enumerate(coords):
        fill = pale1 if i % 2 == 0 else pale2
        pieces += f'<rect x="{x-80}" y="{y-34}" width="160" height="68" rx="20" fill="{fill}" stroke="{a}" stroke-width="2"/>'
        pieces += tspan_lines(wrap(items[i], 12)[:2], x, y-2, 'label', anchor='middle', line_h=18)
    for s, e in [(0,1),(1,2),(2,3),(3,4),(2,5),(5,1)]:
        x1,y1 = coords[s]
        x2,y2 = coords[e]
        pieces += arrow(x1, y1, x2, y2, b, False)
    pieces += box(442, 578, 316, 58, '상태 제어 정보', [items[-1]], '#ffffff', b)
    return pieces


def render_security(meta: dict, labels: list[str]) -> str:
    a, b, pale1, pale2, _ = PALETTES[meta['subject']]
    items = labels[:5]
    while len(items) < 5:
        items.append('보안')
    pieces = markers(meta)
    pieces += box(90, 322, 180, 120, items[0], [], pale1, a)
    pieces += box(350, 250, 180, 120, items[1], [], '#ffffff', b)
    pieces += box(620, 322, 180, 120, items[2], [], pale2, a)
    pieces += box(890, 250, 180, 120, items[3], [], '#ffffff', b)
    pieces += box(455, 510, 250, 92, items[4], [], '#ffffff', a)
    pieces += arrow(270, 382, 350, 310, b)
    pieces += arrow(530, 310, 620, 382, b)
    pieces += arrow(800, 382, 890, 310, b)
    pieces += arrow(710, 442, 610, 510, b, False)
    pieces += arrow(440, 370, 520, 510, b, False)
    pieces += '<circle cx="595" cy="382" r="36" fill="#ffffff" stroke="%s" stroke-width="3"/>' % b
    pieces += tspan_lines(["검증"], 595, 389, 'label', anchor='middle')
    return pieces


def render_ncs(meta: dict, labels: list[str]) -> str:
    a, b, pale1, pale2, _ = PALETTES[meta['subject']]
    items = labels[:4]
    while len(items) < 4:
        items.append('단계')
    pieces = []
    for i, label in enumerate(items):
        x = 110 + i * 250
        fill = pale1 if i % 2 == 0 else pale2
        pieces.append(box(x, 270, 180, 200, label, [], fill, a))
        pieces.append(f'<circle cx="{x+90}" cy="520" r="24" fill="#ffffff" stroke="{b}" stroke-width="3"/>')
        pieces.append(tspan_lines([str(i+1)], x + 90, 528, 'label', anchor='middle'))
        if i < 3:
            pieces.append(arrow(x + 180, 370, x + 250, 370, b))
    pieces.append(box(250, 562, 700, 70, '풀이 루틴', items, '#ffffff', b))
    return markers(meta) + ''.join(pieces)


def render_finance(meta: dict, labels: list[str]) -> str:
    a, b, pale1, pale2, _ = PALETTES[meta['subject']]
    items = labels[:5]
    while len(items) < 5:
        items.append('단계')
    pieces = []
    xs = [90, 300, 510, 720, 930]
    for i, x in enumerate(xs):
        fill = pale1 if i % 2 == 0 else pale2
        pieces.append(box(x, 290, 180, 130, items[i], [], fill, a))
        if i < 4:
            pieces.append(arrow(x + 180, 355, xs[i + 1], 355, b))
    pieces.append('<rect x="90" y="510" width="1020" height="92" rx="26" fill="#ffffff" stroke="%s" stroke-width="2"/>' % a)
    pieces.append(tspan_lines(wrap('검증 · 기록 · 감사 추적 · 장애 대응', 48), 600, 558, 'body', anchor='middle', line_h=20))
    pieces.append('<line x1="90" y1="463" x2="1110" y2="463" stroke="%s" stroke-width="2" stroke-dasharray="10 8" opacity="0.4"><animate attributeName="stroke-dashoffset" from="0" to="-70" dur="4s" repeatCount="indefinite"/></line>' % b)
    return markers(meta) + ''.join(pieces)


def render_ai(meta: dict, labels: list[str]) -> str:
    a, b, pale1, pale2, _ = PALETTES[meta['subject']]
    items = labels[:5]
    while len(items) < 5:
        items.append('단계')
    pieces = markers(meta)
    pieces += box(450, 130, 300, 80, items[0], [], '#ffffff', b)
    lower = [(130, 320), (370, 320), (610, 320), (850, 320)]
    for i, (x, y) in enumerate(lower, start=1):
        fill = pale1 if i % 2 else pale2
        pieces += box(x, y, 220, 110, items[i], [], fill, a)
        pieces += arrow(600, 210, x + 110, 320, b, False)
    pieces += box(250, 540, 700, 74, '운영 포인트', items[1:], '#ffffff', a)
    return pieces


def render_pipeline(meta: dict, labels: list[str]) -> str:
    a, b, pale1, pale2, _ = PALETTES[meta['subject']]
    items = labels[:5]
    while len(items) < 5:
        items.append('단계')
    pieces = markers(meta)
    xs = [92, 304, 516, 728, 940]
    for i, x in enumerate(xs):
        fill = pale1 if i % 2 == 0 else pale2
        pieces += box(x, 308, 170, 110, items[i], [], fill, a)
        if i < 4:
            pieces += arrow(x + 170, 363, xs[i + 1], 363, b)
    pieces += box(220, 516, 760, 92, '핵심 체크', items[:4], '#ffffff', b)
    return pieces


def render_family(meta: dict, family: str, labels: list[str]) -> str:
    if family == 'subject_hub':
        return render_subject_hub(meta, labels)
    if family == 'timeline':
        return render_timeline(meta, labels)
    if family == 'layers':
        return render_layers(meta, labels)
    if family == 'schema':
        return render_schema(meta, labels)
    if family == 'tree':
        return render_tree(meta, labels)
    if family == 'graph':
        return render_graph(meta, labels)
    if family == 'compare':
        return render_compare(meta, labels)
    if family == 'network':
        return render_network(meta, labels)
    if family == 'state':
        return render_state(meta, labels)
    if family == 'security':
        return render_security(meta, labels)
    if family == 'ncs':
        return render_ncs(meta, labels)
    if family == 'finance':
        return render_finance(meta, labels)
    if family == 'ai':
        return render_ai(meta, labels)
    if family == 'matrix':
        return render_compare(meta, labels)
    return render_pipeline(meta, labels)


def update_page_image_block(meta: dict, caption: str) -> None:
    alt = f"{meta['title']} SVG 인포그래픽"
    block = f"![{alt}]({meta['asset_url']})\n> 그림: {caption}\n> 출처: 내부 생성 자산 (`{meta['asset_url']}`)\n"
    text = meta['text']
    new_text, count = IMAGE_BLOCK_RE.subn(block, text, count=1)
    if count == 0:
        lines = text.splitlines()
        insert_at = 1
        while insert_at < len(lines) and (not lines[insert_at].strip() or lines[insert_at].startswith('>')):
            insert_at += 1
        merged = lines[:insert_at] + [''] + block.rstrip('\n').splitlines() + [''] + lines[insert_at:]
        new_text = '\n'.join(merged)
        if text.endswith('\n'):
            new_text += '\n'
    meta['page'].write_text(new_text, encoding='utf-8')


def main() -> None:
    for page in page_files():
        meta = read_meta(page)
        family = detect_family(meta)
        labels, caption = family_payload(meta, family)
        svg = base_svg(meta, render_family(meta, family, labels))
        (ASSET_DIR / meta['asset_name']).write_text(svg, encoding='utf-8')
        update_page_image_block(meta, caption)
        print(f"{page.name}: {family} -> {meta['asset_name']}")


if __name__ == '__main__':
    main()
