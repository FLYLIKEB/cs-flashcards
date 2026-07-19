import base64
import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock



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


def write_wiki_book(root: Path) -> Path:
    book = root / 'wikidocs-ebook'
    pages = book / 'pages'
    pages.mkdir(parents=True, exist_ok=True)
    (book / 'README.md').write_text(
        '# 금공 IT 위키\n\n- [소개 문서](pages/intro.md)\n',
        encoding='utf-8',
    )
    (book / 'TOC.md').write_text(
        '# 목차\n\n- [소개 문서](pages/intro.md)\n  - [하위 문서](pages/child.md)\n',
        encoding='utf-8',
    )
    (pages / 'intro.md').write_text(
        '# 소개 문서\n\n- [ ] 체크 항목\n\n[하위 문서](./child.md)\n\n| 구분 | 내용 |\n| --- | --- |\n| A | B |\n\n```text\nhello\n```\n',
        encoding='utf-8',
    )
    (pages / 'child.md').write_text(
        '# 하위 문서\n\n- 첫 항목\n- 둘째 항목\n',
        encoding='utf-8',
    )
    return book



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
            flashcard_app.AUTH_COOKIE_NAME = 'cs_flashcards_auth'
            self.assertFalse(flashcard_app.is_authorized(None))
            self.assertFalse(flashcard_app.is_authorized('Basic bad-token'))
            header = 'Basic ' + base64.b64encode(b'cs:secret').decode()
            self.assertTrue(flashcard_app.is_authorized(header))
            wrong = 'Basic ' + base64.b64encode(b'cs:wrong').decode()
            self.assertFalse(flashcard_app.is_authorized(wrong))
            cookie_value = flashcard_app.authorized_cookie_value()
            self.assertTrue(flashcard_app.is_authorized_cookie(cookie_value))
            self.assertFalse(flashcard_app.is_authorized_cookie('bad-cookie'))
            self.assertTrue(flashcard_app.is_authorized_request(None, cookie_value))
            self.assertTrue(flashcard_app.is_authorized_request(header, None))
            self.assertFalse(flashcard_app.is_authorized_request(None, None))
        finally:
            flashcard_app.PUBLIC_USERNAME = original_user
            flashcard_app.PUBLIC_PASSWORD = original_password




