import csv
import tempfile
import unittest
from pathlib import Path

import cs_flashcards.app as flashcard_app
from cs_flashcards.app import mark_card, read_cards, summarize


def write_sample(path: Path):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'term', 'english', 'category', 'definition', 'detailed_explanation', 'related_concepts', 'source_files', 'exam_note'])
        writer.writeheader()
        writer.writerow({'id': 'CS-001', 'term': '테스트', 'english': 'Test', 'category': '소프트웨어공학', 'definition': '정의', 'detailed_explanation': '상세', 'related_concepts': '[[검증]]', 'source_files': 'sample.md', 'exam_note': '포인트'})


class FlashcardCsvTests(unittest.TestCase):
    def test_read_cards_adds_review_columns(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / 'cards.csv'
            write_sample(csv_path)
            rows, fields = read_cards(csv_path)
            self.assertEqual(len(rows), 1)
            self.assertIn('known_status', fields)
            self.assertEqual(rows[0]['known_status'], '')
            self.assertEqual(rows[0]['review_count'], '0')

    def test_mark_card_persists_status_and_backup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            backup_dir = root / 'backups'
            write_sample(csv_path)
            updated = mark_card('CS-001', 'O', csv_path, backup_dir)
            self.assertEqual(updated['known_status'], 'O')
            self.assertEqual(updated['review_count'], '1')
            rows, _ = read_cards(csv_path)
            self.assertEqual(rows[0]['known_status'], 'O')
            self.assertTrue(rows[0]['last_reviewed'])
            self.assertTrue(list(backup_dir.glob('*.csv')))
            summary = summarize(rows)
            self.assertEqual(summary['known'], 1)
            self.assertEqual(summary['unknown'], 0)
            self.assertEqual(summary['unreviewed'], 0)


    def test_optional_basic_auth_helper(self):
        original_user = flashcard_app.PUBLIC_USERNAME
        original_password = flashcard_app.PUBLIC_PASSWORD
        try:
            flashcard_app.PUBLIC_USERNAME = 'cs'
            flashcard_app.PUBLIC_PASSWORD = 'secret'
            self.assertFalse(flashcard_app.is_authorized(None))
            self.assertFalse(flashcard_app.is_authorized('Basic bad-token'))
            import base64
            header = 'Basic ' + base64.b64encode(b'cs:secret').decode()
            self.assertTrue(flashcard_app.is_authorized(header))
            wrong = 'Basic ' + base64.b64encode(b'cs:wrong').decode()
            self.assertFalse(flashcard_app.is_authorized(wrong))
        finally:
            flashcard_app.PUBLIC_USERNAME = original_user
            flashcard_app.PUBLIC_PASSWORD = original_password


if __name__ == '__main__':
    unittest.main()
