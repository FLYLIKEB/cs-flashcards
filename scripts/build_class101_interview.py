"""Build the standalone interview Q&A page from Markdown sources."""

import html
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1] / "applications" / "class101-interview"


def parse_questions(source):
    groups = []
    numbers = []
    for line in source.splitlines():
        if line.startswith("## "):
            groups.append((line[3:], []))
        elif match := re.fullmatch(r"(\d+)\. (.+)", line):
            if not groups:
                raise ValueError("Question appears before a category")
            number, question = match.groups()
            numbers.append(int(number))
            groups[-1][1].append((int(number), question))
    if numbers != list(range(1, 101)):
        raise ValueError("Expected questions numbered 1 through 100 in order")
    if len(groups) != 10 or any(len(items) != 10 for _, items in groups):
        raise ValueError("Expected 10 categories containing 10 questions each")

    return groups


def parse_answers(paths):
    answers = {}
    for path in paths:
        source = path.read_text(encoding="utf-8").strip()
        chunks = re.split(r"^### (\d+)\s*$", source, flags=re.MULTILINE)
        if chunks[0].strip():
            raise ValueError(f"Unexpected content before first answer: {path.name}")
        for number, body in zip(chunks[1::2], chunks[2::2]):
            number = int(number)
            if number in answers:
                raise ValueError(f"Duplicate answer: {number}")
            body = body.strip()
            if not any(line.strip() and not line.startswith(">") for line in body.splitlines()):
                raise ValueError(f"Empty answer: {number}")
            if re.search(r"^#{1,6} ", body, flags=re.MULTILINE):
                raise ValueError(f"Unexpected heading inside answer: {number}")
            answers[number] = body
    if sorted(answers) != list(range(1, 101)):
        raise ValueError("Expected exactly answers 1 through 100")
    return answers


