from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
QUESTION_BANK_HTML = (ROOT / 'static' / 'question-bank.html').read_text(encoding='utf-8')
APP_JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
QUESTION_BANK_JS = (ROOT / 'static' / 'question-bank.js').read_text(encoding='utf-8')


class QuestionBankMetadataTests(unittest.TestCase):
    def test_question_bank_pages_use_category_and_issuer_selects(self):
        self.assertIn('<select id="bankPageCategoryInput"', QUESTION_BANK_HTML)
        self.assertIn('<select id="bankPageIssuerInput"', QUESTION_BANK_HTML)
        self.assertIn('<select id="questionBankCategoryInput"', INDEX_HTML)
        self.assertIn('<select id="questionBankIssuerInput"', INDEX_HTML)

    def test_question_bank_scripts_populate_category_and_issuer_options(self):
        self.assertIn('function populateIssuerOptions(', QUESTION_BANK_JS)
        self.assertIn('function populateCategoryOptions(', QUESTION_BANK_JS)
        self.assertIn('available_issuers', QUESTION_BANK_JS)
        self.assertIn('available_categories', QUESTION_BANK_JS)
        self.assertIn('function populateQuestionBankIssuerOptions(', APP_JS)
        self.assertIn('function populateQuestionBankCategoryOptions(', APP_JS)
        self.assertIn('available_issuers', APP_JS)
        self.assertIn('available_categories', APP_JS)


if __name__ == '__main__':
    unittest.main()
