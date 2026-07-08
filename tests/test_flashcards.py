import base64
import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

import app as flashcard_app
from app import mark_card, read_cards, read_csv_cards, save_memo, set_bookmark, summarize


BASE_FIELDS = [
    'id', 'term', 'english', 'category', 'definition', 'detailed_explanation',
    'related_concepts', 'source_files', 'exam_note', 'bok_appeared', 'importance', 'difficulty',
]
IMAGE_FIELDS = ['concept_image_url', 'concept_image_alt']
REVIEW_FIELDS = ['known_status', 'last_reviewed', 'review_count']


def write_sample(
    path: Path,
    *,
    include_review: bool = False,
    include_image: bool = False,
    status: str = '',
    count: str = '0',
):
    fieldnames = BASE_FIELDS + (IMAGE_FIELDS if include_image else []) + (REVIEW_FIELDS if include_review else [])
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        row = {
            'id': 'CS-001',
            'term': '테스트',
            'english': 'Test',
            'category': '소프트웨어공학',
            'definition': '정의',
            'detailed_explanation': '상세',
            'related_concepts': '[[검증]]',
            'source_files': 'sample.md',
            'exam_note': '포인트',
            'bok_appeared': 'O',
            'importance': '상',
            'difficulty': '중',
        }
        if include_image:
            row.update({
                'concept_image_url': 'https://example.com/test-concept.png',
                'concept_image_alt': '테스트 개념 이해 이미지',
            })
        if include_review:
            row.update({
                'known_status': status,
                'last_reviewed': '2026-07-08T12:00:00+09:00' if status else '',
                'review_count': count,
            })
        writer.writerow(row)


def csv_status(path: Path) -> dict[str, str]:
    with path.open(encoding='utf-8-sig', newline='') as f:
        return next(csv.DictReader(f))


