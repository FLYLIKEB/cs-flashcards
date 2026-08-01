import base64
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock

from PIL import Image

import app as flashcard_app


class FakeUrlopenResponse:
    def __init__(self, payload=None, *, raw: bytes | None = None):
        self.payload = payload
        self.raw = raw

    def read(self):
        if self.raw is not None:
            return self.raw
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
    (pages / 'intro.md').write_text(
        '# 소개 문서\n\n'
        '![기존 그림](https://example.com/old.png)\n'
        '> 그림: 큐 처리 흐름을 간단히 보여준다.\n'
        '> 출처: 예시 출처\n\n'
        '원본 본문입니다.\n',
        encoding='utf-8',
    )
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

    def test_read_wiki_page_returns_image_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            book = write_wiki_book(Path(td))
            page = flashcard_app.read_wiki_page('intro', book)
            self.assertEqual(page['images'][0]['index'], 0)
            self.assertEqual(page['images'][0]['alt'], '기존 그림')
            self.assertEqual(page['images'][0]['format'], 'png')
            self.assertIn('https://example.com/old.png', page['images'][0]['src'])

    def test_api_wiki_image_regenerate_png_updates_local_markdown_and_asset(self):
        with tempfile.TemporaryDirectory() as td:
            book = write_wiki_book(Path(td))
            original_book_dir = flashcard_app.WIKI_BOOK_DIR
            original_key = flashcard_app.OPENAI_API_KEY
            try:
                flashcard_app.WIKI_BOOK_DIR = book
                flashcard_app.OPENAI_API_KEY = 'test-key'
                png_bytes = b'\x89PNG\r\n\x1a\npng-preview'
                with mock.patch.object(
                    flashcard_app,
                    'urlopen',
                    return_value=FakeUrlopenResponse({
                        'data': [{'b64_json': base64.b64encode(png_bytes).decode('ascii')}],
                    }),
                ):
                    data = flashcard_app.api_wiki_image_regenerate(
                        flashcard_app.WikiImageRegenerateRequest(
                            source_path='pages/intro.md',
                            image_index=0,
                            format='png',
                        )
                    )
                updated_text = (book / 'pages' / 'intro.md').read_text(encoding='utf-8')
                self.assertIn('assets/generated-wiki-ai/', updated_text)
                self.assertTrue(data['updated']['asset_relative_path'].endswith('.png'))
                asset_path = book / data['updated']['asset_relative_path']
                self.assertEqual(asset_path.read_bytes(), png_bytes)
                self.assertIn('/api/wiki/raw/assets/generated-wiki-ai/', data['page']['html'])
            finally:
                flashcard_app.WIKI_BOOK_DIR = original_book_dir
                flashcard_app.OPENAI_API_KEY = original_key

    def test_api_wiki_image_regenerate_svg_updates_local_markdown_and_asset(self):
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
                            'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="18" fill="#eff6ff"/><circle cx="50" cy="50" r="24" fill="#2563eb"/></svg>',
                        }, ensure_ascii=False),
                    }),
                ):
                    data = flashcard_app.api_wiki_image_regenerate(
                        flashcard_app.WikiImageRegenerateRequest(
                            source_path='pages/intro.md',
                            image_index=0,
                            format='svg',
                        )
                    )
                asset_path = book / data['updated']['asset_relative_path']
                self.assertTrue(asset_path.read_text(encoding='utf-8').startswith('<svg'))
                self.assertTrue(data['updated']['asset_relative_path'].endswith('.svg'))
                self.assertIn('assets/generated-wiki-ai/', (book / 'pages' / 'intro.md').read_text(encoding='utf-8'))
            finally:
                flashcard_app.WIKI_BOOK_DIR = original_book_dir
                flashcard_app.OPENAI_API_KEY = original_key

    def test_api_wiki_image_regenerate_gif_writes_gif_asset(self):
        with tempfile.TemporaryDirectory() as td:
            book = write_wiki_book(Path(td))
            original_book_dir = flashcard_app.WIKI_BOOK_DIR
            original_key = flashcard_app.OPENAI_API_KEY
            try:
                flashcard_app.WIKI_BOOK_DIR = book
                flashcard_app.OPENAI_API_KEY = 'test-key'
                buffer = BytesIO()
                Image.new('RGBA', (4, 4), '#60a5fa').save(buffer, format='PNG')
                png_bytes = buffer.getvalue()
                with mock.patch.object(
                    flashcard_app,
                    'urlopen',
                    return_value=FakeUrlopenResponse({
                        'data': [{'b64_json': base64.b64encode(png_bytes).decode('ascii')}],
                    }),
                ):
                    data = flashcard_app.api_wiki_image_regenerate(
                        flashcard_app.WikiImageRegenerateRequest(
                            source_path='pages/intro.md',
                            image_index=0,
                            format='gif',
                        )
                    )
                asset_path = book / data['updated']['asset_relative_path']
                self.assertEqual(asset_path.read_bytes()[:6], b'GIF89a')
                self.assertTrue(data['updated']['asset_relative_path'].endswith('.gif'))
            finally:
                flashcard_app.WIKI_BOOK_DIR = original_book_dir
                flashcard_app.OPENAI_API_KEY = original_key


if __name__ == '__main__':
    unittest.main()
