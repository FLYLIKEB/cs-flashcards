"""Standalone interview generation checks; no app or database access."""

from contextlib import redirect_stdout
from html.parser import HTMLParser
import io
from pathlib import Path
import re
import tempfile
import unittest

from scripts.build_class101_interview import build, emphasize_keywords, inline, parse_answers, parse_questions, render_answer
from scripts.render_class101_audio import plain_text


ROOT = Path(__file__).resolve().parents[1]


class InterviewPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.summaries = []
        self.summary = None
        self.answer_count = 0
        self.confirmation_count = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "details":
            self.ids.append(attrs["id"])
        if tag == "summary":
            self.summary = ""
        if attrs.get("class") == "answer":
            self.answer_count += 1
        if attrs.get("class") == "confirmation":
            self.confirmation_count += 1

    def handle_data(self, data):
        if self.summary is not None:
            self.summary += data

    def handle_endtag(self, tag):
        if tag == "summary":
            self.summaries.append(self.summary)
            self.summary = None


class InterviewGenerationTests(unittest.TestCase):
    def test_published_answers_are_complete_without_confirmation_notes(self):
        source_root = ROOT / "applications/class101-interview"
        answers = parse_answers([source_root / name for name in (
            "answers-01-30.md", "answers-31-60.md", "answers-61-100.md",
        )])
        for number, body in answers.items():
            with self.subTest(number=number):
                self.assertTrue(body.startswith("**핵심 키워드:** "))
                spoken = plain_text(body)
                self.assertGreaterEqual(len(spoken), 100)
                self.assertLessEqual(len(spoken), 350)
                self.assertNotIn("핵심 키워드", spoken)
                for phrase in ("추정", "예측", "가정하", "가정하면", "설명하겠습니다", "확인 필요"):
                    self.assertNotIn(phrase, body)
                self.assertNotIn("확인 메모", body)
                self.assertFalse(any(line.startswith(">") for line in body.splitlines()))

    def test_keywords_are_visible_but_not_narrated(self):
        answer = "**핵심 키워드:** `SQL` · 멱등성 · 원자성\n\n동일 요청은 한 번만 처리하겠습니다."
        self.assertIn('class="answer-keywords"', render_answer(answer))
        self.assertEqual(plain_text(answer), "동일 요청은 한 번만 처리하겠습니다.")

    def test_keyword_emphasis_preserves_speech_and_inline_markup(self):
        body = "**핵심 키워드:** SQL · 멱등성\n\nSQL과 멱등성을 사용하고 `SQL`과 **멱등성**을 확인합니다. [SQL](https://example.com/SQL)"
        marked = emphasize_keywords(body)
        self.assertIn("**SQL**과 **멱등성**을", marked)
        self.assertIn("`SQL`과 **멱등성**", marked)
        self.assertIn("[SQL](https://example.com/SQL)", marked)
        self.assertEqual(plain_text(body), plain_text(marked))
        self.assertEqual(emphasize_keywords(marked), marked)
        rendered = render_answer(marked, 1)
        self.assertIn('data-underline-id="1-answer-1"', rendered)
        self.assertIn('<strong>SQL</strong>', rendered)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = (ROOT / "applications/class101-interview/questions.md").read_text(encoding="utf-8")
        (self.root / "questions.md").write_text(self.source, encoding="utf-8")
        self.paths = []
        for start, end in ((1, 30), (31, 60), (61, 100)):
            path = self.root / f"answers-{start:02}-{end}.md"
            path.write_text("\n\n".join(
                f"### {number}\n\n답변 {number}: 실제 경험과 설계 제안을 구분합니다.\n\n두 번째 문단입니다.\n\n> 확인 메모: 당시 설정을 확인하세요."
                for number in range(start, end + 1)
            ), encoding="utf-8")
            self.paths.append(path)

    def test_full_build_preserves_questions_and_answers_in_order(self):
        with redirect_stdout(io.StringIO()):
            build(self.root)
        document = (self.root / "index.html").read_text(encoding="utf-8")
        markdown = (self.root / "answers.md").read_text(encoding="utf-8")
        page = InterviewPage()
        page.feed(document)
        self.assertEqual(page.ids, [f"question-{number}" for number in range(1, 101)])
        self.assertEqual(page.answer_count, 100)
        self.assertEqual(page.confirmation_count, 100)
        groups = parse_questions(self.source)
        answers = parse_answers(self.paths)
        for number, question in [item for _, questions in groups for item in questions]:
            with self.subTest(number=number):
                self.assertIn(question.replace("`", ""), page.summaries[number - 1])
                self.assertIn(f"### {number}. {question}\n\n{answers[number]}", markdown)
        self.assertEqual(re.findall(r"^## (.+)$", markdown, re.MULTILINE), [title for title, _ in groups])
        self.assertEqual((self.root / "questions.md").read_text(encoding="utf-8"), self.source)
        self.assertIn('href="answers.md" download', document)
        self.assertIn('href="questions.md" download', document)
        self.assertEqual(document.count('data-listen="question"'), 100)
        self.assertEqual(document.count('data-listen="answer"'), 100)
        self.assertEqual(document.count('data-listen="from-here"'), 100)
        self.assertIn('id="interview-audio" controls preload="none"', document)
        self.assertIn('src="audio-player.js" defer', document)
        self.assertNotIn('class="draft-note"', document)
        self.assertNotIn('details[open] .preview { display:none;', document)

    def test_missing_answer_rejected_before_outputs(self):
        source = self.paths[-1].read_text(encoding="utf-8")
        self.paths[-1].write_text(source.split("### 100")[0], encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exactly answers 1 through 100"):
            build(self.root)
        self.assertFalse((self.root / "index.html").exists())
        self.assertFalse((self.root / "answers.md").exists())

    def test_duplicate_answer_rejected(self):
        with self.paths[-1].open("a", encoding="utf-8") as stream:
            stream.write("\n\n### 1\n\n중복 답변")
        with self.assertRaisesRegex(ValueError, "Duplicate answer: 1"):
            parse_answers(self.paths)

    def test_empty_or_note_only_answer_rejected(self):
        for body in ("", "> 확인 메모: 본문이 없습니다."):
            with self.subTest(body=body):
                self.paths[0].write_text(f"### 1\n\n{body}", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Empty answer: 1"):
                    parse_answers(self.paths)

    def test_question_order_and_category_size_rejected(self):
        with self.assertRaisesRegex(ValueError, "questions numbered"):
            parse_questions(self.source.replace("1. 본인의", "2. 본인의"))
        misplaced = self.source.replace("## 2. 성능 최적화·JPA·캐싱", "")
        with self.assertRaisesRegex(ValueError, "10 categories"):
            parse_questions(misplaced)

    def test_inline_formatting_escapes_html_and_unsafe_links(self):
        content = '<script>alert(1)</script> `<b>` **중요** [문서](https://example.com/?a=1&b=2) [실행](javascript:alert(1))'
        result = inline(content)
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)
        self.assertIn("<code>&lt;b&gt;</code>", result)
        self.assertIn("<strong>중요</strong>", result)
        self.assertIn('href="https://example.com/?a=1&amp;b=2"', result)
        self.assertNotIn('href="javascript:', result)
        result = inline('[링크](https://example.com/"onclick="alert)')
        self.assertNotIn('"onclick="', result)
        self.assertIn("&quot;", result)


if __name__ == "__main__":
    unittest.main()
