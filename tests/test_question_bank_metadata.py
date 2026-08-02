import app as flashcard_app
import json
import tempfile

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
        self.assertIn('id="bankPageReviewSummary"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageToggleReviewBtn"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageReviewBody"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageReviewStats"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageReviewFilters"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageReviewList"', QUESTION_BANK_HTML)
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
        self.assertIn('function missingCardRows()', QUESTION_BANK_JS)
        self.assertIn('function questionBankReviewRequestPayload(', QUESTION_BANK_JS)
        self.assertIn('function renderQuestionBankReview(', QUESTION_BANK_JS)
        self.assertIn('function ensureQuestionBankReviewLoaded(', QUESTION_BANK_JS)
        self.assertIn('function loadQuestionBankReview(', QUESTION_BANK_JS)
        self.assertIn('function renderMissingCardTable()', QUESTION_BANK_JS)
        self.assertIn('card_query=', QUESTION_BANK_JS)
        self.assertIn('available_topics', QUESTION_BANK_JS)
        self.assertIn('available_field_names', QUESTION_BANK_JS)
        self.assertIn('available_issuers', QUESTION_BANK_JS)
        self.assertIn('available_categories', QUESTION_BANK_JS)
        self.assertIn('missing_cards', QUESTION_BANK_JS)
        self.assertIn('card_created', QUESTION_BANK_JS)
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

    def test_question_bank_service_separates_missing_card_tracking_from_linked_keywords(self):
        fieldnames = flashcard_app.content_fieldnames()
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / 'progress.sqlite'
            flashcard_app.ensure_progress_db(db_path, [
                {
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
                },
                {
                    **{field: '' for field in fieldnames},
                    'id': 'CS-002',
                    'term': '추가 카드',
                    'english': '',
                    'category': '소프트웨어공학',
                    'related_concepts': '',
                    'source_files': 'sample.md',
                    'difficulty': '중',
                    'known_status': '',
                    'last_reviewed': '',
                    'review_count': '0',
                },
            ])
            flashcard_app.upsert_question_bank_entries([
                {
                    'card_id': 'CS-001',
                    'question_type': 'short',
                    'prompt': '### 테스트 문제',
                    'answer': '정답',
                    'explanation': '설명',
                    'topic': '테스트',
                    'field_name': '소프트웨어공학',
                    'category': '소프트웨어공학',
                    'keywords': ['테스트', '검증', '추가 카드', '없는 카드'],
                    'difficulty': '중',
                    'issuer': '한국은행',
                    'source_location': '샘플 위치',
                }
            ], db_path)

            listed = flashcard_app.read_question_bank_entries(db_path, limit=10)
            item = listed['items'][0]
            self.assertEqual(item['keywords'], ['테스트', 'Test', '검증'])
            self.assertEqual(item['missing_card_keywords'], ['추가 카드', '없는 카드'])
            self.assertNotIn('없는 카드', item['keywords'])
            self.assertEqual(listed['summary']['missing_cards'], [
                {'keyword': '추가 카드', 'question_count': 1, 'card_created': True, 'card_id': 'CS-002'},
                {'keyword': '없는 카드', 'question_count': 1, 'card_created': False, 'card_id': ''},
            ])

            missing_query = flashcard_app.read_question_bank_entries(db_path, query='없는 카드', limit=10)
            self.assertEqual(missing_query['summary']['total'], 1)
            self.assertEqual(missing_query['items'][0]['question_bank_id'], item['question_bank_id'])

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

    def test_question_bank_backfill_normalizes_invalid_difficulty_labels(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / 'progress.sqlite'
            flashcard_app.ensure_progress_db(
                db_path,
                seed_rows=[
                    {'id': 'CARD-HIGH', 'term': '고난도 카드', 'category': '테스트', 'difficulty': '상', 'known_status': 'X'},
                    {'id': 'CARD-DEFAULT', 'term': '기본 난이도 카드', 'category': '테스트', 'known_status': 'X'},
                ],
            )
            now = flashcard_app.utc_now_iso()
            with closing(flashcard_app.connect_progress_db(db_path)) as conn:
                conn.executemany(
                    """
                    INSERT INTO question_bank (
                        id, fingerprint, card_id, question_type, prompt, body, answer, explanation,
                        difficulty, issuer, source_location, category, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            'qb-fallback-blank', 'fp-fallback-blank', 'CARD-HIGH', 'short', 'blank difficulty prompt', '', '', '',
                            '', '테스트기관', '테스트출처', '테스트', now, now,
                        ),
                        (
                            'qb-fallback-invalid', 'fp-fallback-invalid', 'CARD-HIGH', 'short', 'invalid difficulty prompt', '', '', '',
                            '어려움', '테스트기관', '테스트출처', '테스트', now, now,
                        ),
                        (
                            'qb-fallback-default', 'fp-fallback-default', 'CARD-DEFAULT', 'short', 'default difficulty prompt', '', '', '',
                            '보통', '테스트기관', '테스트출처', '테스트', now, now,
                        ),
                    ],
                )
                flashcard_app.backfill_question_bank_difficulty_rows(conn)
                conn.commit()
                persisted_rows = conn.execute(
                    "SELECT id, difficulty FROM question_bank WHERE id LIKE 'qb-fallback-%' ORDER BY id"
                ).fetchall()
            persisted = {row['id']: row['difficulty'] for row in persisted_rows}
            self.assertEqual(persisted['qb-fallback-blank'], '상')
            self.assertEqual(persisted['qb-fallback-invalid'], '상')
            self.assertEqual(persisted['qb-fallback-default'], flashcard_app.QUESTION_BANK_DEFAULT_DIFFICULTY)
            listed = flashcard_app.read_question_bank_entries(db_path, query='difficulty prompt', limit=10)
            items_by_id = {item['question_bank_id']: item for item in listed['items']}
            self.assertEqual(items_by_id['qb-fallback-blank']['difficulty'], '상')
            self.assertEqual(items_by_id['qb-fallback-invalid']['difficulty'], '상')
            self.assertEqual(items_by_id['qb-fallback-default']['difficulty'], flashcard_app.QUESTION_BANK_DEFAULT_DIFFICULTY)

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
