from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
APP_JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
QUESTION_BANK_JS = (ROOT / 'static' / 'question-bank.js').read_text(encoding='utf-8')
STYLE_CSS = (ROOT / 'static' / 'style.css').read_text(encoding='utf-8')
TABLE_SHELL_CSS = (ROOT / 'static' / 'table-shell.css').read_text(encoding='utf-8')


class QuestionBankKeywordTests(unittest.TestCase):
    def test_question_bank_columns_show_keywords(self):
        self.assertIn("<th scope=\"col\">키워드</th>", INDEX_HTML)
        self.assertIn("{key: 'topic', label: '키워드'", QUESTION_BANK_JS)

    def test_keyword_navigation_helpers_exist(self):
        for snippet in [
            'function normalizeQuestionKeywords(',
            'function findCardByKeyword(',
            'function renderQuestionKeywordLinks(',
            'function goToQuestionKeyword(',
            'card_query=',
            "[data-question-keyword]",
        ]:
            self.assertIn(snippet, APP_JS + QUESTION_BANK_JS)

    def test_keyword_styles_exist(self):
        self.assertIn('.question-keyword-list', STYLE_CSS)
        self.assertIn('.question-keyword-link', STYLE_CSS)
        self.assertIn('.question-keyword-link', TABLE_SHELL_CSS)


if __name__ == '__main__':
    unittest.main()
