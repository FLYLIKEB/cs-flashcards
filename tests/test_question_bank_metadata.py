import app as flashcard_app
import json
import tempfile
from contextlib import closing
from pathlib import Path
import sqlite3
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROGRESS_DB = ROOT / 'state' / 'progress.sqlite'
INDEX_HTML = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
QUESTION_BANK_HTML = (ROOT / 'static' / 'question-bank.html').read_text(encoding='utf-8')
APP_JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
QUESTION_BANK_JS = (ROOT / 'static' / 'question-bank.js').read_text(encoding='utf-8')


class QuestionBankMetadataTests(unittest.TestCase):
    def test_question_bank_pages_use_searchable_topic_and_status_filters(self):
        self.assertIn('<input id="bankPageTopicInput"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageTopicOptions"', QUESTION_BANK_HTML)
        self.assertIn('<select id="bankPageAttemptStatusSelect"', QUESTION_BANK_HTML)
        self.assertIn('<select id="bankPageFieldInput"', QUESTION_BANK_HTML)
        self.assertIn('<select id="bankPageCategoryInput"', QUESTION_BANK_HTML)
        self.assertIn('<select id="bankPageIssuerInput"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageCategoryGuideBtn"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageCategoryGuideDialog"', QUESTION_BANK_HTML)
        self.assertIn('<input id="questionBankTopicInput"', INDEX_HTML)
        self.assertIn('id="questionBankTopicOptions"', INDEX_HTML)
        self.assertIn('<select id="questionBankAttemptStatusSelect"', INDEX_HTML)
        self.assertIn('<select id="questionBankFieldInput"', INDEX_HTML)
        self.assertIn('<select id="questionBankCategoryInput"', INDEX_HTML)
        self.assertIn('<select id="questionBankIssuerInput"', INDEX_HTML)

    def test_question_bank_scripts_populate_category_and_issuer_options_and_keywords(self):
        self.assertIn('function populateTopicOptions(', QUESTION_BANK_JS)
        self.assertIn('function populateFieldNameOptions(', QUESTION_BANK_JS)
        self.assertIn('function populateIssuerOptions(', QUESTION_BANK_JS)
        self.assertIn('function populateCategoryOptions(', QUESTION_BANK_JS)
        self.assertIn('function normalizeQuestionKeywords(', QUESTION_BANK_JS)
        self.assertIn('function renderQuestionKeywordLinks(', QUESTION_BANK_JS)
        self.assertIn('card_query=', QUESTION_BANK_JS)
        self.assertIn('available_topics', QUESTION_BANK_JS)
        self.assertIn('available_field_names', QUESTION_BANK_JS)
        self.assertIn('available_issuers', QUESTION_BANK_JS)
        self.assertIn('available_categories', QUESTION_BANK_JS)
        self.assertIn('category_breakdown', QUESTION_BANK_JS)
        self.assertIn('function populateQuestionBankTopicOptions(', APP_JS)
        self.assertIn('function populateQuestionBankFieldNameOptions(', APP_JS)
        self.assertIn('function populateQuestionBankIssuerOptions(', APP_JS)
        self.assertIn('function populateQuestionBankCategoryOptions(', APP_JS)
        self.assertIn('function findCardByKeyword(', APP_JS)
        self.assertIn('function renderQuestionKeywordLinks(', APP_JS)
        self.assertIn('function goToQuestionKeyword(', APP_JS)
        self.assertIn('available_topics', APP_JS)
        self.assertIn('available_field_names', APP_JS)
        self.assertIn('available_issuers', APP_JS)
        self.assertIn('available_categories', APP_JS)

    def test_question_bank_upsert_response_and_readback_preserve_missing_card_keywords(self):
        fieldnames = flashcard_app.content_fieldnames()
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / 'progress.sqlite'
            flashcard_app.ensure_progress_db(db_path, [{
                **{field: '' for field in fieldnames},
                'id': 'CS-001',
                'term': '테스트',
                'english': 'Test',
                'category': '소프트웨어공학',
                'related_concepts': '[[검증]]',
                'source_files': 'sample.md',
                'difficulty': '중',
                'known_status': '',
                'last_reviewed': '',
                'review_count': '0',
            }])

            saved = flashcard_app.upsert_question_bank_entries([
                {
                    'card_id': 'CS-001',
                    'question_type': 'short',
                    'prompt': '### 테스트 문제',
                    'answer': '정답',
                    'explanation': '설명',
                    'topic': '테스트',
                    'field_name': '소프트웨어공학',
                    'category': '소프트웨어공학',
                    'keywords': ['테스트', '검증', '없는 카드'],
                    'difficulty': '중',
                    'issuer': '한국은행',
                    'source_location': '샘플 위치',
                }
            ], db_path)

            self.assertEqual(saved['items'][0]['keywords'], ['테스트', 'Test', '검증'])
            self.assertEqual(saved['items'][0]['missing_card_keywords'], ['없는 카드'])

            listed = flashcard_app.read_question_bank_entries(db_path, query='없는 카드', limit=10)
            self.assertEqual(listed['items'][0]['keywords'], ['테스트', 'Test', '검증'])
            self.assertEqual(listed['items'][0]['missing_card_keywords'], ['없는 카드'])

    def test_question_bank_missing_card_summary_uses_full_filtered_result_set(self):
        fieldnames = flashcard_app.content_fieldnames()
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / 'progress.sqlite'
            flashcard_app.ensure_progress_db(db_path, [{
                **{field: '' for field in fieldnames},
                'id': 'CS-001',
                'term': '테스트',
                'english': 'Test',
                'category': '소프트웨어공학',
                'related_concepts': '[[검증]]',
                'source_files': 'sample.md',
                'difficulty': '중',
                'known_status': '',
                'last_reviewed': '',
                'review_count': '0',
            }])

            flashcard_app.upsert_question_bank_entries([
                {
                    'card_id': 'CS-001',
                    'question_type': 'short',
                    'prompt': '### 첫 번째 테스트 문제',
                    'answer': '정답',
                    'explanation': '설명',
                    'topic': '테스트',
                    'field_name': '소프트웨어공학',
                    'category': '소프트웨어공학',
                    'keywords': ['테스트', '검증', '없는 카드'],
                    'difficulty': '중',
                },
                {
                    'card_id': 'CS-001',
                    'question_type': 'short',
                    'prompt': '### 두 번째 테스트 문제',
                    'answer': '정답',
                    'explanation': '설명',
                    'topic': '테스트',
                    'field_name': '소프트웨어공학',
                    'category': '소프트웨어공학',
                    'keywords': ['테스트', '없는 카드'],
                    'difficulty': '중',
                },
            ], db_path)

            listed = flashcard_app.read_question_bank_entries(db_path, query='없는 카드', limit=1)
            self.assertEqual(listed['summary']['total'], 2)
            self.assertEqual(listed['summary']['returned'], 1)
            self.assertEqual(listed['summary']['missing_cards'], [
                {'keyword': '없는 카드', 'question_count': 2, 'card_created': False, 'card_id': ''},
            ])

    def test_question_bank_runtime_rows_use_normalized_difficulty_labels(self):
        with closing(sqlite3.connect(PROGRESS_DB)) as conn:
            invalid_count = conn.execute(
                "SELECT COUNT(*) FROM question_bank WHERE trim(coalesce(difficulty, '')) NOT IN ('상', '중', '하')"
            ).fetchone()[0]
        self.assertEqual(invalid_count, 0)

    def test_question_bank_runtime_rows_match_linked_flashcard_keywords(self):
        with closing(sqlite3.connect(PROGRESS_DB)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT qb.card_id, qb.keywords_json, c.term, c.english, c.related_concepts
                FROM question_bank AS qb
                LEFT JOIN cards AS c ON c.card_id = qb.card_id
                """
            ).fetchall()
        mismatches = []
        for row in rows:
            card = {
                'term': row['term'] or '',
                'english': row['english'] or '',
                'related_concepts': row['related_concepts'] or '',
            } if str(row['card_id'] or '').strip() else None
            expected = flashcard_app.question_bank_keywords_for_linked_card(card)
            current = flashcard_app.question_bank_json_list(row['keywords_json'] or '[]')
            if current != expected:
                mismatches.append({
                    'card_id': row['card_id'] or '',
                    'current': current,
                    'expected': expected,
                })
        self.assertEqual(mismatches, [], json.dumps(mismatches[:10], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    unittest.main()
