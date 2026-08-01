import base64
import csv
import json
import os
from datetime import datetime, timezone

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

import app as flashcard_app
from app import mark_card, read_cards, save_memo, save_question_attempt, set_bookmark, summarize



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


def seed_rows_from_csv(path: Path) -> list[dict[str, str]]:
    fieldnames = flashcard_app.content_fieldnames()
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        rows: list[dict[str, str]] = []
        for row in reader:
            normalized = {field: (row.get(field) or '') for field in fieldnames}
            if normalized.get('known_status') not in flashcard_app.VALID_STATUSES:
                normalized['known_status'] = ''
            normalized['review_count'] = flashcard_app.normalized_review_count(normalized.get('review_count'))
            rows.append(normalized)
    return rows


def seed_runtime_db(csv_path: Path | None, db_path: Path) -> None:
    if csv_path is not None and not db_path.exists():
        flashcard_app.ensure_progress_db(
            db_path,
            [
                {**row, 'known_status': '', 'last_reviewed': '', 'review_count': '0'}
                for row in seed_rows_from_csv(csv_path)
            ],
        )


def read_cards(csv_path: Path | None, progress_db_path: Path):
    seed_runtime_db(csv_path, progress_db_path)
    return flashcard_app.read_cards(progress_db_path)


def mark_card(card_id: str, status: str, csv_path: Path | None, backup_dir: Path, progress_db_path: Path):
    seed_runtime_db(csv_path, progress_db_path)
    return flashcard_app.mark_card(card_id, status, backup_dir, progress_db_path)


def set_bookmark(card_id: str, bookmarked: bool, csv_path: Path | None, progress_db_path: Path):
    seed_runtime_db(csv_path, progress_db_path)
    return flashcard_app.set_bookmark(card_id, bookmarked, progress_db_path)


def save_memo(card_id: str, memo: str, csv_path: Path | None, progress_db_path: Path):
    seed_runtime_db(csv_path, progress_db_path)
    return flashcard_app.save_memo(card_id, memo, progress_db_path)