def inline(text):
    # This page uses only code, bold and HTTPS links, not arbitrary Markdown/HTML.
    pattern = r"`([^`]+)`|\*\*([^*]+)\*\*|\[([^\]]+)\]\((https://[^\s)]+)\)"
    parts = []
    start = 0
    for match in re.finditer(pattern, text):
        parts.append(html.escape(text[start:match.start()]))
        code, bold, label, url = match.groups()
        if code is not None:
            parts.append(f"<code>{html.escape(code)}</code>")
        elif bold is not None:
            parts.append(f"<strong>{html.escape(bold)}</strong>")
        else:
            parts.append(f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>')
        start = match.end()
    parts.append(html.escape(text[start:]))
    return "".join(parts)


def emphasize_keywords(body):
    match = re.match(r"\*\*핵심 키워드:\*\* ([^\n]+)", body)
    if not match:
        return body
    keywords = [word.strip().strip("`*") for word in match[1].split(" · ")]
    pattern = re.compile("|".join(re.escape(word) for word in sorted(keywords, key=len, reverse=True) if word))
    # Keep existing Markdown tokens intact, including URLs and explicit emphasis.
    parts = re.split(r"(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\(https://[^\s)]+\))", body[match.end():])
    emphasized = "".join(part if index % 2 else pattern.sub(lambda m: f"**{m[0]}**", part)
                         for index, part in enumerate(parts))
    return "**핵심 키워드:** " + " · ".join(f"**{word}**" for word in keywords) + emphasized


def render_answer(body, number=None):
    blocks = []
    for paragraph in re.split(r"\n\s*\n", body):
        lines = paragraph.splitlines()
        if all(line.startswith(">") for line in lines):
            text = " ".join(line.removeprefix(">").strip() for line in lines)
            blocks.append(f'<aside class="confirmation">{inline(text)}</aside>')
        elif paragraph.startswith("**핵심 키워드:**"):
            blocks.append(f'<p class="answer-keywords">{inline(" ".join(lines))}</p>')
        else:
            blocks.append(f'<p>{inline(" ".join(lines))}</p>')
    if number is not None:
        blocks = [block.replace("<p", f'<p data-underline-id="{number}-answer-{index}"', 1)
                  if block.startswith("<p") else block for index, block in enumerate(blocks)]
    return "".join(blocks)


def build(root=ROOT):
    groups = parse_questions((root / "questions.md").read_text(encoding="utf-8"))
    answers = parse_answers([root / name for name in (
        "answers-01-30.md", "answers-31-60.md", "answers-61-100.md",
    )])
    markdown = ["# 클래스101 PP 팀 면접 예상 질문과 답변 100개",
                "질문별 핵심 키워드와 면접 답변을 정리했습니다."]
    navigation = []
    sections = []
    for index, (title, questions) in enumerate(groups, 1):
        markdown.append(f"## {title}")
        title = html.escape(title)
        navigation.append(f'<a href="#category-{index}">{title}</a>')
        cards = []
        for number, question in questions:
            preview = inline(question)
            emphasized = emphasize_keywords(answers[number])
            body = render_answer(emphasized, number)
            markdown.extend([f"### {number}. {question}", emphasized])
            cards.append(f'''<details id="question-{number}">
<summary><span class="number">Q{number:03}</span><span class="preview" data-underline-id="{number}-question">{preview}</span><span class="indicator" aria-hidden="true">+</span></summary>
<div class="answer"><div class="listen-actions" aria-label="{number}번 음성 듣기"><button type="button" data-listen="question" data-question="{number}">질문 듣기</button><button type="button" data-listen="answer" data-question="{number}">답변 듣기</button><button type="button" data-listen="from-here" data-question="{number}">여기부터 연속 듣기</button></div><p class="answer-label">답변</p>{body}</div></details>''')
        sections.append(f'<section id="category-{index}" aria-labelledby="heading-{index}"><h2 id="heading-{index}">{title}<small>10문항</small></h2>{"".join(cards)}</section>')

    page = '''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>클래스101 · 면접 질문 100</title>
<style>
:root { color-scheme: light; --bg:#f6f5f1; --ink:#202d2a; --muted:#5a6863; --line:#d9ded8; --accent:#215f4e; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:16px/1.7 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif; }
header,main,footer { max-width:1160px; margin:auto; padding:32px; }
header { padding-top:56px; padding-bottom:28px; }
.eyebrow { margin:0 0 10px; color:var(--accent); font-size:13px; font-weight:700; letter-spacing:.08em; }
h1 { margin:0; font-size:clamp(28px,4vw,42px); line-height:1.3; letter-spacing:-.04em; }
.intro { color:var(--muted); margin:14px 0 20px; }
.tools { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
button,.download { min-height:44px; padding:9px 15px; border:1px solid var(--line); border-radius:8px; background:white; color:var(--ink); font:inherit; font-size:14px; cursor:pointer; text-decoration:none; }
button:first-child { background:var(--accent); color:white; border-color:var(--accent); }
button:hover,.download:hover { filter:brightness(.95); }
:focus-visible { outline:3px solid #b05d22; outline-offset:4px; }
main { display:grid; grid-template-columns:235px minmax(0,1fr); gap:40px; padding-top:8px; }
nav { position:sticky; top:24px; align-self:start; }
nav p { margin:0 0 12px; color:var(--muted); font-size:13px; }
nav a { display:block; padding:10px 8px; color:var(--muted); text-decoration:none; font-size:14px; border-radius:6px; }
nav a:hover { background:#e8ede7; color:var(--accent); }
section { margin:0 0 40px; scroll-margin-top:24px; }
h2 { display:flex; flex-wrap:wrap; align-items:center; gap:10px; font-size:20px; margin:0 0 16px; line-height:1.5; letter-spacing:-.03em; }
h2 small { font-size:12px; color:var(--muted); font-weight:400; letter-spacing:0; }
details { background:#fff; border:1px solid var(--line); border-radius:10px; margin:8px 0; overflow:hidden; }
summary { display:flex; align-items:center; gap:12px; min-height:64px; padding:16px 18px; cursor:pointer; list-style:none; }
summary::-webkit-details-marker { display:none; }
.number { flex-shrink:0; font-size:12px; font-weight:700; color:var(--accent); font-variant-numeric:tabular-nums; }
.preview { min-width:0; font-size:16px; line-height:1.7; word-break:keep-all; overflow-wrap:anywhere; }
.indicator { flex-shrink:0; margin-left:auto; font-size:22px; line-height:1; color:var(--muted); }
details[open] { border-color:#9db9ad; }
details[open] .indicator { font-size:0; }
details[open] .indicator::after { content:"−"; font-size:22px; }
.answer { margin:0 18px 22px; padding-top:14px; border-top:1px solid var(--line); font-size:16px; line-height:1.85; overflow-wrap:anywhere; word-break:keep-all; }
.answer p { margin:0 0 14px; }
.answer .answer-label { color:var(--accent); font-size:12px; font-weight:700; margin-bottom:10px; }
.answer .answer-keywords { padding:10px 12px; background:#edf2ed; border-radius:6px; font-size:14px; color:var(--accent); }
strong { font-weight:750; }
[data-underline-id] { user-select:text; -webkit-user-select:text; }
.user-underline { text-decoration:underline; text-decoration-color:#b05d22; text-decoration-thickness:2px; text-underline-offset:4px; }
#underline-tools { position:fixed; bottom:20px; left:50%; transform:translateX(-50%); z-index:5; width:max-content; max-width:calc(100% - 24px); padding:10px; background:#fff; border:1px solid var(--line); border-radius:10px; box-shadow:0 4px 24px #202d2a26; }
#underline-tools:not([hidden]) { display:flex; flex-wrap:wrap; gap:8px; }
#underline-status { display:block; flex-basis:100%; font-size:12px; color:var(--muted); }
.confirmation { padding:12px 14px; border-left:3px solid #bda471; background:#f7f3e9; color:#655438; font-size:14px; margin-top:16px; }
code { background:#eef2ee; padding:2px 5px; border-radius:4px; font-size:.9em; }
footer { padding-top:0; font-size:13px; color:var(--muted); }
.audio-player { position:sticky; top:0; z-index:2; max-width:1096px; margin:0 auto 24px; padding:14px 18px; background:#edf2ed; border:1px solid #c5d4c8; border-radius:10px; }
.audio-options,.audio-transport,.listen-actions { display:flex; flex-wrap:wrap; align-items:center; gap:8px; }
.audio-options label { font-size:14px; }
.audio-options select { min-height:44px; border:1px solid var(--line); border-radius:6px; padding:8px; background:white; color:var(--ink); font:inherit; }
.audio-transport { margin-top:8px; }
.audio-transport audio { width:280px; max-width:100%; height:44px; }
#listen-status { display:block; font-size:14px; color:var(--accent); margin-top:8px; }
.listen-actions { margin-bottom:16px; }
.listen-actions button { font-size:13px; padding:8px 11px; }
details.is-speaking { border:2px solid var(--accent); }
section[id] { scroll-margin-top:240px; }
nav { top:220px; }
@media(max-width:760px) {
 header,main,footer { padding-left:20px; padding-right:20px; }
 header { padding-top:32px; }
 main { display:block; }
 nav { position:static; display:flex; overflow-x:auto; gap:8px; padding-bottom:18px; margin-bottom:20px; }
 nav p { display:none; }
 nav a { white-space:nowrap; border:1px solid var(--line); background:white; }
 h2 { font-size:18px; }
 .preview,.answer { font-size:16px; }
 summary { padding:15px 14px; gap:10px; }
 .audio-player { position:static; margin:0 20px 24px; }
 .audio-transport audio { width:100%; }
 section[id] { scroll-margin-top:24px; }
}
@media print { nav,.tools,footer,.audio-player,.listen-actions,#underline-tools { display:none; } main { display:block; } details { break-inside:avoid; } }
</style>
</head>
<body>
<header>
<p class="eyebrow">CLASS101 · PAYMENTS &amp; PAYOUTS</p>
<h1>면접 질문 100</h1>
<p class="intro">박지우 이력서 × 클래스101 PP 팀<br>10개 분야 · 질문을 누르면 핵심 키워드와 답변이 펼쳐집니다.</p>
<div class="tools"><button type="button" id="expand">모두 펼치기</button><button type="button" id="collapse">모두 접기</button><a class="download" href="answers.md" download>질문·답변 Markdown</a><a class="download" href="questions.md" download>질문만 저장</a></div>
<p class="intro">질문이나 답변에서 글자를 선택하면 밑줄을 추가하거나 지울 수 있습니다. 밑줄은 이 브라우저에 저장됩니다.</p>
</header>
<aside class="audio-player" aria-label="면접 음성 플레이어">
<div class="audio-options">
<label for="listen-mode">연속 재생</label><select id="listen-mode"><option value="both">질문 → 답변</option><option value="question">질문만</option><option value="answer">답변만</option></select>
<label for="playback-rate">속도</label><select id="playback-rate"><option value="0.8">0.8배</option><option value="1" selected>1배</option><option value="1.2">1.2배</option><option value="1.5">1.5배</option></select>
<button type="button" id="listen-all">전체 연속 듣기</button>
</div>
<div class="audio-transport"><audio id="interview-audio" controls preload="none" aria-label="현재 질문 또는 답변 음성"></audio><button type="button" id="listen-prev" disabled>이전 음성</button><button type="button" id="listen-pause" disabled>일시정지</button><button type="button" id="listen-next" disabled>다음 음성</button><button type="button" id="listen-stop" disabled>정지</button></div>
<output id="listen-status" role="status">한국어 음성으로 질문과 답변을 개별 또는 연속으로 들을 수 있습니다.</output>
</aside>
<main><nav aria-label="질문 분야"><p>분야 바로가기</p>__NAV__</nav><div>__SECTIONS__</div></main>
<footer>이력서와 채용공고를 바탕으로 작성한 예상 질문과 답변입니다.</footer>
<div id="underline-tools" role="group" aria-label="선택한 글자 밑줄" hidden><button type="button" id="underline-add">밑줄 긋기</button><button type="button" id="underline-remove">밑줄 지우기</button><output id="underline-status" role="status">선택한 글자에 적용합니다.</output></div>
<script>
const questions = document.querySelectorAll('details');
document.getElementById('expand').addEventListener('click', () => questions.forEach(item => { item.open = true; }));
document.getElementById('collapse').addEventListener('click', () => questions.forEach(item => { item.open = false; }));
</script>
<script src="audio-player.js" defer></script>
<script src="underline.js" defer></script>
</body>
</html>
'''
    page = page.replace("__NAV__", "".join(navigation)).replace("__SECTIONS__", "".join(sections))
    (root / "index.html").write_text(page, encoding="utf-8")
    (root / "answers.md").write_text("\n\n".join(markdown) + "\n", encoding="utf-8")
    print("Built 100 question-and-answer toggles in 10 categories")


if __name__ == "__main__":
    build()
