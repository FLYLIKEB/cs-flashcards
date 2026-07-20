import tempfile
import unittest
from pathlib import Path

import app as flashcard_app


ROOT = Path(__file__).resolve().parents[1]
WIKI_HTML = (ROOT / 'static' / 'wiki.html').read_text(encoding='utf-8')
WIKI_JS = (ROOT / 'static' / 'wiki.js').read_text(encoding='utf-8')
STYLE_CSS = (ROOT / 'static' / 'style.css').read_text(encoding='utf-8')


def write_wiki_book(root: Path) -> Path:
    book = root / 'wikidocs-ebook'
    pages = book / 'pages'
    pages.mkdir(parents=True, exist_ok=True)
    (book / 'README.md').write_text('# 금공 IT 위키\n', encoding='utf-8')
    (book / 'TOC.md').write_text('# 목차\n\n- [소개 문서](pages/intro.md)\n', encoding='utf-8')
    (pages / 'intro.md').write_text('# 소개 문서\n\n- [ ] 체크 항목\n\n[하위 문서](./child.md)\n', encoding='utf-8')
    (pages / 'child.md').write_text('# 하위 문서\n\n본문\n', encoding='utf-8')
    return book


class WikiMarkdownEditorTests(unittest.TestCase):
    def test_wiki_static_assets_include_markdown_editor(self):
        self.assertIn('easymde.min.css', WIKI_HTML)
        self.assertIn('easymde.min.js', WIKI_HTML)
        self.assertIn('id="wikiEditorTextarea"', WIKI_HTML)
        self.assertIn('new window.EasyMDE({', WIKI_JS)
        self.assertIn("/api/wiki/render-preview", WIKI_JS)
        self.assertIn('previewRender: (plainText, previewEl) => {', WIKI_JS)
        self.assertIn('toggleSideBySide()', WIKI_JS)
        self.assertIn('.wiki-editor .EasyMDEContainer', STYLE_CSS)
        self.assertIn('.wiki-editor .EasyMDEContainer .editor-preview-side', STYLE_CSS)
        self.assertIn('.wiki-editor-preview-loading', STYLE_CSS)

    def test_render_wiki_markdown_preview_uses_wiki_renderer(self):
        with tempfile.TemporaryDirectory() as td:
            book = write_wiki_book(Path(td))
            payload = flashcard_app.render_wiki_markdown_preview(
                'pages/intro.md',
                '# 소개 문서\n\n- [x] 체크 항목\n\n[하위 문서](./child.md)\n',
                book,
            )
            self.assertEqual(payload['source_path'], 'pages/intro.md')
            self.assertEqual(payload['page_slug'], 'intro')
            self.assertIn('data-wiki-task-checkbox="1"', payload['html'])
            self.assertIn('/wiki/page/child', payload['html'])

    def test_api_wiki_render_preview_returns_rendered_html(self):
        with tempfile.TemporaryDirectory() as td:
            book = write_wiki_book(Path(td))
            original_book_dir = flashcard_app.WIKI_BOOK_DIR
            try:
                flashcard_app.WIKI_BOOK_DIR = book
                payload = flashcard_app.api_wiki_render_preview(
                    flashcard_app.WikiRenderPreviewRequest(
                        source_path='pages/intro.md',
                        content='# 소개 문서\n\n본문 미리보기\n',
                    )
                )
                self.assertEqual(payload['page_slug'], 'intro')
                self.assertIn('<p>본문 미리보기</p>', payload['html'])
            finally:
                flashcard_app.WIKI_BOOK_DIR = original_book_dir


if __name__ == '__main__':
    unittest.main()
