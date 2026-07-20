import base64
import csv
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

import app as flashcard_app
from app import mark_card, read_cards, read_csv_cards, save_memo, save_question_attempt, set_bookmark, summarize



BASE_FIELDS = [
    'id', 'term', 'english', 'category', 'definition', 'detailed_explanation',
    'related_concepts', 'source_files', 'exam_note', 'bok_appeared', 'importance', 'difficulty',
]
IMAGE_FIELDS = ['concept_image_url', 'concept_image_alt']
MEDIA_FIELDS = ['concept_media_type', 'concept_media_payload']
REVIEW_FIELDS = ['known_status', 'last_reviewed', 'review_count']


def write_sample(
    path: Path,
    *,
    include_review: bool = False,
    include_image: bool = False,
    include_media: bool = False,
    status: str = '',
    count: str = '0',
    term: str = '테스트',
    english: str = 'Test',
    source_files: str = 'sample.md',
):
    fieldnames = BASE_FIELDS + (IMAGE_FIELDS if include_image else []) + (MEDIA_FIELDS if include_media else []) + (REVIEW_FIELDS if include_review else [])
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        row = {
            'id': 'CS-001',
            'term': term,
            'english': english,
            'category': '소프트웨어공학',
            'definition': '정의',
            'detailed_explanation': '상세',
            'related_concepts': '[[검증]]',
            'source_files': source_files,
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
        if include_media:
            row.update({
                'concept_media_type': 'mermaid',
                'concept_media_payload': 'graph TD\n  A[테스트] --> B[흐름]',
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


def sqlite_card_status(path: Path, card_id: str = 'CS-001') -> dict[str, str]:
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute('SELECT * FROM cards WHERE card_id=?', (card_id,)).fetchone()
    return dict(row) if row else {}

def bootstrap_runtime_db(csv_path: Path | None, db_path: Path) -> None:
    if csv_path is not None and not db_path.exists():
        flashcard_app.bootstrap_cards_from_csv(csv_path, db_path)


def read_cards(csv_path: Path | None, progress_db_path: Path):
    bootstrap_runtime_db(csv_path, progress_db_path)
    return flashcard_app.read_cards(None, progress_db_path)


def mark_card(card_id: str, status: str, csv_path: Path | None, backup_dir: Path, progress_db_path: Path):
    bootstrap_runtime_db(csv_path, progress_db_path)
    return flashcard_app.mark_card(card_id, status, None, backup_dir, progress_db_path)


def set_bookmark(card_id: str, bookmarked: bool, csv_path: Path | None, progress_db_path: Path):
    bootstrap_runtime_db(csv_path, progress_db_path)
    return flashcard_app.set_bookmark(card_id, bookmarked, None, progress_db_path)


def save_memo(card_id: str, memo: str, csv_path: Path | None, progress_db_path: Path):
    bootstrap_runtime_db(csv_path, progress_db_path)
    return flashcard_app.save_memo(card_id, memo, None, progress_db_path)


def save_question_attempt(payload, csv_path: Path | None, progress_db_path: Path):
    bootstrap_runtime_db(csv_path, progress_db_path)
    return flashcard_app.save_question_attempt(payload, None, progress_db_path)



class FakeUrlopenResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False



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

    def test_read_cards_preserves_concept_media_fields(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / 'cards.csv'
            db_path = Path(td) / 'progress.sqlite'
            write_sample(csv_path, include_image=True, include_media=True)
            rows, fields = read_cards(csv_path, db_path)
            self.assertIn('concept_media_type', fields)
            self.assertIn('concept_media_payload', fields)
            self.assertEqual(rows[0]['concept_media_type'], 'mermaid')
            self.assertEqual(rows[0]['concept_media_payload'], 'graph TD\n  A[테스트] --> B[흐름]')

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

    def test_read_cards_flushes_legacy_ai_overrides_into_sqlite(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / 'cards.csv'
            db_path = Path(td) / 'progress.sqlite'
            write_sample(csv_path, include_image=True)
            read_cards(csv_path, db_path)

            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute(
                    """
                    INSERT INTO card_progress (card_id, definition, detailed_explanation, exam_note, concept_image_url, concept_image_alt, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(card_id) DO UPDATE SET
                        definition=excluded.definition,
                        detailed_explanation=excluded.detailed_explanation,
                        exam_note=excluded.exam_note,
                        concept_image_url=excluded.concept_image_url,
                        concept_image_alt=excluded.concept_image_alt,
                        updated_at=excluded.updated_at
                    """,
                    (
                        'CS-001',
                        '레거시 정의',
                        '의미: 레거시 상세. 활용: 레거시 예시.',
                        '레거시 포인트',
                        '/api/ai-images/legacy.png',
                        '레거시 이미지 설명',
                        '2026-07-20T00:00:00+09:00',
                    ),
                )
                conn.commit()

            rows, _ = read_cards(csv_path, db_path)
            self.assertEqual(rows[0]['definition'], '레거시 정의')
            saved = sqlite_card_status(db_path)
            self.assertEqual(saved['definition'], '레거시 정의')
            self.assertEqual(saved['concept_image_url'], '/api/ai-images/legacy.png')
            csv_path.unlink()
            rows, _ = read_cards(csv_path, db_path)
            self.assertEqual(rows[0]['definition'], '레거시 정의')
            with closing(sqlite3.connect(db_path)) as conn:
                legacy = conn.execute(
                    'SELECT definition, detailed_explanation, exam_note, concept_image_url, concept_image_alt FROM card_progress WHERE card_id=?',
                    ('CS-001',),
                ).fetchone()
            self.assertEqual(legacy, ('', '', '', '', ''))

    def test_read_cards_normalizes_legacy_concept_image_urls(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / 'cards.csv'
            db_path = Path(td) / 'progress.sqlite'
            write_sample(csv_path, include_image=True)
            read_cards(csv_path, db_path)

            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute(
                    "UPDATE cards SET concept_image_url=?, concept_media_type='', concept_media_payload='' WHERE card_id=?",
                    ('/api/concept-images/legacy.png', 'CS-001'),
                )
                conn.commit()

            rows, _ = read_cards(None, db_path)
            self.assertEqual(rows[0]['concept_image_url'], '/api/ai-images/legacy.png')


    def test_api_cards_reads_sqlite_when_runtime_csv_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            missing_csv = root / 'missing.csv'
            write_sample(csv_path, include_image=True)
            read_cards(csv_path, db_path)

            original_csv = flashcard_app.CSV_PATH
            original_db = flashcard_app.PROGRESS_DB_PATH
            try:
                flashcard_app.CSV_PATH = missing_csv
                flashcard_app.PROGRESS_DB_PATH = db_path
                data = flashcard_app.api_cards()
            finally:
                flashcard_app.CSV_PATH = original_csv
                flashcard_app.PROGRESS_DB_PATH = original_db

            self.assertEqual(len(data['cards']), 1)
            self.assertEqual(data['cards'][0]['definition'], '정의')
            self.assertEqual(data['cards'][0]['concept_image_url'], 'https://example.com/test-concept.png')
            self.assertEqual(data['summary']['content_db_path'], str(db_path))


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

            with closing(sqlite3.connect(db_path)) as conn:
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

            with closing(sqlite3.connect(db_path)) as conn:
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

            with closing(sqlite3.connect(db_path)) as conn:
                saved = conn.execute('SELECT memo, memo_updated_at FROM card_progress WHERE card_id=?', ('CS-001',)).fetchone()
            self.assertEqual(saved[0], '헷갈리는 개인 메모')
            self.assertTrue(saved[1])

            cleared = save_memo('CS-001', '', csv_path, db_path)
            self.assertEqual(cleared['memo'], '')
            self.assertEqual(cleared['memo_updated_at'], '')

    def test_update_card_ai_content_updates_sqlite_content(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            backup_dir = root / 'backups'
            write_sample(csv_path, include_image=True, include_review=True, status='O', count='2')
            bootstrap_runtime_db(csv_path, db_path)


            updated, backup_path = flashcard_app.update_card_ai_content(
                'CS-001',
                flashcard_app.CardAiApplyRequest(
                    definition='새 정의',
                    detailed_explanation='의미: 더 쉽게 설명합니다. 활용: 면접 답변에 바로 쓰게 정리합니다.',
                    exam_note='비교 포인트까지 함께 말합니다.',
                    concept_image_alt='새 학습 이미지 설명',
                ),
                csv_path,
                backup_dir,
                db_path,
            )

            self.assertEqual(updated['definition'], '새 정의')
            self.assertIsNotNone(backup_path)
            raw = csv_status(csv_path)
            self.assertEqual(raw['definition'], '정의')
            self.assertEqual(raw['concept_image_alt'], '테스트 개념 이해 이미지')
            rows, _ = read_cards(csv_path, db_path)
            self.assertEqual(rows[0]['definition'], '새 정의')
            saved = sqlite_card_status(db_path)
            self.assertEqual(saved['definition'], '새 정의')
            self.assertEqual(saved['concept_image_alt'], '새 학습 이미지 설명')
            csv_path.unlink()
            rows, _ = read_cards(csv_path, db_path)
            self.assertEqual(rows[0]['definition'], '새 정의')
            with closing(sqlite3.connect(db_path)) as conn:
                legacy = conn.execute(
                    'SELECT definition, detailed_explanation, exam_note, concept_image_alt FROM card_progress WHERE card_id=?',
                    ('CS-001',),
                ).fetchone()
            self.assertEqual(legacy, ('', '', '', ''))

    def test_update_card_concept_media_updates_sqlite_content(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            backup_dir = root / 'backups'
            write_sample(csv_path, include_image=True)
            bootstrap_runtime_db(csv_path, db_path)


            updated, backup_path = flashcard_app.update_card_concept_media(
                'CS-001',
                flashcard_app.CardConceptMediaRequest(
                    concept_media_type='html',
                    concept_media_payload='<div class="demo">flow</div><script>document.body.dataset.ready = "1";</script>',
                    concept_image_alt='동적 개념 위젯',
                ),
                csv_path,
                backup_dir,
                db_path,
            )

            self.assertEqual(updated['concept_media_type'], 'html')
            self.assertIn('document.body.dataset.ready', updated['concept_media_payload'])
            self.assertEqual(updated['concept_image_alt'], '동적 개념 위젯')
            self.assertIsNotNone(backup_path)
            saved = sqlite_card_status(db_path)
            self.assertEqual(saved['concept_media_type'], 'html')
            self.assertIn('document.body.dataset.ready', saved['concept_media_payload'])
            self.assertEqual(saved['concept_image_alt'], '동적 개념 위젯')
            self.assertEqual(saved['concept_image_url'], 'https://example.com/test-concept.png')

    def test_rewrite_card_with_codex_parses_json_output(self):
        original_key = flashcard_app.OPENAI_API_KEY
        try:
            flashcard_app.OPENAI_API_KEY = 'test-key'
            with mock.patch.object(
                flashcard_app,
                'urlopen',
                return_value=FakeUrlopenResponse({
                    'output_text': json.dumps({
                        'definition': '새 정의',
                        'detailed_explanation': '의미: 핵심을 정리합니다. 활용: 답변 흐름을 만듭니다.',
                        'exam_note': '관련 개념과 비교합니다.',
                        'concept_image_alt': '학습용 새 이미지 설명',
                    }, ensure_ascii=False),
                }),
            ) as urlopen_mock:
                result = flashcard_app.rewrite_card_with_codex({
                    'id': 'CS-001',
                    'term': '테스트',
                    'definition': '기존 정의',
                    'detailed_explanation': '기존 상세',
                    'exam_note': '기존 포인트',
                    'concept_image_alt': '기존 이미지 설명',
                }, '더 쉽게')
            self.assertEqual(result['definition'], '새 정의')
            self.assertEqual(result['concept_image_alt'], '학습용 새 이미지 설명')
            self.assertIn('/responses', urlopen_mock.call_args.args[0].full_url)
        finally:
            flashcard_app.OPENAI_API_KEY = original_key

    def test_api_card_ai_rewrite_preview_uses_csv_cards(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_sample(csv_path, include_image=True)
            read_cards(csv_path, db_path)

            original_csv = flashcard_app.CSV_PATH
            original_db = flashcard_app.PROGRESS_DB_PATH
            original_key = flashcard_app.OPENAI_API_KEY
            try:
                flashcard_app.CSV_PATH = csv_path
                flashcard_app.PROGRESS_DB_PATH = db_path
                flashcard_app.OPENAI_API_KEY = 'test-key'
                with mock.patch.object(
                    flashcard_app,
                    'urlopen',
                    return_value=FakeUrlopenResponse({
                        'output_text': json.dumps({
                            'definition': '면접형 정의',
                            'detailed_explanation': '의미: 구조적으로 설명합니다. 활용: 실무 예시를 붙입니다.',
                            'exam_note': '비교 질문을 대비합니다.',
                            'concept_image_alt': '면접형 이미지 설명',
                        }, ensure_ascii=False),
                    }),
                ):
                    data = flashcard_app.api_card_ai_rewrite_preview('CS-001', flashcard_app.CardAiRewriteRequest(instruction='면접형'))
                self.assertEqual(data['card_id'], 'CS-001')
                self.assertEqual(data['proposal']['definition'], '면접형 정의')
            finally:
                flashcard_app.CSV_PATH = original_csv
                flashcard_app.PROGRESS_DB_PATH = original_db
                flashcard_app.OPENAI_API_KEY = original_key

    def test_api_card_ai_rewrite_apply_updates_card_content(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_sample(csv_path, include_image=True)
            read_cards(csv_path, db_path)
            original_csv = flashcard_app.CSV_PATH
            original_db = flashcard_app.PROGRESS_DB_PATH
            original_backup = flashcard_app.BACKUP_DIR
            try:
                flashcard_app.CSV_PATH = csv_path
                flashcard_app.PROGRESS_DB_PATH = db_path
                flashcard_app.BACKUP_DIR = root / 'backups'
                data = flashcard_app.api_card_ai_rewrite_apply(
                    'CS-001',
                    flashcard_app.CardAiApplyRequest(
                        definition='적용 정의',
                        detailed_explanation='의미: 적용 테스트입니다. 활용: 저장 흐름을 검증합니다.',
                        exam_note='적용 포인트',
                        concept_image_alt='적용 이미지 설명',
                    ),
                )
                self.assertEqual(data['card']['definition'], '적용 정의')
                self.assertTrue(data['backup_path'])
                self.assertEqual(csv_status(csv_path)['exam_note'], '포인트')
                self.assertEqual(sqlite_card_status(db_path)['exam_note'], '적용 포인트')
                rows, _ = read_cards(csv_path, db_path)
                self.assertEqual(rows[0]['exam_note'], '적용 포인트')
            finally:
                flashcard_app.CSV_PATH = original_csv
                flashcard_app.PROGRESS_DB_PATH = original_db
                flashcard_app.BACKUP_DIR = original_backup

    def test_generate_ai_concept_image_preview_writes_preview_file(self):
        original_key = flashcard_app.OPENAI_API_KEY
        try:
            flashcard_app.OPENAI_API_KEY = 'test-key'
            png_bytes = b'\x89PNG\r\n\x1a\npreview'
            with tempfile.TemporaryDirectory() as td:
                preview_dir = Path(td) / 'previews'
                with mock.patch.object(
                    flashcard_app,
                    'urlopen',
                    return_value=FakeUrlopenResponse({
                        'data': [
                            {'b64_json': base64.b64encode(png_bytes).decode('ascii')},
                        ],
                    }),
                ):
                    preview = flashcard_app.generate_ai_concept_image_preview({
                        'id': 'CS-001',
                        'term': '인수 테스트',
                        'english': 'Acceptance Test',
                        'category': '소프트웨어공학',
                        'definition': '정의',
                        'detailed_explanation': '상세',
                        'related_concepts': '[[검증]]',
                        'concept_image_alt': '기존 이미지 설명',
                    }, preview_dir=preview_dir)
                preview_path, metadata = flashcard_app.read_ai_image_preview(preview['preview_name'], preview_dir=preview_dir)
                self.assertEqual(preview_path.read_bytes(), png_bytes)
                self.assertEqual(metadata['card_id'], 'CS-001')
                self.assertEqual(preview['alt'], '기존 이미지 설명')
                self.assertTrue(preview['preview_url'].endswith(preview['preview_name']))
        finally:
            flashcard_app.OPENAI_API_KEY = original_key

    def test_apply_ai_concept_image_updates_sqlite_and_persists_runtime_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            image_dir = root / 'ai_images'
            preview_dir = root / 'previews'
            backup_dir = root / 'backups'
            write_sample(csv_path, include_image=True)
            bootstrap_runtime_db(csv_path, db_path)

            preview_dir.mkdir(parents=True, exist_ok=True)
            preview_name = 'preview-test.png'
            (preview_dir / preview_name).write_bytes(b'\x89PNG\r\n\x1a\nfinal')
            (preview_dir / 'preview-test.json').write_text(json.dumps({
                'card_id': 'CS-001',
                'alt': 'AI 생성 새 이미지 설명',
            }, ensure_ascii=False), encoding='utf-8')

            updated, backup_path, image_url = flashcard_app.apply_ai_concept_image(
                'CS-001',
                flashcard_app.CardAiImageApplyRequest(preview_name=preview_name),
                csv_path,
                backup_dir,
                db_path,
                image_dir,
                preview_dir,
            )

            self.assertTrue(image_url.startswith('/api/ai-images/CS-001-'))
            self.assertEqual(updated['concept_image_alt'], 'AI 생성 새 이미지 설명')
            self.assertIsNotNone(backup_path)
            saved = sqlite_card_status(db_path)
            self.assertEqual(saved['concept_image_alt'], 'AI 생성 새 이미지 설명')
            self.assertEqual(saved['concept_image_url'], image_url)
            self.assertEqual(saved['concept_media_type'], 'image')
            self.assertEqual(saved['concept_media_payload'], image_url)
            self.assertEqual(csv_status(csv_path)['concept_image_url'], 'https://example.com/test-concept.png')
            rows, _ = read_cards(csv_path, db_path)
            self.assertEqual(rows[0]['concept_image_url'], image_url)
            self.assertEqual(rows[0]['concept_image_alt'], 'AI 생성 새 이미지 설명')
            self.assertEqual(rows[0]['concept_media_type'], 'image')
            self.assertEqual(rows[0]['concept_media_payload'], image_url)
            self.assertFalse((preview_dir / preview_name).exists())
            self.assertEqual(len(list(image_dir.glob('*.png'))), 1)

    def test_api_card_ai_image_preview_and_apply_use_runtime_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            image_dir = root / 'ai_images'
            preview_dir = root / 'previews'
            backup_dir = root / 'backups'
            write_sample(csv_path, include_image=True)
            read_cards(csv_path, db_path)

            original_csv = flashcard_app.CSV_PATH
            original_db = flashcard_app.PROGRESS_DB_PATH
            original_backup = flashcard_app.BACKUP_DIR
            original_image_dir = flashcard_app.AI_IMAGE_DIR
            original_preview_dir = flashcard_app.AI_IMAGE_PREVIEW_DIR
            original_key = flashcard_app.OPENAI_API_KEY
            try:
                flashcard_app.CSV_PATH = csv_path
                flashcard_app.PROGRESS_DB_PATH = db_path
                flashcard_app.BACKUP_DIR = backup_dir
                flashcard_app.AI_IMAGE_DIR = image_dir
                flashcard_app.AI_IMAGE_PREVIEW_DIR = preview_dir
                flashcard_app.OPENAI_API_KEY = 'test-key'
                png_bytes = b'\x89PNG\r\n\x1a\npreview'
                with mock.patch.object(
                    flashcard_app,
                    'urlopen',
                    return_value=FakeUrlopenResponse({
                        'data': [
                            {'b64_json': base64.b64encode(png_bytes).decode('ascii')},
                        ],
                    }),
                ):
                    preview = flashcard_app.api_card_ai_image_preview('CS-001')
                self.assertEqual(preview['card_id'], 'CS-001')
                preview_name = preview['preview_name']
                served_preview = flashcard_app.api_ai_image_preview_file(preview_name)
                self.assertTrue(str(served_preview.path).endswith(preview_name))

                applied = flashcard_app.api_card_ai_image_apply(
                    'CS-001',
                    flashcard_app.CardAiImageApplyRequest(preview_name=preview_name),
                )
                self.assertTrue(applied['image_url'].startswith('/api/ai-images/'))
                served_final = flashcard_app.api_ai_image_file(Path(applied['image_url']).name)
                self.assertTrue(str(served_final.path).endswith('.png'))
            finally:
                flashcard_app.CSV_PATH = original_csv
                flashcard_app.PROGRESS_DB_PATH = original_db
                flashcard_app.BACKUP_DIR = original_backup
                flashcard_app.AI_IMAGE_DIR = original_image_dir
                flashcard_app.AI_IMAGE_PREVIEW_DIR = original_preview_dir
                flashcard_app.OPENAI_API_KEY = original_key

    def test_api_card_concept_media_updates_runtime_sqlite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            backup_dir = root / 'backups'
            write_sample(csv_path, include_image=True)
            read_cards(csv_path, db_path)

            original_csv = flashcard_app.CSV_PATH
            original_db = flashcard_app.PROGRESS_DB_PATH
            original_backup = flashcard_app.BACKUP_DIR
            try:
                flashcard_app.CSV_PATH = csv_path
                flashcard_app.PROGRESS_DB_PATH = db_path
                flashcard_app.BACKUP_DIR = backup_dir
                payload = flashcard_app.CardConceptMediaRequest(
                    concept_media_type='mermaid',
                    concept_media_payload='graph TD\n  A[CPU] --> B[스케줄링]',
                    concept_image_alt='CPU 스케줄링 흐름도',
                )
                result = flashcard_app.api_card_concept_media('CS-001', payload)
                self.assertEqual(result['card']['concept_media_type'], 'mermaid')
                self.assertIn('A[CPU]', result['card']['concept_media_payload'])
                self.assertEqual(result['card']['concept_image_alt'], 'CPU 스케줄링 흐름도')
                saved = sqlite_card_status(db_path)
                self.assertEqual(saved['concept_media_type'], 'mermaid')
            finally:
                flashcard_app.CSV_PATH = original_csv
                flashcard_app.PROGRESS_DB_PATH = original_db
                flashcard_app.BACKUP_DIR = original_backup

    def test_api_card_ai_image_discard_removes_preview_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            preview_dir = root / 'previews'
            write_sample(csv_path, include_image=True)
            read_cards(csv_path, db_path)

            original_csv = flashcard_app.CSV_PATH
            original_db = flashcard_app.PROGRESS_DB_PATH
            original_preview_dir = flashcard_app.AI_IMAGE_PREVIEW_DIR
            original_key = flashcard_app.OPENAI_API_KEY
            try:
                flashcard_app.CSV_PATH = csv_path
                flashcard_app.PROGRESS_DB_PATH = db_path
                flashcard_app.AI_IMAGE_PREVIEW_DIR = preview_dir
                flashcard_app.OPENAI_API_KEY = 'test-key'
                png_bytes = b'\x89PNG\r\n\x1a\npreview'
                with mock.patch.object(
                    flashcard_app,
                    'urlopen',
                    return_value=FakeUrlopenResponse({
                        'data': [
                            {'b64_json': base64.b64encode(png_bytes).decode('ascii')},
                        ],
                    }),
                ):
                    preview = flashcard_app.api_card_ai_image_preview('CS-001')
                flashcard_app.api_card_ai_image_discard(
                    'CS-001',
                    flashcard_app.CardAiImageApplyRequest(preview_name=preview['preview_name']),
                )
                self.assertFalse((preview_dir / preview['preview_name']).exists())
                self.assertFalse((preview_dir / f"{Path(preview['preview_name']).stem}.json").exists())
            finally:
                flashcard_app.CSV_PATH = original_csv
                flashcard_app.PROGRESS_DB_PATH = original_db
                flashcard_app.AI_IMAGE_PREVIEW_DIR = original_preview_dir
                flashcard_app.OPENAI_API_KEY = original_key
    def test_question_attempt_persists_to_sqlite_and_updates_card_stats(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_sample(csv_path)

            first = save_question_attempt(
                flashcard_app.QuestionAttemptRequest(
                    question_id='q-CS-001-short-1',
                    card_id='CS-001',
                    question_type='short',
                    prompt='설명에 해당하는 개념은?',
                    body='정의',
                    user_answer='검증',
                    is_correct=False,
                    judgment='wrong',
                    wrong_note='정의와 용어를 혼동함',
                    session_id='mock-001',
                    session_title='OS/DB 모의 세트 1',
                    session_mode='bok',
                    section='전공필기',
                    points=10,
                    expected_time_seconds=720,
                    answer_guide='정의 → 원리 → 장단점/비교 → 예시 → 금융IT 적용 순으로 5~7문장',
                    question_order=1,
                    question_elapsed_seconds=48,
                    session_elapsed_seconds=48,
                    time_limit_seconds=5400,
                    question_started_at='2026-07-19T09:00:00+09:00',
                    answered_at='2026-07-19T09:00:48+09:00',
                ),
                csv_path,
                db_path,
            )
            self.assertFalse(first['attempt']['is_correct'])
            self.assertEqual(first['attempt']['judgment'], 'wrong')
            self.assertEqual(first['attempt']['wrong_note'], '정의와 용어를 혼동함')
            self.assertEqual(first['attempt']['session_id'], 'mock-001')
            self.assertEqual(first['attempt']['session_title'], 'OS/DB 모의 세트 1')
            self.assertEqual(first['attempt']['session_mode'], 'bok')
            self.assertEqual(first['attempt']['section'], '전공필기')
            self.assertEqual(first['attempt']['points'], 10)
            self.assertEqual(first['attempt']['expected_time_seconds'], 720)
            self.assertEqual(first['attempt']['answer_guide'], '정의 → 원리 → 장단점/비교 → 예시 → 금융IT 적용 순으로 5~7문장')
            self.assertEqual(first['attempt']['question_elapsed_seconds'], 48)
            self.assertEqual(first['attempt']['session_elapsed_seconds'], 48)

            second = save_question_attempt(
                flashcard_app.QuestionAttemptRequest(
                    question_id='q-CS-001-multiple_choice-2',
                    card_id='CS-001',
                    question_type='multiple_choice',
                    prompt='객관식',
                    body='설명',
                    user_answer='테스트',
                    selected_choice_index=1,
                    is_correct=True,
                    judgment='correct',
                    session_id='mock-001',
                    session_title='OS/DB 모의 세트 1',
                    session_mode='bok',
                    section='전공필기',
                    points=10,
                    expected_time_seconds=720,
                    answer_guide='정의 → 원리 → 장단점/비교 → 예시 → 금융IT 적용 순으로 5~7문장',
                    question_order=2,
                    question_elapsed_seconds=22,
                    session_elapsed_seconds=70,
                    time_limit_seconds=5400,
                ),
                csv_path,
                db_path,
            )
            self.assertTrue(second['attempt']['is_correct'])
            self.assertEqual(second['attempt']['judgment'], 'correct')

            third = save_question_attempt(
                flashcard_app.QuestionAttemptRequest(
                    question_id='q-CS-001-subjective-3',
                    card_id='CS-001',
                    question_type='subjective',
                    prompt='장단점 서술',
                    body='비교 설명',
                    user_answer='애매한 답안',
                    is_correct=False,
                    judgment='ambiguous',
                    wrong_note='정의는 맞췄지만 장단점 비교가 빠짐',
                    session_id='mock-001',
                    session_title='OS/DB 모의 세트 1',
                    session_mode='bok',
                    section='전공논술',
                    points=20,
                    expected_time_seconds=3240,
                    answer_guide='정의 → 원리 → 비교 → 사례 → 금융IT 적용 → 결론 순으로 12~15문장',
                    question_order=3,
                    question_elapsed_seconds=95,
                    session_elapsed_seconds=165,
                    time_limit_seconds=5400,
                ),
                csv_path,
                db_path,
            )
            self.assertFalse(third['attempt']['is_correct'])
            self.assertEqual(third['attempt']['judgment'], 'ambiguous')

            rows, _ = read_cards(csv_path, db_path)
            self.assertEqual(rows[0]['question_attempt_count'], 3)
            self.assertEqual(rows[0]['question_correct_count'], 1)
            self.assertEqual(rows[0]['question_wrong_count'], 2)
            self.assertEqual(rows[0]['latest_wrong_note'], '정의는 맞췄지만 장단점 비교가 빠짐')

            with closing(sqlite3.connect(db_path)) as conn:
                saved = conn.execute(
                    'SELECT COUNT(*), SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) FROM question_attempts WHERE card_id=?',
                    ('CS-001',),
                ).fetchone()
            self.assertEqual(saved, (3, 2))

            history_all = flashcard_app.read_question_attempts(csv_path, db_path, card_ids=['CS-001'], result='all', limit=10)
            self.assertEqual(history_all['summary']['total'], 3)
            self.assertEqual(history_all['summary']['correct'], 1)
            self.assertEqual(history_all['summary']['ambiguous'], 1)
            self.assertEqual(history_all['summary']['wrong'], 1)
            self.assertEqual(history_all['items'][0]['card_id'], 'CS-001')

            history_wrong = flashcard_app.read_question_attempts(csv_path, db_path, card_ids=['CS-001'], result='wrong', limit=10)
            self.assertEqual(history_wrong['summary']['wrong'], 1)
            self.assertEqual(len(history_wrong['items']), 1)
            self.assertFalse(history_wrong['items'][0]['is_correct'])
            self.assertEqual(history_wrong['items'][0]['wrong_note'], '정의와 용어를 혼동함')

            history_ambiguous = flashcard_app.read_question_attempts(csv_path, db_path, card_ids=['CS-001'], result='ambiguous', limit=10)
            self.assertEqual(history_ambiguous['summary']['ambiguous'], 1)
            self.assertEqual(len(history_ambiguous['items']), 1)
            self.assertEqual(history_ambiguous['items'][0]['judgment'], 'ambiguous')
            self.assertEqual(history_ambiguous['items'][0]['session_title'], 'OS/DB 모의 세트 1')
            self.assertEqual(history_ambiguous['items'][0]['session_mode'], 'bok')
            self.assertEqual(history_ambiguous['items'][0]['section'], '전공논술')
            self.assertEqual(history_ambiguous['items'][0]['points'], 20)

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

    def test_question_bank_upsert_deduplicates_and_links_attempts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_sample(csv_path)
            bootstrap_runtime_db(csv_path, db_path)


            saved = flashcard_app.upsert_question_bank_entries(
                [
                    {
                        'card_id': 'CS-001',
                        'question_type': 'subjective',
                        'prompt': '정규화의 목적을 설명하시오.',
                        'body': '데이터베이스 설계 관점에서 답하시오.',
                        'answer': '중복을 줄이고 이상 현상을 방지하기 위해 정규화를 수행한다.',
                        'explanation': '삽입/삭제/갱신 이상을 줄이는 것이 핵심이다.',
                        'rubric': ['중복 제거', '이상 현상 방지'],
                        'choices': [],
                        'answer_index': None,
                        'topic': '데이터베이스',
                        'field_name': '전산학술',
                        'category': '데이터베이스',
                        'keywords': '정규화, 이상 현상; 정규화',
                        'difficulty': '중',
                        'issuer': '한국은행',
                        'source_location': '2013년 학술파트 1',
                        'section': '전공필기',
                        'points': 10,
                        'expected_time_seconds': 600,
                        'answer_guide': '정의와 목적을 3문장 이상으로 설명',
                        'session_mode': 'bok',

                    }
                ],
                csv_path,
                db_path,
            )
            self.assertEqual(saved['count'], 1)
            item = saved['items'][0]
            self.assertEqual(item['topic'], '데이터베이스')
            self.assertEqual(item['field_name'], '전산학술')
            self.assertEqual(item['category'], '데이터베이스')

            self.assertEqual(item['issuer'], '한국은행')
            self.assertEqual(item['source_location'], '2013년 학술파트 1')
            self.assertEqual(item['keywords'], ['정규화', '이상 현상'])
            self.assertEqual(item['rubric'], ['중복 제거', '이상 현상 방지'])

            saved_again = flashcard_app.upsert_question_bank_entries(
                [
                    {
                        'card_id': 'CS-001',
                        'question_type': 'subjective',
                        'prompt': '정규화의 목적을 설명하시오.',
                        'body': '데이터베이스 설계 관점에서 답하시오.',
                        'answer': '중복을 줄이고 이상 현상을 방지하기 위해 정규화를 수행한다.',
                        'explanation': '삽입/삭제/갱신 이상을 줄이는 것이 핵심이다.',
                        'rubric': ['중복 제거', '이상 현상 방지'],
                        'choices': [],
                        'answer_index': None,
                        'topic': '데이터베이스',
                        'field_name': '전산학술',
                        'category': '데이터베이스',
                        'keywords': '정규화, 이상 현상; 정규화',
                        'difficulty': '중',
                        'issuer': '한국은행',
                        'source_location': '2013년 학술파트 1',
                        'section': '전공필기',
                        'points': 10,
                        'expected_time_seconds': 600,
                        'answer_guide': '정의와 목적을 3문장 이상으로 설명',
                        'session_mode': 'bok',

                    }
                ],
                csv_path,
                db_path,
            )
            self.assertEqual(saved_again['count'], 1)
            self.assertEqual(saved_again['items'][0]['question_bank_id'], item['question_bank_id'])

            with closing(sqlite3.connect(db_path)) as conn:
                question_bank_count = conn.execute('SELECT COUNT(*) FROM question_bank').fetchone()[0]
            self.assertEqual(question_bank_count, 1)

            attempt = save_question_attempt(
                flashcard_app.QuestionAttemptRequest(
                    question_id='bank-linked-1',
                    question_bank_id=item['question_bank_id'],
                    card_id='CS-001',
                    question_type='subjective',
                    prompt='정규화의 목적을 설명하시오.',
                    body='데이터베이스 설계 관점에서 답하시오.',
                    user_answer='중복 제거와 이상 현상 방지',
                    is_correct=True,
                    judgment='correct',
                ),
                csv_path,
                db_path,
            )
            self.assertEqual(attempt['attempt']['question_bank_id'], item['question_bank_id'])

            listed = flashcard_app.read_question_bank_entries(
                csv_path,
                db_path,
                topic='데이터베이스',
                issuer='한국은행',
                limit=10,
            )
            self.assertEqual(listed['summary']['total'], 1)
            self.assertIn('한국은행', listed['summary']['available_issuers'])
            self.assertIn('데이터베이스', listed['summary']['available_categories'])
            self.assertEqual(listed['items'][0]['question_bank_id'], item['question_bank_id'])

    def test_question_bank_preserves_markdown_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_sample(csv_path)
            bootstrap_runtime_db(csv_path, db_path)


            prompt = '## 제목\n\n다음 그림을 보고 답하시오.\n\n![문제 그림](/static/favicon.svg)'
            body = '- 첫째 줄\n- 둘째 줄\n\n```sql\nSELECT *\nFROM exam_questions;\n```'
            answer = '1. 중복 제거\n2. 이상 현상 방지'
            explanation = '### 해설\n\n|항목|설명|\n|---|---|\n|정규화|중복 감소|'
            answer_guide = '1단락으로 요약하고\n2단락에서 예시를 쓰시오.'

            saved = flashcard_app.upsert_question_bank_entries(
                [
                    {
                        'card_id': 'CS-001',
                        'question_type': 'subjective',
                        'prompt': prompt,
                        'body': body,
                        'answer': answer,
                        'explanation': explanation,
                        'rubric': ['중복 제거'],
                        'topic': '데이터베이스',
                        'field_name': '전산학술',
                        'difficulty': '중',
                        'issuer': '한국은행',
                        'source_location': '2013년 학술파트 2',
                        'answer_guide': answer_guide,
                    }
                ],
                csv_path,
                db_path,
            )
            item = saved['items'][0]
            self.assertEqual(item['prompt'], prompt)
            self.assertEqual(item['body'], body)
            self.assertEqual(item['answer'], answer)
            self.assertEqual(item['explanation'], explanation)
            self.assertEqual(item['answer_guide'], answer_guide)

            listed = flashcard_app.read_question_bank_entries(csv_path, db_path, issuer='한국은행', limit=10)
            self.assertEqual(listed['summary']['total'], 1)
            listed_item = listed['items'][0]
            self.assertEqual(listed_item['prompt'], prompt)
            self.assertEqual(listed_item['body'], body)
            self.assertEqual(listed_item['answer'], answer)
            self.assertEqual(listed_item['explanation'], explanation)
            self.assertEqual(listed_item['answer_guide'], answer_guide)
    def test_parse_bok_question_bank_entries_splits_and_preserves_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wiki_root = root / 'wikidocs-ebook'
            pages = wiki_root / 'pages'
            pages.mkdir(parents=True)
            (pages / '05-14-01-한국은행-2021-컴퓨터공학-학술-파트-I.md').write_text(
                '# 05-14-01. 한국은행 2021 컴퓨터공학 학술 파트 I\n\n'
                '## 2021 파트 I\n\n'
                '### 1. 데이터베이스\n\n'
                '다음 테이블을 보고 답하시오.\n\n'
                '| 항목 | 값 |\n|---|---|\n| PK | 학번 |\n\n'
                '```sql\nSELECT *\nFROM student;\n```\n\n'
                '### 2. 네트워크\n\n'
                'DNS의 기능을 2가지 이상 서술하시오.\n',
                encoding='utf-8',
            )
            (pages / '05-14-03-한국은행-2021-컴퓨터공학-학술-파트-II.md').write_text(
                '# 05-14-03. 한국은행 2021 컴퓨터공학 학술 파트 II\n\n'
                '## 2021 파트 II\n\n'
                '다음을 기술하시오.\n\n'
                '### 유의사항\n\n'
                '1. 답안은 한 페이지 이내로 작성하시오.\n\n'
                '### 문제\n\n'
                '#### 원격근무(VDI) 환경 참고 그림\n\n'
                '![문제 그림](https://example.com/vdi.png)\n\n'
                '현재 원격근무 환경의 한계와 개선방안을 논술하시오.\n',
                encoding='utf-8',
            )
            (pages / '05-14-44-한국은행-2009-전산학술-발췌.md').write_text(
                '# 05-14-44. 한국은행 2009 전산학술 발췌\n\n'
                '## Ⅰ. 다음 문제를 읽고 가장 적당한 답의 기호를 고르시오.\n\n'
                '### 1. 해시 테이블에 대한 다음 설명으로 옳은 것은?\n\n'
                'A. 충돌을 줄이는 방법이다.\n\n'
                'B. 연결 리스트를 이용한 체이닝 기법이다.\n\n'
                'C. 이진 탐색 트리와 동일하다.\n',
                encoding='utf-8',
            )

            entries = flashcard_app.parse_bok_question_bank_entries(wiki_root)
            self.assertEqual(len(entries), 4)

            database = entries[0]
            self.assertEqual(database['prompt'], '### 1. 데이터베이스')
            self.assertEqual(database['question_type'], 'subjective')
            self.assertEqual(database['topic'], '데이터베이스')
            self.assertEqual(database['field_name'], '컴퓨터공학 학술')
            self.assertEqual(database['issuer'], '한국은행')
            self.assertEqual(database['category'], '데이터베이스')
            self.assertEqual(database['answer'], '')
            self.assertEqual(database['explanation'], '')
            self.assertIn('| 항목 | 값 |', database['body'])
            self.assertIn('```sql\nSELECT *\nFROM student;\n```', database['body'])
            self.assertEqual(database['section'], '전공필기')
            self.assertEqual(database['points'], 10)
            self.assertEqual(database['expected_time_seconds'], 12 * 60)
            self.assertEqual(database['session_mode'], 'bok')
            self.assertEqual(database['source_location'], '한국은행 2021 컴퓨터공학 학술 파트 I · 1. 데이터베이스')
            self.assertEqual(database['keywords'], ['데이터베이스'])


            essay = next(item for item in entries if item['question_type'] == 'essay')
            self.assertEqual(essay['prompt'], '### 1. 원격근무(VDI) 환경 참고 그림')
            self.assertIn('### 유의사항', essay['body'])
            self.assertIn('### 문제', essay['body'])
            self.assertEqual(essay['section'], '전공논술')
            self.assertEqual(essay['category'], '클라우드·분산시스템')
            self.assertEqual(essay['points'], 20)
            self.assertEqual(essay['expected_time_seconds'], 54 * 60)
            self.assertEqual(essay['answer'], '')
            self.assertIn('VDI', essay['keywords'])
            self.assertIn('원격근무', essay['keywords'])
            self.assertNotIn('한국은행', essay['keywords'])
            self.assertNotIn('2021', essay['keywords'])


            multiple_choice = next(item for item in entries if item['question_type'] == 'multiple_choice')
            self.assertEqual(multiple_choice['prompt'], '### 1. 해시 테이블에 대한 다음 설명으로 옳은 것은?')
            self.assertEqual(multiple_choice['choices'], ['충돌을 줄이는 방법이다.', '연결 리스트를 이용한 체이닝 기법이다.', '이진 탐색 트리와 동일하다.'])
            self.assertEqual(multiple_choice['answer'], '')
            self.assertEqual(multiple_choice['section'], '전공필기')
            self.assertIsNone(multiple_choice['points'])
            self.assertEqual(multiple_choice['session_mode'], 'bok')
            self.assertEqual(multiple_choice['category'], '자료구조·알고리즘')

    def test_bok_question_bank_keywords_drop_generic_labels(self):
        essay_keywords = flashcard_app.bok_question_bank_keywords(
            '한국은행 2013 일반논술 발췌',
            '제시문 1',
            prompt='### 1. 제시문 1',
            body='인간 본성(human nature)과 성범죄 문제를 다루고 문화적 진화와 DNA를 함께 논한다.',
            category='인공지능·데이터',
            question_type='essay',
        )
        self.assertIn('인간 본성', essay_keywords)
        self.assertIn('성범죄', essay_keywords)
        self.assertNotIn('제시문 1', essay_keywords)
        self.assertNotIn('한국은행', essay_keywords)

        topical_keywords = flashcard_app.bok_question_bank_keywords(
            '한국은행 2025 컴퓨터공학 학술 13. 정보보호: 사회공학, XSS, CSRF',
            '정보보호: 사회공학, XSS, CSRF',
            prompt='### 13. 정보보호: 사회공학, XSS, CSRF',
            body='사회공학, XSS, CSRF 공격 대응 방안을 설명하시오.',
            category='보안',
            question_type='subjective',
        )
        self.assertEqual(topical_keywords[:4], ['정보보호', '사회공학', 'XSS', 'CSRF'])

    def test_sync_bok_question_bank_entries_upserts_empty_answers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            wiki_root = root / 'wikidocs-ebook'
            pages = wiki_root / 'pages'
            pages.mkdir(parents=True)
            write_sample(csv_path)
            bootstrap_runtime_db(csv_path, db_path)

            (pages / '05-14-01-한국은행-2021-컴퓨터공학-학술-파트-I.md').write_text(
                '# 05-14-01. 한국은행 2021 컴퓨터공학 학술 파트 I\n\n'
                '## 2021 파트 I\n\n'
                '### 1. 데이터베이스\n\n'
                '정규화의 장단점을 설명하시오.\n\n'
                '### 2. 네트워크\n\n'
                'DNS의 기능을 2가지 이상 서술하시오.\n',
                encoding='utf-8',
            )
            (pages / '05-14-03-한국은행-2021-컴퓨터공학-학술-파트-II.md').write_text(
                '# 05-14-03. 한국은행 2021 컴퓨터공학 학술 파트 II\n\n'
                '## 2021 파트 II\n\n'
                '다음을 기술하시오.\n\n'
                '### 문제\n\n'
                '#### 원격근무(VDI) 환경 참고 그림\n\n'
                '현재 원격근무 환경의 한계와 개선방안을 논술하시오.\n',
                encoding='utf-8',
            )

            saved = flashcard_app.sync_bok_question_bank_entries(wiki_root, csv_path, db_path)
            self.assertEqual(saved['pages'], 2)
            self.assertEqual(saved['count'], 3)

            saved_again = flashcard_app.sync_bok_question_bank_entries(wiki_root, csv_path, db_path)
            self.assertEqual(saved_again['count'], 3)

            listed = flashcard_app.read_question_bank_entries(csv_path, db_path, issuer='한국은행', limit=10)
            self.assertEqual(listed['summary']['total'], 3)
            self.assertTrue(all(item['answer'] == '' for item in listed['items']))
            self.assertTrue(all(item['session_mode'] == 'bok' for item in listed['items']))
            self.assertTrue(all(item['category'] for item in listed['items']))
            self.assertEqual({item['source_location'] for item in listed['items']}, {
                '한국은행 2021 컴퓨터공학 학술 파트 I · 1. 데이터베이스',
                '한국은행 2021 컴퓨터공학 학술 파트 I · 2. 네트워크',
                '한국은행 2021 컴퓨터공학 학술 파트 II · 1. 원격근무(VDI) 환경 참고 그림',
            })

    def test_api_generate_questions_persists_question_bank_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_sample(csv_path)
            read_cards(csv_path, db_path)

            original_csv = flashcard_app.CSV_PATH
            original_db = flashcard_app.PROGRESS_DB_PATH
            try:
                flashcard_app.CSV_PATH = csv_path
                flashcard_app.PROGRESS_DB_PATH = db_path
                payload = flashcard_app.QuestionGenerateRequest(card_ids=['CS-001'], types=['short'], count=1, seed=7)
                generated = flashcard_app.api_generate_questions(payload)
            finally:
                flashcard_app.CSV_PATH = original_csv
                flashcard_app.PROGRESS_DB_PATH = original_db

            self.assertEqual(len(generated['questions']), 1)
            question = generated['questions'][0]
            self.assertTrue(question['question_bank_id'])
            self.assertEqual(question['topic'], '소프트웨어공학')
            self.assertEqual(question['difficulty'], '중')
            self.assertEqual(question['issuer'], '카드 생성')
            self.assertEqual(question['source_location'], 'sample.md')

            listed = flashcard_app.read_question_bank_entries(csv_path, db_path, card_id='CS-001', limit=10)
            self.assertEqual(listed['summary']['total'], 1)
            self.assertEqual(listed['items'][0]['question_bank_id'], question['question_bank_id'])

    def test_read_question_bank_entries_seeds_demo_and_filters(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_sample(csv_path)
            bootstrap_runtime_db(csv_path, db_path)


            seeded = flashcard_app.read_question_bank_entries(csv_path, db_path, limit=10)
            self.assertEqual(seeded['summary']['total'], 1)
            self.assertEqual(seeded['items'][0]['issuer'], '샘플')
            self.assertEqual(seeded['items'][0]['topic'], '데이터베이스')
            self.assertIn('/static/favicon.svg', seeded['items'][0]['body'])

            filtered = flashcard_app.read_question_bank_entries(
                csv_path,
                db_path,
                issuer='샘플',
                difficulty='중',
                topic='데이터',
                query='정규화',
                limit=10,
            )
            self.assertEqual(filtered['summary']['total'], 1)
            self.assertEqual(filtered['items'][0]['field_name'], '데모')
    def test_old_progress_schema_migrates_for_bookmark_and_memo_columns(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_sample(csv_path)
            with closing(sqlite3.connect(db_path)) as conn:
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

            flashcard_app.bootstrap_cards_from_csv(csv_path, db_path)
            rows, _ = read_cards(csv_path, db_path)
            self.assertEqual(rows[0]['known_status'], 'X')
            self.assertEqual(rows[0]['bookmarked'], '0')
            self.assertEqual(rows[0]['memo'], '')
            with closing(sqlite3.connect(db_path)) as conn:
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

    def test_health_reports_ai_rewrite_config(self):
        original_key = flashcard_app.OPENAI_API_KEY
        original_model = flashcard_app.CODEX_MODEL
        original_image_model = flashcard_app.IMAGE_MODEL
        try:
            flashcard_app.OPENAI_API_KEY = 'test-key'
            flashcard_app.CODEX_MODEL = 'codex-test'
            flashcard_app.IMAGE_MODEL = 'gpt-image-test'
            payload = flashcard_app.health()
            self.assertTrue(payload['ai_rewrite_enabled'])
            self.assertEqual(payload['codex_model'], 'codex-test')
            self.assertEqual(payload['ai_image_model'], 'gpt-image-test')
        finally:
            flashcard_app.OPENAI_API_KEY = original_key
            flashcard_app.CODEX_MODEL = original_model
            flashcard_app.IMAGE_MODEL = original_image_model




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

    def test_read_wiki_page_includes_linked_flashcards(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            book = write_wiki_book(root)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_sample(csv_path, term='소개 문서', english='Intro Document', source_files='pages/intro.md;pages/child.md')
            read_cards(csv_path, db_path)
            original_csv = flashcard_app.CSV_PATH
            original_db = flashcard_app.PROGRESS_DB_PATH
            try:
                flashcard_app.CSV_PATH = csv_path
                flashcard_app.PROGRESS_DB_PATH = db_path
                page = flashcard_app.read_wiki_page('intro', book)
                self.assertEqual(page['primary_card']['id'], 'CS-001')
                self.assertTrue(page['primary_card']['card_url'].startswith('/?card=CS-001'))
                self.assertEqual(page['linked_cards'][0]['term'], '소개 문서')
            finally:
                flashcard_app.CSV_PATH = original_csv
                flashcard_app.PROGRESS_DB_PATH = original_db

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

    def test_api_wiki_page_save_updates_local_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            book = write_wiki_book(Path(td))
            original_repo = flashcard_app.WIKI_GITHUB_REPO
            original_branch = flashcard_app.WIKI_GITHUB_BRANCH
            original_token = flashcard_app.WIKI_GITHUB_TOKEN
            original_prefix = flashcard_app.WIKI_GITHUB_PATH_PREFIX
            original_book_dir = flashcard_app.WIKI_BOOK_DIR
            try:
                flashcard_app.WIKI_BOOK_DIR = book
                flashcard_app.WIKI_GITHUB_REPO = ''
                flashcard_app.WIKI_GITHUB_BRANCH = 'main'
                flashcard_app.WIKI_GITHUB_TOKEN = ''
                flashcard_app.WIKI_GITHUB_PATH_PREFIX = ''
                original = (book / 'pages' / 'intro.md').read_text(encoding='utf-8')
                updated_content = original.replace('# 소개 문서', '# 소개 문서 수정', 1) + '\n수정된 본문입니다.\n'
                response = flashcard_app.api_wiki_page_save(
                    flashcard_app.WikiPageUpdateRequest(
                        source_path='pages/intro.md',
                        content=updated_content,
                        previous_content=original,
                    )
                )
                self.assertEqual(response['updated']['sync_target'], 'local')
                self.assertTrue(response['updated']['changed'])
                self.assertIn('소개 문서 수정', response['page']['html'])
                self.assertIn('수정된 본문입니다.', response['page']['html'])
                saved = (book / 'pages' / 'intro.md').read_text(encoding='utf-8')
                self.assertEqual(saved, updated_content)
            finally:
                flashcard_app.WIKI_GITHUB_REPO = original_repo
                flashcard_app.WIKI_GITHUB_BRANCH = original_branch
                flashcard_app.WIKI_GITHUB_TOKEN = original_token
                flashcard_app.WIKI_GITHUB_PATH_PREFIX = original_prefix
                flashcard_app.WIKI_BOOK_DIR = original_book_dir

    def test_update_wiki_page_source_syncs_github_when_configured(self):
        with tempfile.TemporaryDirectory() as td:
            book = write_wiki_book(Path(td))
            local_text = (book / 'pages' / 'intro.md').read_text(encoding='utf-8')
            updated_content = local_text + '\nGitHub 저장 테스트\n'
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
                        updated = flashcard_app.update_wiki_page_source('pages/intro.md', updated_content, local_text, book)
                fetch_mock.assert_called_once_with('pages/intro.md')
                update_mock.assert_called_once_with('pages/intro.md', updated_content, 'sha123', 'Update wiki page: pages/intro.md')
                self.assertEqual(updated['sync_target'], 'github')
                self.assertTrue(updated['changed'])
                saved = (book / 'pages' / 'intro.md').read_text(encoding='utf-8')
                self.assertEqual(saved, updated_content)
            finally:
                flashcard_app.WIKI_GITHUB_REPO = original_repo
                flashcard_app.WIKI_GITHUB_BRANCH = original_branch
                flashcard_app.WIKI_GITHUB_TOKEN = original_token
                flashcard_app.WIKI_GITHUB_PATH_PREFIX = original_prefix

    def test_update_wiki_page_source_rejects_stale_editor_content(self):
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
                original = (book / 'pages' / 'intro.md').read_text(encoding='utf-8')
                (book / 'pages' / 'intro.md').write_text(original + '\n다른 사용자의 변경\n', encoding='utf-8')
                with self.assertRaisesRegex(RuntimeError, '문서 원본이 다른 내용으로 바뀌어 저장을 중단했습니다'):
                    flashcard_app.update_wiki_page_source('pages/intro.md', original + '\n내 수정\n', original, book)
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

                question_bank_shell = flashcard_app.question_bank_shell()
                self.assertTrue(str(question_bank_shell.path).endswith('static/question-bank.html'))

                raw_response = flashcard_app.api_wiki_raw('pages/intro.md')
                self.assertTrue(str(raw_response.path).endswith('pages/intro.md'))
            finally:
                flashcard_app.WIKI_BOOK_DIR = original_book_dir
if __name__ == '__main__':
    unittest.main()