class FlashcardProgressTests(unittest.TestCase):
    def test_read_cards_adds_review_columns_without_csv_progress(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / 'cards.csv'
            db_path = Path(td) / 'progress.sqlite'
            write_sample(csv_path)
            rows, fields = read_cards(csv_path, db_path)
            self.assertEqual(len(rows), 1)
            self.assertIn('known_status', fields)
            self.assertEqual(rows[0]['known_status'], '')
            self.assertEqual(rows[0]['review_count'], '0')
            self.assertEqual(rows[0]['bookmarked'], '0')
            self.assertEqual(rows[0]['memo'], '')
            self.assertEqual(rows[0]['memo_updated_at'], '')
            self.assertTrue(db_path.exists())


    def test_read_cards_preserves_importance_and_difficulty(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / 'cards.csv'
            db_path = Path(td) / 'progress.sqlite'
            write_sample(csv_path)
            rows, fields = read_cards(csv_path, db_path)
            self.assertIn('bok_appeared', fields)
            self.assertIn('importance', fields)
            self.assertIn('difficulty', fields)
            self.assertEqual(rows[0]['bok_appeared'], 'O')
            self.assertEqual(rows[0]['importance'], '상')
            self.assertEqual(rows[0]['difficulty'], '중')

    def test_read_cards_preserves_concept_image_fields(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / 'cards.csv'
            db_path = Path(td) / 'progress.sqlite'
            write_sample(csv_path, include_image=True)
            rows, fields = read_cards(csv_path, db_path)
            self.assertIn('concept_image_url', fields)
            self.assertIn('concept_image_alt', fields)
            self.assertEqual(rows[0]['concept_image_url'], 'https://example.com/test-concept.png')
            self.assertEqual(rows[0]['concept_image_alt'], '테스트 개념 이해 이미지')

    def test_read_cards_migrates_existing_csv_progress_once(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / 'cards.csv'
            db_path = Path(td) / 'progress.sqlite'
            write_sample(csv_path, include_review=True, status='O', count='4')

            rows, _ = read_cards(csv_path, db_path)
            self.assertEqual(rows[0]['known_status'], 'O')
            self.assertEqual(rows[0]['review_count'], '4')

            # After the DB exists, CSV progress is ignored so future content deploys cannot reapply stale O/X.
            write_sample(csv_path, include_review=True, status='X', count='99')
            rows, _ = read_cards(csv_path, db_path)
            self.assertEqual(rows[0]['known_status'], 'O')
            self.assertEqual(rows[0]['review_count'], '4')

    def test_mark_card_persists_status_to_sqlite_not_csv(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_sample(csv_path)

            updated = mark_card('CS-001', 'O', csv_path, root / 'backups', db_path)
            self.assertEqual(updated['known_status'], 'O')
            self.assertEqual(updated['review_count'], '1')
            self.assertTrue(updated['last_reviewed'])

            raw = csv_status(csv_path)
            self.assertNotIn('known_status', raw)
            self.assertFalse(list((root / 'backups').glob('*.csv')))

            rows, _ = read_cards(csv_path, db_path)
            self.assertEqual(rows[0]['known_status'], 'O')
            summary = summarize(rows)
            self.assertEqual(summary['known'], 1)
            self.assertEqual(summary['unknown'], 0)
            self.assertEqual(summary['unreviewed'], 0)

            with sqlite3.connect(db_path) as conn:
                saved = conn.execute('SELECT known_status, review_count FROM card_progress WHERE card_id=?', ('CS-001',)).fetchone()
            self.assertEqual(saved, ('O', 1))

    def test_bookmark_card_persists_to_sqlite_not_csv(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_sample(csv_path)

            updated = set_bookmark('CS-001', True, csv_path, db_path)
            self.assertEqual(updated['bookmarked'], '1')
            rows, _ = read_cards(csv_path, db_path)
            summary = summarize(rows)
            self.assertEqual(summary['bookmarked'], 1)

            raw = csv_status(csv_path)
            self.assertNotIn('bookmarked', raw)

            with sqlite3.connect(db_path) as conn:
                saved = conn.execute('SELECT bookmarked, known_status, review_count FROM card_progress WHERE card_id=?', ('CS-001',)).fetchone()
            self.assertEqual(saved, (1, '', 0))

            updated = set_bookmark('CS-001', False, csv_path, db_path)
            self.assertEqual(updated['bookmarked'], '0')

    def test_memo_persists_to_sqlite_not_csv(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_sample(csv_path)

            updated = save_memo('CS-001', '헷갈리는 개인 메모', csv_path, db_path)
            self.assertEqual(updated['memo'], '헷갈리는 개인 메모')
            self.assertTrue(updated['memo_updated_at'])
            rows, _ = read_cards(csv_path, db_path)
            summary = summarize(rows)
            self.assertEqual(summary['memo_count'], 1)

            raw = csv_status(csv_path)
            self.assertNotIn('memo', raw)

            with sqlite3.connect(db_path) as conn:
                saved = conn.execute('SELECT memo, memo_updated_at FROM card_progress WHERE card_id=?', ('CS-001',)).fetchone()
            self.assertEqual(saved[0], '헷갈리는 개인 메모')
            self.assertTrue(saved[1])

            cleared = save_memo('CS-001', '', csv_path, db_path)
            self.assertEqual(cleared['memo'], '')
            self.assertEqual(cleared['memo_updated_at'], '')

    def test_mark_card_survives_csv_replacement(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_sample(csv_path)
            mark_card('CS-001', 'X', csv_path, root / 'backups', db_path)

            # Simulate a deployment replacing the content CSV with a clean copy.
            write_sample(csv_path)
            rows, _ = read_cards(csv_path, db_path)
            self.assertEqual(rows[0]['known_status'], 'X')
            self.assertEqual(rows[0]['review_count'], '1')

    def test_old_progress_schema_migrates_for_bookmark_and_memo_columns(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_sample(csv_path)
            with sqlite3.connect(db_path) as conn:
                conn.execute('''
                    CREATE TABLE card_progress (
                        card_id TEXT PRIMARY KEY,
                        known_status TEXT NOT NULL DEFAULT '',
                        last_reviewed TEXT NOT NULL DEFAULT '',
                        review_count INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL
                    )
                ''')
                conn.execute('INSERT INTO card_progress (card_id, known_status, last_reviewed, review_count, updated_at) VALUES (?, ?, ?, ?, ?)', ('CS-001', 'X', '2026-07-08T12:00:00+09:00', 2, '2026-07-08T12:00:00+09:00'))
                conn.commit()

            rows, _ = read_cards(csv_path, db_path)
            self.assertEqual(rows[0]['known_status'], 'X')
            self.assertEqual(rows[0]['bookmarked'], '0')
            self.assertEqual(rows[0]['memo'], '')
            with sqlite3.connect(db_path) as conn:
                columns = {row[1] for row in conn.execute('PRAGMA table_info(card_progress)').fetchall()}
            self.assertIn('bookmarked', columns)
            self.assertIn('memo', columns)
            self.assertIn('memo_updated_at', columns)

    def test_mark_card_can_reset_to_unreviewed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_sample(csv_path)
            marked = mark_card('CS-001', 'X', csv_path, root / 'backups', db_path)
            self.assertEqual(marked['known_status'], 'X')
            reset = mark_card('CS-001', '', csv_path, root / 'backups', db_path)
            self.assertEqual(reset['known_status'], '')
            self.assertEqual(reset['last_reviewed'], '')
            self.assertEqual(reset['review_count'], '1')
            rows, _ = read_cards(csv_path, db_path)
            summary = summarize(rows)
            self.assertEqual(summary['known'], 0)
            self.assertEqual(summary['unknown'], 0)
            self.assertEqual(summary['unreviewed'], 1)

    def test_read_csv_cards_can_view_raw_csv_progress_for_migration(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / 'cards.csv'
            write_sample(csv_path, include_review=True, status='O', count='2')
            raw, _ = read_csv_cards(csv_path, keep_csv_progress=True)
            clean, _ = read_csv_cards(csv_path, keep_csv_progress=False)
            self.assertEqual(raw[0]['known_status'], 'O')
            self.assertEqual(clean[0]['known_status'], '')

    def test_optional_basic_auth_helper(self):
        original_user = flashcard_app.PUBLIC_USERNAME
        original_password = flashcard_app.PUBLIC_PASSWORD
        try:
            flashcard_app.PUBLIC_USERNAME = 'cs'
            flashcard_app.PUBLIC_PASSWORD = 'secret'
            self.assertFalse(flashcard_app.is_authorized(None))
            self.assertFalse(flashcard_app.is_authorized('Basic bad-token'))
            header = 'Basic ' + base64.b64encode(b'cs:secret').decode()
            self.assertTrue(flashcard_app.is_authorized(header))
            wrong = 'Basic ' + base64.b64encode(b'cs:wrong').decode()
            self.assertFalse(flashcard_app.is_authorized(wrong))
        finally:
            flashcard_app.PUBLIC_USERNAME = original_user
            flashcard_app.PUBLIC_PASSWORD = original_password


if __name__ == '__main__':
    unittest.main()
