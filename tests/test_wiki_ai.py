import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app as flashcard_app


class FakeUrlopenResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def write_wiki_book(root: Path) -> Path:
    book = root / 'wikidocs-ebook'
    pages = book / 'pages'
    pages.mkdir(parents=True, exist_ok=True)
    (book / 'README.md').write_text('# 금공 IT 위키\n', encoding='utf-8')
    (book / 'TOC.md').write_text('# 목차\n\n- [소개 문서](pages/intro.md)\n', encoding='utf-8')
    (pages / 'intro.md').write_text('# 소개 문서\n\n- [ ] 체크 항목\n\n원본 본문입니다.\n', encoding='utf-8')
    return book


class WikiAiRewriteTests(unittest.TestCase):
    def test_rewrite_wiki_markdown_with_codex_parses_json_output(self):
        original_key = flashcard_app.OPENAI_API_KEY
        try:
            flashcard_app.OPENAI_API_KEY = 'test-key'
            with mock.patch.object(
                flashcard_app,
                'urlopen',
                return_value=FakeUrlopenResponse({
                    'output_text': json.dumps({
                        'content': '# 소개 문서\n\nAI가 정리한 본문입니다.\n',
                    }, ensure_ascii=False),
                }),
            ) as urlopen_mock:
                result = flashcard_app.rewrite_wiki_markdown_with_codex('pages/intro.md', '# 소개 문서\n\n원본\n', '더 간결하게')
            self.assertIn('AI가 정리한 본문입니다.', result)
            self.assertIn('/responses', urlopen_mock.call_args.args[0].full_url)
        finally:
            flashcard_app.OPENAI_API_KEY = original_key

    def test_api_wiki_ai_rewrite_preview_returns_proposal(self):
        with tempfile.TemporaryDirectory() as td:
            book = write_wiki_book(Path(td))
            original_book_dir = flashcard_app.WIKI_BOOK_DIR
            original_key = flashcard_app.OPENAI_API_KEY
            try:
                flashcard_app.WIKI_BOOK_DIR = book
                flashcard_app.OPENAI_API_KEY = 'test-key'
                with mock.patch.object(
                    flashcard_app,
                    'urlopen',
                    return_value=FakeUrlopenResponse({
                        'output_text': json.dumps({
                            'content': '# 소개 문서\n\nAI 초안 본문입니다.\n',
                        }, ensure_ascii=False),
                    }),
                ):
                    data = flashcard_app.api_wiki_ai_rewrite_preview(
                        flashcard_app.WikiAiRewriteRequest(
                            source_path='pages/intro.md',
                            content='# 소개 문서\n\n원본 본문입니다.\n',
                            instruction='면접 답변용으로 정리',
                        )
                    )
                self.assertEqual(data['source_path'], 'pages/intro.md')
                self.assertEqual(data['page_slug'], 'intro')
                self.assertEqual(data['model'], flashcard_app.CODEX_MODEL)
                self.assertIn('AI 초안 본문입니다.', data['proposal']['content'])
            finally:
                flashcard_app.WIKI_BOOK_DIR = original_book_dir
                flashcard_app.OPENAI_API_KEY = original_key


if __name__ == '__main__':
    unittest.main()
