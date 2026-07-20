from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
QUESTION_BANK_HTML = (ROOT / 'static' / 'question-bank.html').read_text(encoding='utf-8')
QUESTION_BANK_JS = (ROOT / 'static' / 'question-bank.js').read_text(encoding='utf-8')
TABLE_SHELL_JS = (ROOT / 'static' / 'table-shell.js').read_text(encoding='utf-8')
TABLE_SHELL_CSS = (ROOT / 'static' / 'table-shell.css').read_text(encoding='utf-8')


class TableShellSharedTest(unittest.TestCase):
    def test_question_bank_shell_uses_shared_assets(self):
        self.assertIn('/static/table-shell.css', QUESTION_BANK_HTML)
        self.assertIn('/static/table-shell.js', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageList"', QUESTION_BANK_HTML)
        self.assertIn('열 제목 드래그로 순서 변경', QUESTION_BANK_HTML)

    def test_question_bank_page_uses_shared_renderer(self):
        self.assertIn('QUESTION_BANK_COLUMN_ORDER_KEY', QUESTION_BANK_JS)
        self.assertIn('window.CSTableShell.renderTable', QUESTION_BANK_JS)
        self.assertIn('window.CSTableShell.moveColumnOrder', QUESTION_BANK_JS)
        self.assertIn('QUESTION_BANK_COLUMNS', QUESTION_BANK_JS)

    def test_flashcard_popup_uses_shared_renderer(self):
        self.assertIn('/static/table-shell.css', APP_JS)
        self.assertIn('/static/table-shell.js', APP_JS)
        self.assertIn('window.CSTableShell.renderTable', APP_JS)
        self.assertIn("'__csFlashcardsMoveTableColumn'", APP_JS)
        self.assertIn("'__csFlashcardsTableClosed'", APP_JS)

    def test_shared_table_assets_cover_common_features(self):
        self.assertIn('function moveColumnOrder', TABLE_SHELL_JS)
        self.assertIn('function renderTable', TABLE_SHELL_JS)
        self.assertIn('data-column-key', TABLE_SHELL_JS)
        self.assertIn('.column-header.dragging', TABLE_SHELL_CSS)
        self.assertIn('.cs-table-wrap', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-item-preview', TABLE_SHELL_CSS)


if __name__ == '__main__':
    unittest.main()