class WikiBookTests(unittest.TestCase):
    def test_read_wiki_index_and_page_render_internal_links(self):
        with tempfile.TemporaryDirectory() as td:
            book = write_wiki_book(Path(td))
            index = flashcard_app.read_wiki_index(book)
            self.assertEqual(index['book']['title'], '금공 IT 위키')
            self.assertEqual(index['default_page_slug'], 'intro')
            self.assertIn('child', index['pages'])

            page = flashcard_app.read_wiki_page('intro', book)
            self.assertEqual(page['title'], '소개 문서')
            self.assertIn('/wiki/page/child', page['html'])
            self.assertIn('data-wiki-task-checkbox="1"', page['html'])
            self.assertIn('data-wiki-task-source="pages/intro.md"', page['html'])
            self.assertIn('data-wiki-task-line="3"', page['html'])
            self.assertIn('<table>', page['html'])
            self.assertIn('<pre><code class="language-text">hello</code></pre>', page['html'])

    def test_update_wiki_checklist_item_updates_local_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            book = write_wiki_book(Path(td))
            original_repo = flashcard_app.WIKI_GITHUB_REPO
            original_branch = flashcard_app.WIKI_GITHUB_BRANCH
            original_token = flashcard_app.WIKI_GITHUB_TOKEN
            original_prefix = flashcard_app.WIKI_GITHUB_PATH_PREFIX
            try:
                flashcard_app.WIKI_GITHUB_REPO = ''
                flashcard_app.WIKI_GITHUB_BRANCH = 'main'
                flashcard_app.WIKI_GITHUB_TOKEN = ''
                flashcard_app.WIKI_GITHUB_PATH_PREFIX = ''
                updated = flashcard_app.update_wiki_checklist_item('pages/intro.md', 3, True, book)
                self.assertEqual(updated['sync_target'], 'local')
                self.assertTrue(updated['checked'])
                saved = (book / 'pages' / 'intro.md').read_text(encoding='utf-8')
                self.assertIn('- [x] 체크 항목', saved)
                page = flashcard_app.read_wiki_page('intro', book)
                self.assertIn(' checked />', page['html'])
            finally:
                flashcard_app.WIKI_GITHUB_REPO = original_repo
                flashcard_app.WIKI_GITHUB_BRANCH = original_branch
                flashcard_app.WIKI_GITHUB_TOKEN = original_token
                flashcard_app.WIKI_GITHUB_PATH_PREFIX = original_prefix

    def test_update_wiki_checklist_item_syncs_github_when_configured(self):
        with tempfile.TemporaryDirectory() as td:
            book = write_wiki_book(Path(td))
            local_text = (book / 'pages' / 'intro.md').read_text(encoding='utf-8')
            original_repo = flashcard_app.WIKI_GITHUB_REPO
            original_branch = flashcard_app.WIKI_GITHUB_BRANCH
            original_token = flashcard_app.WIKI_GITHUB_TOKEN
            original_prefix = flashcard_app.WIKI_GITHUB_PATH_PREFIX
            try:
                flashcard_app.WIKI_GITHUB_REPO = 'owner/repo'
                flashcard_app.WIKI_GITHUB_BRANCH = 'main'
                flashcard_app.WIKI_GITHUB_TOKEN = 'token'
                flashcard_app.WIKI_GITHUB_PATH_PREFIX = ''
                with mock.patch.object(flashcard_app, 'github_fetch_wiki_source', return_value=(local_text, 'sha123')) as fetch_mock:
                    with mock.patch.object(flashcard_app, 'github_update_wiki_source', return_value={}) as update_mock:
                        updated = flashcard_app.update_wiki_checklist_item('pages/intro.md', 3, True, book)
                fetch_mock.assert_called_once_with('pages/intro.md')
                update_mock.assert_called_once()
                self.assertEqual(update_mock.call_args.args[0], 'pages/intro.md')
                self.assertEqual(updated['sync_target'], 'github')
                saved = (book / 'pages' / 'intro.md').read_text(encoding='utf-8')
                self.assertIn('- [x] 체크 항목', saved)
            finally:
                flashcard_app.WIKI_GITHUB_REPO = original_repo
                flashcard_app.WIKI_GITHUB_BRANCH = original_branch
                flashcard_app.WIKI_GITHUB_TOKEN = original_token
                flashcard_app.WIKI_GITHUB_PATH_PREFIX = original_prefix

    def test_wiki_book_dir_and_health_use_configured_or_fallback_location(self):
        with tempfile.TemporaryDirectory() as td:
            book = write_wiki_book(Path(td))
            original_book_dir = flashcard_app.WIKI_BOOK_DIR
            try:
                flashcard_app.WIKI_BOOK_DIR = book
                self.assertEqual(flashcard_app.wiki_book_dir(), book.resolve())
                payload = flashcard_app.health()
                self.assertTrue(payload['wiki_book_exists'])
                self.assertEqual(payload['wiki_book_dir'], str(book.resolve()))
                self.assertEqual(payload['wiki_book_configured_dir'], str(flashcard_app.WIKI_BOOK_DIR))
            finally:
                flashcard_app.WIKI_BOOK_DIR = original_book_dir

    def test_wiki_route_helpers_serve_local_book(self):
        with tempfile.TemporaryDirectory() as td:
            book = write_wiki_book(Path(td))
            original_book_dir = flashcard_app.WIKI_BOOK_DIR
            try:
                flashcard_app.WIKI_BOOK_DIR = book
                index_payload = flashcard_app.api_wiki_index()
                self.assertEqual(index_payload['default_page_slug'], 'intro')

                page_payload = flashcard_app.api_wiki_page('intro')
                self.assertEqual(page_payload['title'], '소개 문서')

                shell_response = flashcard_app.wiki_page_shell('intro')
                self.assertTrue(str(shell_response.path).endswith('static/wiki.html'))

                raw_response = flashcard_app.api_wiki_raw('pages/intro.md')
                self.assertTrue(str(raw_response.path).endswith('pages/intro.md'))
            finally:
                flashcard_app.WIKI_BOOK_DIR = original_book_dir
if __name__ == '__main__':
    unittest.main()
