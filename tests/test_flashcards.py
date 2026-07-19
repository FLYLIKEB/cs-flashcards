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
REVIEW_FIELDS = ['known_status', 'last_reviewed', 'review_count']


def write_sample(
    path: Path,
    *,
    include_review: bool = False,
    include_image: bool = False,
    status: str = '',
    count: str = '0',
    term: str = '테스트',
    english: str = 'Test',
    source_files: str = 'sample.md',
):
    fieldnames = BASE_FIELDS + (IMAGE_FIELDS if include_image else []) + (REVIEW_FIELDS if include_review else [])
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

    def test_update_card_ai_content_rewrites_csv_fields_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            backup_dir = root / 'backups'
            write_sample(csv_path, include_image=True, include_review=True, status='O', count='2')

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
            self.assertTrue(backup_path.exists())
            raw = csv_status(csv_path)
            self.assertEqual(raw['definition'], '새 정의')
            self.assertEqual(raw['concept_image_alt'], '새 학습 이미지 설명')
            self.assertEqual(raw['known_status'], 'O')
            rows, _ = read_cards(csv_path, db_path)
            self.assertEqual(rows[0]['definition'], '새 정의')

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
                self.assertEqual(csv_status(csv_path)['exam_note'], '적용 포인트')
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

    def test_apply_ai_concept_image_updates_csv_and_persists_runtime_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            image_dir = root / 'ai_images'
            preview_dir = root / 'previews'
            backup_dir = root / 'backups'
            write_sample(csv_path, include_image=True)
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
            self.assertTrue(backup_path.exists())
            saved = csv_status(csv_path)
            self.assertEqual(saved['concept_image_alt'], 'AI 생성 새 이미지 설명')
            self.assertEqual(saved['concept_image_url'], image_url)
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

    def test_api_card_ai_image_discard_removes_preview_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            preview_dir = root / 'previews'
            write_sample(csv_path, include_image=True)
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
                    wrong_note='정의와 용어를 혼동함',
                ),
                csv_path,
                db_path,
            )
            self.assertFalse(first['attempt']['is_correct'])
            self.assertEqual(first['attempt']['wrong_note'], '정의와 용어를 혼동함')

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
                ),
                csv_path,
                db_path,
            )
            self.assertTrue(second['attempt']['is_correct'])

            rows, _ = read_cards(csv_path, db_path)
            self.assertEqual(rows[0]['question_attempt_count'], 2)
            self.assertEqual(rows[0]['question_correct_count'], 1)
            self.assertEqual(rows[0]['question_wrong_count'], 1)
            self.assertEqual(rows[0]['latest_wrong_note'], '정의와 용어를 혼동함')

            with closing(sqlite3.connect(db_path)) as conn:
                saved = conn.execute(
                    'SELECT COUNT(*), SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) FROM question_attempts WHERE card_id=?',
                    ('CS-001',),
                ).fetchone()
            self.assertEqual(saved, (2, 1))

            history_all = flashcard_app.read_question_attempts(csv_path, db_path, card_ids=['CS-001'], result='all', limit=10)
            self.assertEqual(history_all['summary']['total'], 2)
            self.assertEqual(history_all['summary']['correct'], 1)
            self.assertEqual(history_all['summary']['wrong'], 1)
            self.assertEqual(history_all['items'][0]['card_id'], 'CS-001')

            history_wrong = flashcard_app.read_question_attempts(csv_path, db_path, card_ids=['CS-001'], result='wrong', limit=10)
            self.assertEqual(history_wrong['summary']['wrong'], 1)
            self.assertEqual(len(history_wrong['items']), 1)
            self.assertFalse(history_wrong['items'][0]['is_correct'])
            self.assertEqual(history_wrong['items'][0]['wrong_note'], '정의와 용어를 혼동함')

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
