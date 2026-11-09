"""Build the standalone interview Q&A page from Markdown sources."""

import html
import json
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


def sentence_lines(text):
    return re.split(r"(?<=[.!?]) +(?=\S)", text)


def sentence_markdown(body):
    return "\n\n".join(
        paragraph if paragraph.startswith(("**핵심 키워드:**", ">"))
        else "  \n".join(sentence_lines(" ".join(paragraph.splitlines())))
        for paragraph in re.split(r"\n\s*\n", body)
    )


def render_answer(body, number=None):
    blocks = []
    sentence_index = 0
    for paragraph in re.split(r"\n\s*\n", body):
        lines = paragraph.splitlines()
        if all(line.startswith(">") for line in lines):
            text = " ".join(line.removeprefix(">").strip() for line in lines)
            blocks.append(f'<aside class="confirmation">{inline(text)}</aside>')
        elif paragraph.startswith("**핵심 키워드:**"):
            blocks.append(f'<p class="answer-keywords">{inline(" ".join(lines))}</p>')
        else:
            # Preserve the separating space in textContent for saved underline offsets.
            spans = []
            for sentence in sentence_lines(" ".join(lines)):
                spans.append(f'<span class="speech-sentence" data-speech-kind="answer" data-sentence="{sentence_index}">{inline(sentence)}</span>')
                sentence_index += 1
            sentences = "<br> ".join(spans)
            blocks.append(f'<p>{sentences}</p>')
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
            preview = " ".join(f'<span class="speech-sentence" data-speech-kind="question" data-sentence="{i}">{inline(sentence)}</span>'
                               for i, sentence in enumerate(sentence_lines(question)))
            emphasized = emphasize_keywords(answers[number])
            body = render_answer(emphasized, number)
            markdown.extend([f"### {number}. {question}", sentence_markdown(emphasized)])
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
<link rel="preload" href="fonts/PretendardVariable.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="interview.css">
</head>
<body>
<nav aria-label="면접 연습 화면" style="display:flex;flex-wrap:wrap;gap:8px;width:min(800px,calc(100% - 48px));margin:20px auto 0;font-family:sans-serif">
<a href="./" aria-current="page" style="padding:10px 16px;min-height:44px;box-sizing:border-box;border:1px solid #275c48;border-radius:10px;background:#275c48;color:white;text-decoration:none">면접 답변 연습</a>
<a href="whiteboard.html" style="padding:10px 16px;min-height:44px;box-sizing:border-box;border:1px solid #275c48;border-radius:10px;background:white;color:#275c48;text-decoration:none">화이트보드 알고리즘</a>
</nav>
<header class="page-header">
<div><p class="eyebrow">CLASS101 · PP TEAM</p><h1>면접 연습</h1></div>
<button type="button" id="focus-break" hidden>잠깐 쉬기</button>
</header>
<details id="library-panel" class="library">
<summary>문항 고르기<span>목록 · 보기 설정 · 자료</span></summary>
<div class="library-body">
<label for="question-picker">바로 이동</label><select id="question-picker">__PICKER__</select>
<nav aria-label="질문 분야">__NAV__</nav>
<div class="tools"><button type="button" id="focus-mode" aria-pressed="true">전체 목록 보기</button><button type="button" id="expand">모두 펼치기</button><button type="button" id="collapse">모두 접기</button><a class="download" href="answers.md" download>질문·답변 Markdown</a><a class="download" href="questions.md" download>질문만 저장</a></div>
<p class="help">글자를 선택하면 밑줄을 긋거나 지울 수 있습니다. 밑줄과 연습 위치는 이 브라우저에 저장됩니다.</p>
</div></details>
<section id="break-panel" class="break-panel" aria-labelledby="break-title" hidden>
<p class="eyebrow">잠깐 멈춰도 괜찮아요</p><h2 id="break-title">돌아오면 여기서 이어가세요.</h2>
<p id="break-context"></p><p>음성은 멈춰 두었습니다. 준비되면 아래 버튼을 눌러 주세요.</p>
<button type="button" id="focus-resume" class="primary">이어서 연습하기</button>
</section>
<main id="study-main">
<div id="focus-controls" hidden>
<div class="focus-meta"><span id="focus-category"></span><span id="focus-position">1 / 100</span></div>
<div class="practice-progress"><progress id="focus-progress" max="100" value="0" aria-label="연습 표시한 문항 수"></progress><span id="focus-completed">연습 표시 0개</span></div>
<p id="focus-hint" role="status">먼저 질문을 읽고 내 말로 답해 보세요.</p>
<div class="focus-listen"><button type="button" id="focus-listen-question">질문 듣기</button><button type="button" id="focus-listen-answer">답변 듣기</button></div>
</div>
<div id="question-content">__SECTIONS__</div>
<div id="focus-actions" hidden>
<div class="study-steps"><button type="button" id="focus-prev">이전</button><button type="button" id="focus-reveal" class="primary">답변 보기</button><button type="button" id="focus-next">다음 문항 →</button></div>
<button type="button" id="focus-done" aria-pressed="false">이 문항 연습했어요</button>
</div>
</main>
<aside class="audio-player" aria-label="면접 음성 플레이어">
<div class="audio-transport"><audio id="interview-audio" controls preload="none" aria-label="현재 질문 또는 답변 음성"></audio><button type="button" id="listen-pause" disabled>일시정지</button></div>
<output id="listen-status" role="status">질문이나 답변을 선택해 들어보세요.</output>
<details class="audio-settings"><summary>연속 듣기 · 음성 설정</summary>
<div class="audio-options">
<label for="listen-mode">연속 재생</label><select id="listen-mode"><option value="both">질문 → 답변</option><option value="question">질문만</option><option value="answer">답변만</option></select>
<label for="playback-rate">속도</label><select id="playback-rate"><option value="0.8">0.8배</option><option value="1" selected>1배</option><option value="1.2">1.2배</option><option value="1.5">1.5배</option></select>
<label class="follow-option"><input type="checkbox" id="follow-reading" checked>재생 위치 따라가기</label>
</div>
<div class="audio-options"><button type="button" id="focus-listen-from-here">현재 문항부터 연속 듣기</button><button type="button" id="listen-all">전체 연속 듣기</button><button type="button" id="listen-prev" disabled>이전 음성</button><button type="button" id="listen-next" disabled>다음 음성</button><button type="button" id="listen-stop" disabled>정지</button></div>
</details>
</aside>
<footer><p id="focus-save-status" role="status">현재 위치는 이 브라우저에 저장됩니다.</p><p>박지우 이력서 · 클래스101 PP 팀 면접 준비</p></footer>
<div id="underline-tools" role="group" aria-label="선택한 글자 밑줄" hidden><button type="button" id="underline-add">밑줄 긋기</button><button type="button" id="underline-remove">밑줄 지우기</button><output id="underline-status" role="status">선택한 글자에 적용합니다.</output></div>

<script src="audio-player.js" defer></script>
<script src="underline.js" defer></script>
<script type="application/json" id="sentence-timings">__TIMINGS__</script>
<script src="focus-study.js" defer></script>
<script src="reading-highlight.js" defer></script>
</body>
</html>
'''
    picker = "".join(f'<option value="{number}">{number:03}. {html.escape(question.replace("`", ""))}</option>'
                     for _, questions in groups for number, question in questions)
    page = page.replace("__PICKER__", picker)
    page = page.replace("__NAV__", "".join(navigation)).replace("__SECTIONS__", "".join(sections))
    manifest = root / "audio" / "manifest.json"
    timings = {}
    if manifest.exists():
        timings = {f'{track["type"]}-{track["id"]:03}': track.get("sentences", [])
                   for track in json.loads(manifest.read_text(encoding="utf-8"))["tracks"]}
    page = page.replace("__TIMINGS__", json.dumps(timings).replace("<", "\\u003c"))
    (root / "index.html").write_text(page, encoding="utf-8")
    (root / "answers.md").write_text("\n\n".join(markdown) + "\n", encoding="utf-8")
    print("Built 100 question-and-answer toggles in 10 categories")


if __name__ == "__main__":
    build()