def save_question_attempt(payload, csv_path_or_progress_db: Path, progress_db_path: Path | None = None):
    if progress_db_path is None:
        progress_db_path = csv_path_or_progress_db
        sibling_csv_path = progress_db_path.with_name('cards.csv')
        csv_path = sibling_csv_path if sibling_csv_path.exists() else None
    else:
        csv_path = csv_path_or_progress_db
    seed_runtime_db(csv_path, progress_db_path)
    return flashcard_app.save_question_attempt(payload, progress_db_path)



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

    def test_read_cards_ignores_csv_progress_columns(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / 'cards.csv'
            db_path = Path(td) / 'progress.sqlite'
            write_sample(csv_path, include_review=True, status='O', count='4')

            rows, _ = read_cards(csv_path, db_path)
            self.assertEqual(rows[0]['known_status'], '')
            self.assertEqual(rows[0]['review_count'], '0')

            write_sample(csv_path, include_review=True, status='X', count='99')
            rows, _ = read_cards(csv_path, db_path)
            self.assertEqual(rows[0]['known_status'], '')
            self.assertEqual(rows[0]['review_count'], '0')


    def test_read_cards_recovers_saved_ai_image_files(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / 'cards.csv'
            db_path = Path(td) / 'progress.sqlite'
            image_dir = Path(td) / 'ai_images'
            write_sample(csv_path, include_image=True)
            seed_runtime_db(csv_path, db_path)
            image_dir.mkdir(parents=True, exist_ok=True)
            image_name = 'CS-001-20260720-223000-deadbeef.png'
            (image_dir / image_name).write_bytes(b'\x89PNG\r\n\x1a\nrestored')
            original_image_dir = flashcard_app.AI_IMAGE_DIR
            try:
                flashcard_app.AI_IMAGE_DIR = image_dir
                rows, _ = read_cards(None, db_path)
            finally:
                flashcard_app.AI_IMAGE_DIR = original_image_dir
            self.assertEqual(rows[0]['concept_image_url'], f'/api/ai-images/{image_name}')
            self.assertEqual(rows[0]['concept_media_type'], 'image')
            self.assertEqual(rows[0]['concept_media_payload'], f'/api/ai-images/{image_name}')
            saved = sqlite_card_status(db_path)
            self.assertEqual(saved['concept_image_url'], f'/api/ai-images/{image_name}')
            self.assertEqual(saved['concept_media_type'], 'image')
            self.assertEqual(saved['concept_media_payload'], f'/api/ai-images/{image_name}')


    def test_api_cards_reads_sqlite_when_runtime_csv_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            missing_csv = root / 'missing.csv'
            write_sample(csv_path, include_image=True)
            read_cards(csv_path, db_path)
            original_db = flashcard_app.PROGRESS_DB_PATH
            try:
                flashcard_app.PROGRESS_DB_PATH = db_path
                data = flashcard_app.api_cards()
            finally:
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
            seed_runtime_db(csv_path, db_path)


            updated, backup_path = flashcard_app.update_card_ai_content(
                'CS-001',
                flashcard_app.CardAiApplyRequest(
                    definition='새 정의',
                    detailed_explanation='의미: 더 쉽게 설명합니다. 활용: 면접 답변에 바로 쓰게 정리합니다.',
                    exam_note='비교 포인트까지 함께 말합니다.',
                    concept_image_alt='새 학습 이미지 설명',
                ),
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

    def test_update_card_concept_media_updates_sqlite_content(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            backup_dir = root / 'backups'
            write_sample(csv_path, include_image=True)
            seed_runtime_db(csv_path, db_path)


            updated, backup_path = flashcard_app.update_card_concept_media(
                'CS-001',
                flashcard_app.CardConceptMediaRequest(
                    concept_media_type='html',
                    concept_media_payload='<div class="demo">flow</div><script>document.body.dataset.ready = "1";</script>',
                    concept_image_alt='동적 개념 위젯',
                ),
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
            original_db = flashcard_app.PROGRESS_DB_PATH
            original_key = flashcard_app.OPENAI_API_KEY
            try:
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
                flashcard_app.PROGRESS_DB_PATH = original_db
                flashcard_app.OPENAI_API_KEY = original_key

    def test_api_card_ai_rewrite_apply_updates_card_content(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_sample(csv_path, include_image=True)
            read_cards(csv_path, db_path)
            original_db = flashcard_app.PROGRESS_DB_PATH
            original_backup = flashcard_app.BACKUP_DIR
            try:
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
            seed_runtime_db(csv_path, db_path)

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
            original_db = flashcard_app.PROGRESS_DB_PATH
            original_backup = flashcard_app.BACKUP_DIR
            original_image_dir = flashcard_app.AI_IMAGE_DIR
            original_preview_dir = flashcard_app.AI_IMAGE_PREVIEW_DIR
            original_key = flashcard_app.OPENAI_API_KEY
            try:
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
            original_db = flashcard_app.PROGRESS_DB_PATH
            original_backup = flashcard_app.BACKUP_DIR
            try:
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
            original_db = flashcard_app.PROGRESS_DB_PATH
            original_preview_dir = flashcard_app.AI_IMAGE_PREVIEW_DIR
            original_key = flashcard_app.OPENAI_API_KEY
            try:
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

            history_all = flashcard_app.read_question_attempts(db_path, card_ids=['CS-001'], result='all', limit=10)
            self.assertEqual(history_all['summary']['total'], 3)
            self.assertEqual(history_all['summary']['correct'], 1)
            self.assertEqual(history_all['summary']['ambiguous'], 1)
            self.assertEqual(history_all['summary']['wrong'], 1)
            self.assertEqual(history_all['items'][0]['card_id'], 'CS-001')

            history_wrong = flashcard_app.read_question_attempts(db_path, card_ids=['CS-001'], result='wrong', limit=10)
            self.assertEqual(history_wrong['summary']['wrong'], 1)
            self.assertEqual(len(history_wrong['items']), 1)
            self.assertFalse(history_wrong['items'][0]['is_correct'])
            self.assertEqual(history_wrong['items'][0]['wrong_note'], '정의와 용어를 혼동함')

            history_ambiguous = flashcard_app.read_question_attempts(db_path, card_ids=['CS-001'], result='ambiguous', limit=10)
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
            seed_runtime_db(csv_path, db_path)


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
                db_path,
            )
            self.assertEqual(attempt['attempt']['question_bank_id'], item['question_bank_id'])

            listed = flashcard_app.read_question_bank_entries(
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
            seed_runtime_db(csv_path, db_path)


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
                db_path,
            )
            item = saved['items'][0]
            self.assertEqual(item['prompt'], prompt)
            self.assertEqual(item['body'], body)
            self.assertEqual(item['answer'], answer)
            self.assertEqual(item['explanation'], explanation)
            self.assertEqual(item['answer_guide'], answer_guide)

            listed = flashcard_app.read_question_bank_entries(db_path, issuer='한국은행', limit=10)
            self.assertEqual(listed['summary']['total'], 1)
            listed_item = listed['items'][0]
            self.assertEqual(listed_item['prompt'], prompt)
            self.assertEqual(listed_item['body'], body)
            self.assertEqual(listed_item['answer'], answer)
            self.assertEqual(listed_item['explanation'], explanation)
            self.assertEqual(listed_item['answer_guide'], answer_guide)
    def test_parse_fin_corp_question_bank_entries_extracts_answers_and_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            wiki_root = root / 'wikidocs-ebook'
            pages = wiki_root / 'pages'
            pages.mkdir(parents=True)

            with csv_path.open('w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=BASE_FIELDS)
                writer.writeheader()
                for row in [
                    {
                        'id': 'CS-001',
                        'term': '프라이빗 블록체인',
                        'english': 'Private Blockchain',
                        'category': '금융IT·신기술',
                        'definition': '허가형 참여자로 제한하는 블록체인이다.',
                        'detailed_explanation': '운영 주체가 명확하고 접근 권한을 통제한다.',
                        'related_concepts': '[[블록체인]], [[퍼블릭 블록체인]]',
                        'source_files': 'pages/05-01-우리은행-기출.md',
                        'exam_note': '퍼블릭과 비교',
                        'bok_appeared': '',
                        'importance': '상',
                        'difficulty': '중',
                    },
                    {
                        'id': 'CS-002',
                        'term': '형상관리',
                        'english': 'Configuration Management',
                        'category': '소프트웨어공학',
                        'definition': '버전과 변경 이력을 통제한다.',
                        'detailed_explanation': '기준선, 변경 통제, 릴리스 구성을 관리한다.',
                        'related_concepts': '[[버전관리]], [[변경관리]]',
                        'source_files': 'pages/05-04-금융결제원-기출.md',
                        'exam_note': '형상관리자 역할',
                        'bok_appeared': '',
                        'importance': '상',
                        'difficulty': '하',
                    },
                ]:
                    writer.writerow(row)
            seed_runtime_db(csv_path, db_path)

            (pages / '05-01-우리은행-기출.md').write_text(
                '# 05-01. 우리은행 기출\n\n'
                '### 1. 프라이빗 블록체인의 특징으로 옳지 않은 것은?\n'
                '1. 분산형으로 네트워크 운영과 관리가 각각 이루어진다.\n'
                '2. 퍼블릭보다 합의 알고리즘이 경량화될 수 있다.\n'
                '3. 허가된 참여자만 접근할 수 있다.\n\n'
                '  **답:** 1번\n'
                '- 프라이빗 블록체인은 운영 주체가 명확하고 접근을 통제한다.\n\n'
                '### 2. 1 Petabyte의 크기는?\n\n'
                '  **답:** 1,024 TB\n',
                encoding='utf-8',
            )
            (pages / '05-04-금융결제원-기출.md').write_text(
                '# 05-04. 금융결제원 기출\n\n'
                '### 147. 형상관리자 역할은?\n'
                '**답(AI답변):** 형상관리자는 변경 이력, 버전, 기준선과 릴리스 구성을 관리한다.\n',
                encoding='utf-8',
            )

            entries = flashcard_app.parse_fin_corp_question_bank_entries(wiki_root, db_path)
            self.assertEqual(len(entries), 3)

            multiple_choice = entries[0]
            self.assertEqual(multiple_choice['question_bank_id'], 'qb-fin239-05-01-01')
            self.assertEqual(multiple_choice['card_id'], 'CS-001')
            self.assertEqual(multiple_choice['question_type'], 'multiple_choice')
            self.assertEqual(multiple_choice['choices'], [
                '분산형으로 네트워크 운영과 관리가 각각 이루어진다.',
                '퍼블릭보다 합의 알고리즘이 경량화될 수 있다.',
                '허가된 참여자만 접근할 수 있다.',
            ])
            self.assertEqual(multiple_choice['answer'], '1번')
            self.assertEqual(multiple_choice['answer_index'], 0)
            self.assertIn('운영 주체가 명확', multiple_choice['explanation'])
            self.assertEqual(multiple_choice['field_name'], flashcard_app.FIN_CORP_FIELD_NAME)
            self.assertEqual(multiple_choice['section'], '전공필기')
            self.assertEqual(multiple_choice['session_mode'], 'practice')
            self.assertEqual(multiple_choice['difficulty'], '중')
            self.assertEqual(multiple_choice['points'], flashcard_app.FIN_CORP_MULTIPLE_CHOICE_POINTS)
            self.assertEqual(multiple_choice['expected_time_seconds'], flashcard_app.FIN_CORP_MULTIPLE_CHOICE_EXPECTED_SECONDS)
            self.assertTrue(multiple_choice['answer_guide'])
            self.assertEqual(multiple_choice['issuer'], '우리은행')
            self.assertIn('프라이빗 블록체인', multiple_choice['keywords'])
            self.assertEqual(multiple_choice['body'], '')

            short = entries[1]
            self.assertEqual(short['question_type'], 'short')
            self.assertEqual(short['answer'], '1,024 TB')
            self.assertEqual(short['category'], '컴퓨터구조')
            self.assertEqual(short['difficulty'], '하')
            self.assertEqual(short['points'], flashcard_app.FIN_CORP_SHORT_POINTS)
            self.assertEqual(short['expected_time_seconds'], flashcard_app.FIN_CORP_SHORT_EXPECTED_SECONDS)

            subjective = entries[2]
            self.assertEqual(subjective['card_id'], 'CS-002')
            self.assertEqual(subjective['issuer'], '금융결제원')
            self.assertEqual(subjective['question_type'], 'subjective')
            self.assertTrue(subjective['answer'])
            self.assertTrue(subjective['explanation'])
            self.assertEqual(subjective['difficulty'], '하')
            self.assertEqual(subjective['source_location'], '금융결제원 기출 · 147. 형상관리자 역할은?')

    def test_sync_fin_corp_question_bank_entries_upserts_parsed_pages(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            wiki_root = root / 'wikidocs-ebook'
            pages = wiki_root / 'pages'
            pages.mkdir(parents=True)

            with csv_path.open('w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=BASE_FIELDS)
                writer.writeheader()
                writer.writerow({
                    'id': 'CS-001',
                    'term': '프라이빗 블록체인',
                    'english': 'Private Blockchain',
                    'category': '금융IT·신기술',
                    'definition': '허가형 참여자로 제한하는 블록체인이다.',
                    'detailed_explanation': '운영 주체가 명확하고 접근 권한을 통제한다.',
                    'related_concepts': '[[블록체인]]',
                    'source_files': 'pages/05-01-우리은행-기출.md',
                    'exam_note': '퍼블릭과 비교',
                    'bok_appeared': '',
                    'importance': '상',
                    'difficulty': '중',
                })
            seed_runtime_db(csv_path, db_path)

            (pages / '05-01-우리은행-기출.md').write_text(
                '# 05-01. 우리은행 기출\n\n'
                '### 1. 프라이빗 블록체인의 특징으로 옳지 않은 것은?\n'
                '1. 분산형으로 네트워크 운영과 관리가 각각 이루어진다.\n'
                '2. 퍼블릭보다 합의 알고리즘이 경량화될 수 있다.\n\n'
                '  **답:** 1번\n'
                '- 프라이빗 블록체인은 운영 주체가 명확하고 접근을 통제한다.\n\n'
                '### 2. 1 Petabyte의 크기는?\n\n'
                '  **답:** 1,024 TB\n',
                encoding='utf-8',
            )
            (pages / '05-04-금융결제원-기출.md').write_text(
                '# 05-04. 금융결제원 기출\n\n'
                '### 147. 형상관리자 역할은?\n'
                '**답(AI답변):** 형상관리자는 변경 이력, 버전, 기준선과 릴리스 구성을 관리한다.\n',
                encoding='utf-8',
            )

            saved = flashcard_app.sync_fin_corp_question_bank_entries(wiki_root, db_path)
            self.assertEqual(saved['pages'], 2)
            self.assertEqual(saved['count'], 3)

            saved_again = flashcard_app.sync_fin_corp_question_bank_entries(wiki_root, db_path)
            self.assertEqual(saved_again['count'], 3)

            listed = flashcard_app.read_question_bank_entries(db_path, field_name=flashcard_app.FIN_CORP_FIELD_NAME, limit=10)
            self.assertEqual(listed['summary']['total'], 3)
            self.assertEqual({item['issuer'] for item in listed['items']}, {'우리은행', '금융결제원'})
            self.assertTrue(all(item['question_bank_id'].startswith('qb-fin239-') for item in listed['items']))
            self.assertTrue(all(item['answer'] for item in listed['items']))
            self.assertTrue(all(item['difficulty'] in {'상', '중', '하'} for item in listed['items']))
            self.assertTrue(all(item['source_location'] for item in listed['items']))
            self.assertTrue(all(item['answer_guide'] for item in listed['items']))

    def test_parse_fin_corp_question_bank_entries_fixes_wrapped_titles_inline_choices_and_ai_misanswers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            wiki_root = root / 'wikidocs-ebook'
            pages = wiki_root / 'pages'
            pages.mkdir(parents=True)

            with csv_path.open('w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=BASE_FIELDS)
                writer.writeheader()
                for row in [
                    {
                        'id': 'CS-101',
                        'term': '동적 계획법',
                        'english': 'Dynamic Programming',
                        'category': '자료구조·알고리즘',
                        'definition': '중복되는 부분 문제의 답을 저장해 전체 문제를 푸는 알고리즘 기법이다.',
                        'detailed_explanation': '최적 부분 구조와 중복 부분 문제를 활용하며 Top-down 메모이제이션과 Bottom-up 테이블 방식으로 구현한다.',
                        'related_concepts': '[[메모이제이션]], [[탭퓰레이션]]',
                        'source_files': 'pages/05-08-산업은행-기출.md',
                        'exam_note': '점화식을 세우고 기저 사례를 먼저 확인한다.',
                        'bok_appeared': '',
                        'importance': '상',
                        'difficulty': '상',
                    },
                    {
                        'id': 'CS-201',
                        'term': 'ACID',
                        'english': '',
                        'category': '데이터베이스',
                        'definition': '원자성, 일관성, 고립성, 지속성을 뜻한다.',
                        'detailed_explanation': '트랜잭션의 신뢰성을 보장하는 성질이다.',
                        'related_concepts': '[[트랜잭션]], [[일관성]]',
                        'source_files': 'pages/05-08-산업은행-기출.md',
                        'exam_note': '',
                        'bok_appeared': '',
                        'importance': '상',
                        'difficulty': '중',
                    },
                ]:
                    writer.writerow(row)
            seed_runtime_db(csv_path, db_path)

            (pages / '05-08-산업은행-기출.md').write_text(
                '# 05-08. 산업은행 기출\n\n'
                '### 2. 빅데이터 3V 중에 아닌 것은?\n'
                '1. Volume 2.Veracity 3.Variety 4.Vividity\n\n'
                '**답:** 4번\n\n'
                '### 74. 두 트랜잭션이 동시에 실행될 때, 한 트랜잭션이 아직 commit되지 않은 데이터를 다른 트랜잭션이 읽는\n'
                '경우 발생하는 문제는?\n'
                '1. Dirty Read\n'
                '2. Lost Update\n'
                '3. Phantom Read\n'
                '4. Non Repeatable Read\n\n'
                '**답:** 1번\n\n'
                '### 91. 베스천 호스트(Bastion Host)에 관해 틀린 내용은?\n'
                '1. 침입 차단 소프트웨어가 설치되어 내부와 외부 네트워크 사이에서 일종의 게이트 역할을 수행하는 호스트\n'
                '2. 배스천 호스트는 방화벽 시스템이 가지는 기능 중 가장 중요한 기능을 제공\n'
                '3. 배스천(Bastion)은 중세시대에 성 외곽을 보호하기 위해 돌출된 부분을 의미\n'
                '- 위 3개 지문은 모두 옳은 지문임.\n'
                '**답(AI답변):** 베스천 호스트는 외부망과 내부망 사이에서 보안 관문 역할을 하는 강화된 서버다.\n\n'
                '### 107. 서버 가상화 기술에 대해 옳지 않은 것은?\n'
                '1. 가상화 대상이 되는 컴퓨터 자원은 프로세서, 메모리, 스토리지, 네트워크를 포함한다\n'
                '2. 가상화 기술 종류는 서버가상화, 데스크톱 가상화, 애플리케이션 가상화이다\n'
                '**답:** 해당 지문은 모두 옳은 선지임.\n\n'
                '### 161. 클래스 설계원칙에 대한 바른 설명은?\n'
                '1. 단일 책임 원칙: 하나의 클래스는 오직 하나의 책임만 가져야 한다.\n'
                '2. 개방-폐쇄 원칙: 클래스는 확장에는 열려 있어야 하며, 변경에는 닫혀 있어야 한다.\n'
                '3. 리스코프 교체 원칙: 서브타입은 언제나 자신의 기반 타입으로 교체할 수 있어야 한다.\n'
                '4. 의존성 역전 원칙: 고수준 모듈은 저수준 모듈에 의존해서는 안 되며, 둘 다 추상화에 의존해야 한다.\n\n'
                '**답:** 모든선지가 맞음\n\n'
                '### 132. GPU 특징\n'
                '**답(AI답변):** GPU는 많은 코어로 병렬 연산에 특화되어 그래픽 처리, AI 학습, 행렬 연산 등에 강하다.\n\n'
                '### 236. 다음은 동적 계획법(Dynamic Programming)을 이용하여 어떤 값을 계산하는 함수이다. 빈칸 ㄱ, ㄴ에\n\n'
                '들어갈 코드를 작성하시오.\n\n'
                '```\n'
                'def solve(n, arr):\n'
                '    dp =[-1] * n\n'
                '```\n\n'
                '```\n'
                'def dfs(i):\n'
                '    if i < 0:\n'
                '        return 0\n'
                '    if i == 0:\n'
                '        return arr[0]\n'
                '    if dp[i] != -1:\n'
                '        return dp[i]\n'
                '```\n\n'
                '```\n'
                '    dp[i] = ㄱ\n'
                '    return dp[i]\n'
                '```\n\n'
                '```\n'
                '# Bottom-up 방식\n'
                'dp2 =[0] * n\n'
                'dp2[0] = arr[0]\n'
                'dp2[1] = max(arr[0], arr[1])\n'
                '```\n\n'
                '```\n'
                'for i in range(2, n):\n'
                '    dp2[i] = ㄴ\n'
                '```\n\n'
                '```\n'
                'return dp2[n-1]\n'
                '```\n'
                '**답(AI답변):** DP는 중복 부분문제와 최적 부분구조를 이용해 결과를 저장하며 푸는 기법이다. Top-down은 재귀+메모이제이션, Bottom-up은 반복문 테이블 채움 방식이다.\n\n'
                '### 237. 동적 계획법(Dynamic Programming)의 개념과 Top-down, Bottom-up 방식의 차이를 설명하시오.\n'
                '**답(AI답변):** 인터넷망을 통해 방송·영상 콘텐츠를 제공하는 서비스로 Netflix, YouTube 등이 예시다.\n\n'
                '### 238. SQL문 약술\n'
                '**답(AI답변):** SQL은 데이터를 정의하고 조작하는 언어다.\n',
                encoding='utf-8',
            )

            entries = flashcard_app.parse_fin_corp_question_bank_entries(wiki_root, db_path)
            by_prompt = {item['prompt']: item for item in entries}

            inline = by_prompt['### 2. 빅데이터 3V 중에 아닌 것은?']
            self.assertEqual(inline['choices'], ['Volume', 'Veracity', 'Variety', 'Vividity'])
            self.assertEqual(inline['answer_index'], 3)
            self.assertEqual(inline['body'], '')

            wrapped = by_prompt['### 74. 두 트랜잭션이 동시에 실행될 때, 한 트랜잭션이 아직 commit되지 않은 데이터를 다른 트랜잭션이 읽는 경우 발생하는 문제는?']
            self.assertEqual(wrapped['source_location'], '산업은행 기출 · 74. 두 트랜잭션이 동시에 실행될 때, 한 트랜잭션이 아직 commit되지 않은 데이터를 다른 트랜잭션이 읽는 경우 발생하는 문제는?')
            self.assertEqual(wrapped['answer_index'], 0)

            gpu = by_prompt['### 132. GPU 특징']
            self.assertEqual(gpu['category'], '컴퓨터구조')

            all_true = by_prompt['### 91. 베스천 호스트(Bastion Host)에 관해 틀린 내용은?']
            self.assertEqual(all_true['choices'][-1], '위 3개 지문은 모두 옳은 지문임.')
            self.assertEqual(all_true['answer_index'], 3)
            self.assertEqual(all_true['answer'], '4번')

            all_true_answer = by_prompt['### 107. 서버 가상화 기술에 대해 옳지 않은 것은?']
            self.assertEqual(all_true_answer['choices'][-1], '해당 지문은 모두 옳은 선지임.')
            self.assertEqual(all_true_answer['answer'], '3번')
            self.assertEqual(all_true_answer['answer_index'], 2)

            all_true_direct = by_prompt['### 161. 클래스 설계원칙에 대한 바른 설명은?']
            self.assertEqual(all_true_direct['choices'][-1], '모든선지가 맞음')
            self.assertEqual(all_true_direct['answer'], '5번')
            self.assertEqual(all_true_direct['answer_index'], 4)
            self.assertEqual(all_true_direct['body'], '')

            coding = by_prompt['### 236. 다음은 동적 계획법(Dynamic Programming)을 이용하여 어떤 값을 계산하는 함수이다. 빈칸 ㄱ, ㄴ에 들어갈 코드를 작성하시오.']
            self.assertEqual(coding['card_id'], 'CS-101')
            self.assertEqual(coding['body'].count('```'), 2)
            self.assertIn('dp[i] = ㄱ', coding['body'])
            self.assertIn('dp2[i] = ㄴ', coding['body'])
            self.assertIn('dfs(i - 1)', coding['answer'])
            self.assertIn('dp2[i - 2] + arr[i]', coding['answer'])
            self.assertEqual(coding['category'], '자료구조·알고리즘')

            repaired = by_prompt['### 237. 동적 계획법(Dynamic Programming)의 개념과 Top-down, Bottom-up 방식의 차이를 설명하시오.']
            self.assertEqual(repaired['card_id'], 'CS-101')
            self.assertNotIn('Netflix', repaired['answer'])
            self.assertIn('중복되는 부분 문제', repaired['answer'])
            self.assertIn('메모이제이션', repaired['explanation'])
            self.assertEqual(repaired['category'], '자료구조·알고리즘')

            sql_short = by_prompt['### 238. SQL에 대해 설명하시오.']
            self.assertEqual(sql_short['card_id'], '')
            self.assertEqual(sql_short['category'], '데이터베이스')

    def test_parse_fin_corp_question_bank_entries_preserves_context_and_strips_duplicate_choices(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_path = root / 'progress.sqlite'
            wiki_root = root / 'wikidocs-ebook'
            pages = wiki_root / 'pages'
            pages.mkdir(parents=True)

            flashcard_app.ensure_progress_db(
                db_path,
                seed_rows=[
                    {
                        'id': 'CS-900',
                        'term': '리스트 append',
                        'english': 'List Append',
                        'category': '프로그래밍 언어',
                        'definition': '파이썬 리스트 끝에 원소를 추가하는 메서드다.',
                        'detailed_explanation': 'append는 리스트 자체를 수정하고 새 길이를 반환하지 않는다.',
                        'related_concepts': '[[리스트]], [[Python]]',
                        'source_files': 'pages/05-02-IBK기업은행-기출.md',
                        'exam_note': '',
                        'bok_appeared': '',
                        'importance': '하',
                        'difficulty': '하',
                    },
                ],
            )
            (pages / '05-02-IBK기업은행-기출.md').write_text(
                '# 05-02. IBK기업은행 기출\n\n'
                '### 56. 다음 코드의 실행 결과는?\n'
                '```python\n'
                'values = [1, 2]\n'
                'values.append(3)\n'
                'print(values)\n'
                '```\n'
                '1. [1, 2]\n'
                '2. [1, 2, 3]\n'
                '3. [3, 2, 1]\n'
                '4. 오류 발생\n\n'
                '**답:** 2번\n',
                encoding='utf-8',
            )

            entry = flashcard_app.parse_fin_corp_question_bank_entries(wiki_root, db_path)[0]

            self.assertEqual(entry['question_type'], 'multiple_choice')
            self.assertEqual(entry['choices'], ['[1, 2]', '[1, 2, 3]', '[3, 2, 1]', '오류 발생'])
            self.assertEqual(entry['answer_index'], 1)
            self.assertIn('```python', entry['body'])
            self.assertIn('values.append(3)', entry['body'])
            self.assertNotIn('1. [1, 2]', entry['body'])
            self.assertNotIn('2. [1, 2, 3]', entry['body'])
            self.assertNotIn('3. [3, 2, 1]', entry['body'])
            self.assertNotIn('4. 오류 발생', entry['body'])

    def test_parse_fin_corp_question_bank_entries_converts_incomplete_rows_and_cleans_keywords(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'unused.csv'
            db_path = root / 'progress.sqlite'
            wiki_root = root / 'wikidocs-ebook'
            pages = wiki_root / 'pages'
            pages.mkdir(parents=True)

            flashcard_app.ensure_progress_db(
                db_path,
                seed_rows=[
                    {
                        'id': 'CS-036',
                        'term': 'C 언어',
                        'english': 'C Programming Language',
                        'category': '프로그래밍 언어',
                        'definition': 'C 언어는 하드웨어에 가까운 메모리 제어와 이식 가능한 절차적 문법을 제공하는 컴파일 언어다.',
                        'detailed_explanation': '포인터, 배열, 함수 호출, 메모리 배치를 직접 다루며 시스템 소프트웨어와 임베디드 구현에 널리 쓰인다.',
                        'related_concepts': '[[포인터]], [[전역 변수]], [[static 변수]]',
                        'source_files': 'pages/05-04-금융결제원-기출.md',
                        'exam_note': '',
                        'bok_appeared': '',
                        'importance': '상',
                        'difficulty': '중',
                    },
                    {
                        'id': 'CS-161',
                        'term': 'LRU',
                        'english': 'LRU',
                        'category': '운영체제',
                        'definition': 'LRU는 가장 오래 사용되지 않은 페이지를 교체 대상으로 삼는 페이지 교체 정책이다.',
                        'detailed_explanation': '최근 사용 이력이 가까운 미래의 재사용 가능성을 나타낸다고 보고 가장 오래 참조되지 않은 항목을 제거한다.',
                        'related_concepts': '[[가상 메모리]], [[페이지 폴트]]',
                        'source_files': 'pages/05-07-금융감독원-기출.md',
                        'exam_note': '',
                        'bok_appeared': '',
                        'importance': '상',
                        'difficulty': '중',
                    },
                    {
                        'id': 'CS-219',
                        'term': '퍼블릭 블록체인',
                        'english': 'Public Blockchain',
                        'category': '금융IT·신기술',
                        'definition': '퍼블릭 블록체인은 누구나 참여하고 검증할 수 있는 공개형 블록체인이다.',
                        'detailed_explanation': '개방성과 투명성은 높지만 성능과 규제 통제, 개인정보 보호 측면의 한계가 있다.',
                        'related_concepts': '[[프라이빗 블록체인]], [[합의 알고리즘]]',
                        'source_files': 'pages/05-03-대구은행-기출.md',
                        'exam_note': '',
                        'bok_appeared': '',
                        'importance': '상',
                        'difficulty': '중',
                    },
                    {
                        'id': 'CS-347',
                        'term': 'XSS',
                        'english': 'XSS',
                        'category': '보안',
                        'definition': '웹 페이지에 악성 스크립트를 삽입해 사용자 브라우저에서 실행시키는 공격이다.',
                        'detailed_explanation': '입력 검증과 출력 인코딩이 핵심 방어 수단이다.',
                        'related_concepts': '[[SQL Injection]], [[CSRF]]',
                        'source_files': 'pages/05-01-우리은행-기출.md',
                        'exam_note': '',
                        'bok_appeared': '',
                        'importance': '상',
                        'difficulty': '중',
                    },
                    {
                        'id': 'CS-348',
                        'term': 'SQL Injection',
                        'english': 'SQL Injection',
                        'category': '보안',
                        'definition': '입력값에 SQL 구문을 삽입해 질의를 변조하는 공격이다.',
                        'detailed_explanation': '준비된 문장과 입력 검증으로 방어한다.',
                        'related_concepts': '[[XSS]], [[인증]]',
                        'source_files': 'pages/05-01-우리은행-기출.md',
                        'exam_note': '',
                        'bok_appeared': '',
                        'importance': '상',
                        'difficulty': '중',
                    },
                ],
            )

            (pages / '05-01-우리은행-기출.md').write_text(
                '# 05-01. 우리은행 기출\n\n'
                '### 11. XSS, SQL Injection 같은 공격기법 객관식으로 주면서 아래에 해당하는 공격기법 선택하라는 문제\n'
                '**답(AI답변):** XSS는 악성 스크립트를 웹페이지에 삽입해 사용자의 브라우저에서 실행시키는 공격이고, SQL Injection은 입력값에 SQL 구문을 삽입해 DB를 조작하는 공격이다.\n\n'
                '### 12. 1 Petabyte의 크기는?\n'
                '**답:** 1,024 TB\n',
                encoding='utf-8',
            )
            (pages / '05-03-대구은행-기출.md').write_text(
                '# 05-03. 대구은행 기출\n\n'
                '### 121. 퍼블릭 블록체인 특징으로 옳지 않은 것은?\n\n'
                '**답:** 중앙시스템 제어가 필요한 금융서비스에 부적합함.\n',
                encoding='utf-8',
            )
            (pages / '05-04-금융결제원-기출.md').write_text(
                '# 05-04. 금융결제원 기출\n\n'
                '### 155. (주관식)C언어 코드 출력결과\n'
                '**답(AI답변):** 문제의 선지/도표가 원문에 충분히 남아 있지 않아 단정형 정답은 제한적이다. 해당 주제의 핵심 개념과 대표 공식·특징을 기준으로 풀이해야 한다.\n',
                encoding='utf-8',
            )
            (pages / '05-07-금융감독원-기출.md').write_text(
                '# 05-07. 금융감독원 기출\n\n'
                '### 195. LRU 계산문제 문제\n'
                '**답(AI답변):** LRU는 가장 오랫동안 사용되지 않은 페이지를 교체한다.\n',
                encoding='utf-8',
            )

            entries = flashcard_app.parse_fin_corp_question_bank_entries(wiki_root, db_path)
            by_id = {item['question_bank_id']: item for item in entries}

            public_blockchain = by_id['qb-fin239-05-03-01']
            self.assertEqual(public_blockchain['prompt'], '### 121. 퍼블릭 블록체인의 특징을 설명하시오.')
            self.assertIn('개념문제로 변환함', public_blockchain['body'])
            self.assertIn('원문 제목: 퍼블릭 블록체인 특징으로 옳지 않은 것은?', public_blockchain['body'])
            self.assertEqual(public_blockchain['card_id'], 'CS-219')
            self.assertEqual(public_blockchain['category'], '금융IT·신기술')
            self.assertEqual(public_blockchain['keywords'], ['퍼블릭 블록체인', 'Public Blockchain'])

            c_output = by_id['qb-fin239-05-04-01']
            self.assertEqual(c_output['prompt'], '### 155. C 언어에 대해 핵심 원리와 풀이 기준을 설명하시오.')
            self.assertEqual(c_output['card_id'], 'CS-036')
            self.assertEqual(c_output['category'], '프로그래밍 언어')
            self.assertIn('C 언어', c_output['keywords'])
            self.assertNotIn('Java', c_output['keywords'])

            lru = by_id['qb-fin239-05-07-01']
            self.assertEqual(lru['prompt'], '### 195. LRU에 대해 핵심 원리와 풀이 기준을 설명하시오.')
            self.assertEqual(lru['card_id'], 'CS-161')
            self.assertEqual(lru['category'], '운영체제')
            self.assertEqual(lru['keywords'], ['LRU'])
            xss = by_id['qb-fin239-05-01-01']
            self.assertEqual(xss['card_id'], 'CS-347')
            self.assertEqual(xss['keywords'], ['XSS', 'SQL Injection'])

            petabyte = by_id['qb-fin239-05-01-02']
            self.assertEqual(petabyte['keywords'], ['Petabyte'])


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
            seed_runtime_db(csv_path, db_path)

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

            saved = flashcard_app.sync_bok_question_bank_entries(wiki_root, db_path)
            self.assertEqual(saved['pages'], 2)
            self.assertEqual(saved['count'], 3)

            saved_again = flashcard_app.sync_bok_question_bank_entries(wiki_root, db_path)
            self.assertEqual(saved_again['count'], 3)

            listed = flashcard_app.read_question_bank_entries(db_path, issuer='한국은행', limit=10)
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
            original_db = flashcard_app.PROGRESS_DB_PATH
            try:
                flashcard_app.PROGRESS_DB_PATH = db_path
                payload = flashcard_app.QuestionGenerateRequest(card_ids=['CS-001'], types=['short'], count=1, seed=7)
                generated = flashcard_app.api_generate_questions(payload)
            finally:
                flashcard_app.PROGRESS_DB_PATH = original_db

            self.assertEqual(len(generated['questions']), 1)
            question = generated['questions'][0]
            self.assertTrue(question['question_bank_id'])
            self.assertEqual(question['topic'], '소프트웨어공학')
            self.assertEqual(question['difficulty'], '중')
            self.assertEqual(question['issuer'], '카드 생성')
            self.assertEqual(question['source_location'], 'sample.md')

            listed = flashcard_app.read_question_bank_entries(db_path, card_id='CS-001', limit=10)
            self.assertEqual(listed['summary']['total'], 1)
            self.assertEqual(listed['items'][0]['question_bank_id'], question['question_bank_id'])

    def test_read_question_bank_entries_seeds_demo_and_filters(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_sample(csv_path)
            seed_runtime_db(csv_path, db_path)


            seeded = flashcard_app.read_question_bank_entries(db_path, limit=10)
            self.assertEqual(seeded['summary']['total'], 1)
            self.assertEqual(seeded['items'][0]['issuer'], '샘플')
            self.assertEqual(seeded['items'][0]['topic'], '데이터베이스')
            self.assertIn('/static/favicon.svg', seeded['items'][0]['body'])

            filtered = flashcard_app.read_question_bank_entries(
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

            flashcard_app.ensure_progress_db(db_path, seed_rows_from_csv(csv_path))
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

    def test_runtime_db_can_seed_from_explicit_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            runtime_db_path = root / 'progress.sqlite'
            write_sample(csv_path, include_image=True, include_media=True)
            flashcard_app.ensure_progress_db(runtime_db_path, seed_rows_from_csv(csv_path))

            rows, _ = flashcard_app.read_cards(runtime_db_path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['term'], '테스트')
            self.assertEqual(rows[0]['concept_image_url'], 'https://example.com/test-concept.png')
            self.assertEqual(rows[0]['concept_media_type'], 'mermaid')

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
            self.assertTrue(flashcard_app.is_public_auth_bypass_path('/public/wiki-assets/07-database-overview-ai.png'))
            self.assertTrue(flashcard_app.is_public_auth_bypass_path('/public/wiki-assets'))
            self.assertFalse(flashcard_app.is_public_auth_bypass_path('/static/favicon.svg'))
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




class RecruitmentCalendarTests(unittest.TestCase):
    def test_build_recruitment_calendar_payload_exposes_subscription_metadata(self):
        payload = flashcard_app.build_recruitment_calendar_payload(base_url='https://example.com')
        self.assertEqual(payload['calendar']['calendar_url'], 'https://example.com/calendar')
        self.assertEqual(payload['calendar']['ics_url'], 'https://example.com/api/calendar/recruitment.ics')
        self.assertGreater(payload['counts']['total_events'], 0)
        self.assertTrue(any(event['google_calendar_url'].startswith('https://calendar.google.com/calendar/render?') for event in payload['events']))
        self.assertTrue(any(event['url'].startswith('https://') for event in payload['events']))
        self.assertTrue(any(event['institution']['name'] == '한국주택금융공사' for event in payload['events']))
        bok_apply = next(event for event in payload['events'] if event['id'] == 'bok-2027-apply')
        self.assertFalse(bok_apply['allDay'])
        self.assertEqual(bok_apply['start'], '2026-07-23T10:00:00+09:00')
        self.assertEqual(bok_apply['end'], '2026-08-05T17:00:00+09:00')
        self.assertEqual(bok_apply['extendedProps']['start_time'], '10:00')
        self.assertIn('ctz=Asia%2FSeoul', bok_apply['google_calendar_url'])

    def test_build_recruitment_calendar_ics_contains_expected_fields(self):
        content = flashcard_app.build_recruitment_calendar_ics(base_url='https://example.com')
        self.assertIn('BEGIN:VCALENDAR', content)
        self.assertIn('UID:bok-2027-apply@cs-flashcards', content)
        self.assertIn('DTSTART:20260723T010000Z', content)
        self.assertIn('DTEND:20260805T080000Z', content)
        self.assertIn('X-WR-CALNAME:2026 금융공기업 IT 채용 캘린더', content)
        self.assertIn('api/calendar/recruitment.ics', content)

    def test_read_wiki_page_hydrates_recruitment_schedule_sections(self):
        with tempfile.TemporaryDirectory() as td:
            book = Path(td) / 'wikidocs-ebook'
            pages = book / 'pages'
            pages.mkdir(parents=True, exist_ok=True)
            (book / 'README.md').write_text('# 금공 IT 위키\n\n- [기본 전제와 일정](pages/02-01-기본-전제와-일정.md)\n', encoding='utf-8')
            (book / 'TOC.md').write_text('# 목차\n\n- [기본 전제와 일정](pages/02-01-기본-전제와-일정.md)\n', encoding='utf-8')
            (pages / '02-01-기본-전제와-일정.md').write_text(
                '# 1. 기본 전제\n\n'
                '## 2. 현재 기준 일정\n\n'
                '기존 섹션\n\n'
                '## 3. 전체 시간 배분\n\n'
                '유지\n\n'
                '## 5. 기관별 채용 일정 대시보드\n\n'
                '기존 대시보드\n\n'
                '## 약어 풀이\n\n'
                '- 테스트\n',
                encoding='utf-8',
            )
            mocked_schedule = json.loads(json.dumps(flashcard_app.load_recruitment_schedule()))
            mocked_schedule['last_updated'] = '2026-08-01'

            with mock.patch.object(flashcard_app, 'load_recruitment_schedule', return_value=mocked_schedule):
                page = flashcard_app.read_wiki_page('02-01-기본-전제와-일정', book)
            self.assertIn('/calendar', page['html'])
            self.assertIn('/api/calendar/recruitment.ics', page['html'])
            self.assertIn('한국주택금융공사', page['html'])
            self.assertIn('Google Calendar', page['html'])
            self.assertIn('2026.08.01 현재 상태', page['html'])

class WikiBookTests(unittest.TestCase):
    def test_read_wiki_index_and_page_render_internal_links(self):
        with tempfile.TemporaryDirectory() as td:
            book = write_wiki_book(Path(td))
            intro_path = book / 'pages' / 'intro.md'
            stamp = datetime(2026, 8, 1, 5, 35, tzinfo=timezone.utc).timestamp()
            os.utime(intro_path, (stamp, stamp))
            index = flashcard_app.read_wiki_index(book)
            self.assertEqual(index['book']['title'], '금공 IT 위키')
            self.assertEqual(index['default_page_slug'], 'intro')
            self.assertIn('child', index['pages'])

            page = flashcard_app.read_wiki_page('intro', book)
            self.assertEqual(page['title'], '소개 문서')
            self.assertEqual(page['last_modified_at'], '2026-08-01T14:35:00+09:00')
            self.assertEqual(page['last_modified_label'], '2026-08-01 14:35')
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
            original_db = flashcard_app.PROGRESS_DB_PATH
            try:
                flashcard_app.PROGRESS_DB_PATH = db_path
                page = flashcard_app.read_wiki_page('intro', book)
                self.assertEqual(page['primary_card']['id'], 'CS-001')
                self.assertTrue(page['primary_card']['card_url'].startswith('/?card=CS-001'))
                self.assertEqual(page['linked_cards'][0]['term'], '소개 문서')
            finally:
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
                self.assertTrue(response['page']['last_modified_at'])
                self.assertRegex(response['page']['last_modified_label'], r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$')
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
