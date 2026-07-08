import csv
import tempfile
import unittest
from pathlib import Path

import app as flashcard_app
from question_generator import generate_questions, normalize_question_types, parse_related_concepts


FIELDS = [
    'id', 'term', 'english', 'category', 'definition', 'detailed_explanation',
    'related_concepts', 'source_files', 'exam_note', 'bok_appeared', 'importance', 'difficulty',
]


def sample_cards():
    return [
        {
            'id': 'CS-001',
            'term': '인수 테스트',
            'english': 'Acceptance Test',
            'category': '소프트웨어공학',
            'definition': '인수 테스트는 사용자가 업무 기준으로 시스템 인수 여부를 판단하는 최종 검증입니다.',
            'detailed_explanation': '의미: 사용자의 수용 기준을 확인합니다. 활용: UAT에서 요구사항 충족을 검증합니다.',
            'related_concepts': '[[통합 테스트]], [[시스템 테스트]], [[블랙박스 테스트]]',
            'source_files': 'sample.md',
            'exam_note': '통합 테스트, 시스템 테스트와 비교하면 좋습니다.',
            'bok_appeared': 'O',
            'importance': '상',
            'difficulty': '중',
        },
        {
            'id': 'CS-002',
            'term': '통합 테스트',
            'english': 'Integration Test',
            'category': '소프트웨어공학',
            'definition': '통합 테스트는 여러 모듈을 결합한 뒤 인터페이스와 상호작용을 검증하는 테스트입니다.',
            'detailed_explanation': '모듈 간 데이터 흐름과 호출 관계를 확인합니다.',
            'related_concepts': '[[단위 테스트]], [[시스템 테스트]]',
            'source_files': 'sample.md',
            'exam_note': '단위 테스트와 비교합니다.',
            'bok_appeared': '',
            'importance': '상',
            'difficulty': '중',
        },
        {
            'id': 'CS-003',
            'term': '시스템 테스트',
            'english': 'System Test',
            'category': '소프트웨어공학',
            'definition': '시스템 테스트는 완성된 시스템 전체가 요구사항을 만족하는지 검증하는 테스트입니다.',
            'detailed_explanation': '전체 기능과 비기능 요구사항을 함께 확인합니다.',
            'related_concepts': '[[인수 테스트]], [[통합 테스트]]',
            'source_files': 'sample.md',
            'exam_note': '인수 테스트와 주체가 다릅니다.',
            'bok_appeared': '',
            'importance': '중',
            'difficulty': '중',
        },
        {
            'id': 'CS-004',
            'term': '접근통제',
            'english': 'Access Control',
            'category': '보안',
            'definition': '접근통제는 인증된 주체가 허용된 자원과 행위만 수행하도록 제한하는 보안 통제입니다.',
            'detailed_explanation': '최소 권한과 직무 분리를 기반으로 권한을 관리합니다.',
            'related_concepts': '[[인증]], [[인가]]',
            'source_files': 'sample.md',
            'exam_note': '인증, 인가와 비교합니다.',
            'bok_appeared': '',
            'importance': '상',
            'difficulty': '중',
        },
    ]


def write_cards(path: Path):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(sample_cards())


class QuestionGeneratorTests(unittest.TestCase):
    def test_normalize_question_types_accepts_korean_aliases(self):
        self.assertEqual(normalize_question_types(['객관식', '논술형']), ['multiple_choice', 'essay'])

    def test_parse_related_concepts_from_wiki_links(self):
        self.assertEqual(parse_related_concepts('[[통합 테스트]], [[시스템 테스트]]'), ['통합 테스트', '시스템 테스트'])

    def test_generate_multiple_choice_has_four_choices_and_answer(self):
        result = generate_questions(sample_cards(), card_ids=['CS-001'], types=['multiple_choice'], count=1, seed=42)
        question = result['questions'][0]
        self.assertEqual(question['type'], 'multiple_choice')
        self.assertEqual(len(question['choices']), 4)
        self.assertIn(question['answer'], question['choices'])
        self.assertEqual(question['choices'][question['answer_index']], question['answer'])
        self.assertEqual(len(set(question['choices'])), 4)

    def test_multiple_choice_prefers_related_or_same_category_distractors(self):
        result = generate_questions(sample_cards(), card_ids=['CS-001'], types=['multiple_choice'], count=1, seed=3)
        question = result['questions'][0]
        distractors = set(question['choices']) - {question['answer']}
        self.assertTrue({'통합 테스트', '시스템 테스트'} <= distractors)

    def test_generate_questions_is_deterministic_with_seed(self):
        first = generate_questions(sample_cards(), types=['short', 'multiple_choice'], count=5, seed=7)
        second = generate_questions(sample_cards(), types=['short', 'multiple_choice'], count=5, seed=7)
        self.assertEqual(first, second)

    def test_generate_questions_reports_missing_card_id(self):
        with self.assertRaises(KeyError):
            generate_questions(sample_cards(), card_ids=['CS-999'], types=['short'], count=1, seed=1)

    def test_api_generate_questions_uses_csv_cards(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / 'cards.csv'
            db_path = root / 'progress.sqlite'
            write_cards(csv_path)
            original_csv = flashcard_app.CSV_PATH
            original_db = flashcard_app.PROGRESS_DB_PATH
            try:
                flashcard_app.CSV_PATH = csv_path
                flashcard_app.PROGRESS_DB_PATH = db_path
                data = flashcard_app.api_generate_questions(flashcard_app.QuestionGenerateRequest(
                    card_ids=['CS-001'],
                    types=['short', 'multiple_choice'],
                    count=2,
                    seed=11,
                ))
                self.assertEqual(len(data['questions']), 2)
                self.assertEqual(data['summary']['available_cards'], 1)
                self.assertTrue(all(q['card_id'] == 'CS-001' for q in data['questions']))
            finally:
                flashcard_app.CSV_PATH = original_csv
                flashcard_app.PROGRESS_DB_PATH = original_db


if __name__ == '__main__':
    unittest.main()
