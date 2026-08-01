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
        '큐는 먼저 들어온 데이터가 먼저 나가는 구조다.\n'
        '![기존 그림](https://example.com/old.png)\n'
        '> 그림: 큐 처리 흐름을 간단히 보여준다.\n'
        '> 출처: 예시 출처\n\n'
        'enqueue 후 dequeue 순서를 단계별로 확인한다.\n\n'
        '## 큐 연산\n\n'
        'dequeue는 맨 앞 원소를 제거한다.\n\n'
        '### 큐 예시\n\n'
        'FIFO 순서를 유지한다.\n',
        encoding='utf-8',
    )
    return book


def sample_gif_plan() -> dict:
    return {
        'nodes': [
            {'id': 'enqueue', 'label': 'enqueue', 'x': 0.2, 'y': 0.5, 'width': 0.18, 'height': 0.14},
            {'id': 'queue', 'label': 'queue', 'x': 0.5, 'y': 0.5, 'width': 0.18, 'height': 0.14},
            {'id': 'dequeue', 'label': 'dequeue', 'x': 0.8, 'y': 0.5, 'width': 0.18, 'height': 0.14},
        ],
        'edges': [
            {'id': 'into-queue', 'from': 'enqueue', 'to': 'queue'},
            {'id': 'out-queue', 'from': 'queue', 'to': 'dequeue'},
        ],
        'stages': [
            {'active_nodes': ['enqueue'], 'active_edges': []},
            {'active_nodes': ['enqueue', 'queue'], 'active_edges': ['into-queue']},
            {'active_nodes': ['queue', 'dequeue'], 'active_edges': ['out-queue']},
        ],
    }


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
            self.assertIn('먼저 들어온 데이터', page['images'][0]['context_excerpt'])

    def test_read_wiki_page_returns_section_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            book = write_wiki_book(Path(td))
            page = flashcard_app.read_wiki_page('intro', book)
            self.assertEqual([section['title'] for section in page['sections'][:3]], ['소개 문서', '큐 연산', '큐 예시'])
            self.assertIn('FIFO 순서를 유지한다.', page['sections'][0]['context_excerpt'])
            self.assertIn('FIFO 순서를 유지한다.', page['sections'][1]['context_excerpt'])
            self.assertEqual(page['sections'][2]['heading_id'], flashcard_app.wiki_heading_id('큐 예시'))

    def test_wiki_gif_image_prompt_uses_skill_style_and_context(self):
        prompt = flashcard_app.wiki_gif_image_prompt('소개 문서', {
            'section_title': '큐',
            'alt': '큐 처리 흐름',
            'caption': '큐 처리 흐름을 간단히 보여준다.',
            'context_excerpt': 'enqueue 후 dequeue 순서를 단계별로 확인한다.',
            'source_note': '예시 출처',
        })
        self.assertIn('설명문보다 움직임만 보고 작동 원리가 직관적으로 이해되게 만들어.', prompt)
        self.assertIn('정적인 인포그래픽 말고 실제 looping GIF로 만들어.', prompt)
        self.assertIn('enqueue 후 dequeue 순서', prompt)

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

    def test_api_wiki_image_regenerate_png_uses_prompt_override(self):
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
                ) as urlopen_mock:
                    flashcard_app.api_wiki_image_regenerate(
                        flashcard_app.WikiImageRegenerateRequest(
                            source_path='pages/intro.md',
                            image_index=0,
                            format='png',
                            prompt_override='CUSTOM PNG PROMPT',
                        )
                    )
                payload = json.loads(urlopen_mock.call_args.args[0].data.decode('utf-8'))
                self.assertEqual(payload['prompt'], 'CUSTOM PNG PROMPT')
            finally:
                flashcard_app.WIKI_BOOK_DIR = original_book_dir
                flashcard_app.OPENAI_API_KEY = original_key

    def test_api_wiki_section_image_generate_inserts_asset_below_heading(self):
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
                    data = flashcard_app.api_wiki_section_image_generate(
                        flashcard_app.WikiSectionImageGenerateRequest(
                            source_path='pages/intro.md',
                            section_index=1,
                            format='png',
                        )
                    )
                updated_text = (book / 'pages' / 'intro.md').read_text(encoding='utf-8')
                self.assertIn(data['updated']['asset_relative_path'], updated_text)
                self.assertIn('## 큐 연산\n![큐 연산 AI 이미지](', updated_text)
                asset_path = book / data['updated']['asset_relative_path']
                self.assertEqual(asset_path.read_bytes(), png_bytes)
                self.assertEqual(data['updated']['title'], '큐 연산')
            finally:
                flashcard_app.WIKI_BOOK_DIR = original_book_dir
                flashcard_app.OPENAI_API_KEY = original_key

    def test_api_wiki_section_image_generate_uses_prompt_override(self):
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
                ) as urlopen_mock:
                    flashcard_app.api_wiki_section_image_generate(
                        flashcard_app.WikiSectionImageGenerateRequest(
                            source_path='pages/intro.md',
                            section_index=1,
                            format='png',
                            prompt_override='CUSTOM SECTION PROMPT',
                        )
                    )
                payload = json.loads(urlopen_mock.call_args.args[0].data.decode('utf-8'))
                self.assertEqual(payload['prompt'], 'CUSTOM SECTION PROMPT')
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

    def test_request_wiki_gif_plan_uses_prompt_override(self):
        with mock.patch.object(
            flashcard_app,
            'request_codex_json_object',
            return_value=sample_gif_plan(),
        ) as request_mock:
            plan = flashcard_app.request_wiki_gif_plan(
                '소개 문서',
                {'section_title': '큐', 'context_excerpt': 'enqueue 후 dequeue 순서를 단계별로 확인한다.'},
                prompt_override='CUSTOM GIF PROMPT',
            )
        self.assertEqual(plan['stages'][1]['active_edges'], ['into-queue'])
        self.assertEqual(request_mock.call_args.args[1]['design_brief'], 'CUSTOM GIF PROMPT')

    def test_render_wiki_gif_plan_produces_distinct_frames(self):
        gif_bytes = flashcard_app.render_wiki_gif_plan(sample_gif_plan())
        self.assertEqual(gif_bytes[:6], b'GIF89a')
        with Image.open(BytesIO(gif_bytes)) as image:
            self.assertGreaterEqual(image.n_frames, 6)
            image.seek(0)
            first = image.convert('RGBA').tobytes()
            image.seek(image.n_frames - 1)
            last = image.convert('RGBA').tobytes()
        self.assertNotEqual(first, last)

    def test_api_wiki_image_regenerate_gif_writes_gif_asset(self):
        with tempfile.TemporaryDirectory() as td:
            book = write_wiki_book(Path(td))
            original_book_dir = flashcard_app.WIKI_BOOK_DIR
            original_key = flashcard_app.OPENAI_API_KEY
            try:
                flashcard_app.WIKI_BOOK_DIR = book
                flashcard_app.OPENAI_API_KEY = 'test-key'
                with mock.patch.object(
                    flashcard_app,
                    'request_wiki_gif_plan',
                    return_value=sample_gif_plan(),
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
                with Image.open(asset_path) as image:
                    self.assertGreaterEqual(image.n_frames, 6)
            finally:
                flashcard_app.WIKI_BOOK_DIR = original_book_dir
                flashcard_app.OPENAI_API_KEY = original_key


if __name__ == '__main__':
    unittest.main()
