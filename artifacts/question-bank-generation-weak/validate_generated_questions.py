from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_KEYS = {
    'question_bank_id', 'card_id', 'question_type', 'prompt', 'body', 'answer', 'explanation',
    'rubric', 'choices', 'answer_index', 'topic', 'field_name', 'category', 'keywords',
    'difficulty', 'issuer', 'source_location', 'section', 'points', 'expected_time_seconds',
    'answer_guide', 'session_mode'
}


def validate_entry(entry: dict, pack: dict, errors: list[str], idx: int) -> None:
    missing = sorted(REQUIRED_KEYS - set(entry))
    if missing:
        errors.append(f"{pack['slug']}[{idx}] missing keys: {missing}")
    if entry.get('category') != pack.get('category'):
        errors.append(f"{pack['slug']}[{idx}] category mismatch")
    if entry.get('field_name') != '한국은행 취약분야 보강 60제':
        errors.append(f"{pack['slug']}[{idx}] bad field_name")
    if entry.get('issuer') != '한국은행 대비 제작':
        errors.append(f"{pack['slug']}[{idx}] bad issuer")
    if entry.get('section') != '전공필기':
        errors.append(f"{pack['slug']}[{idx}] bad section")
    if entry.get('session_mode') != 'practice':
        errors.append(f"{pack['slug']}[{idx}] bad session_mode")
    qtype = entry.get('question_type')
    choices = entry.get('choices') or []
    answer_index = entry.get('answer_index')
    if qtype == 'multiple_choice':
        if len(choices) != 4:
            errors.append(f"{pack['slug']}[{idx}] multiple_choice must have 4 choices")
        if answer_index is None or not isinstance(answer_index, int):
            errors.append(f"{pack['slug']}[{idx}] multiple_choice answer_index required")
    else:
        if choices:
            errors.append(f"{pack['slug']}[{idx}] non-mc must not have choices")
        if answer_index is not None:
            errors.append(f"{pack['slug']}[{idx}] non-mc answer_index must be null")


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    errors: list[str] = []
    total = 0
    for path in sorted(root.glob('*.json')):
        pack = json.loads(path.read_text(encoding='utf-8'))
        entries = pack.get('entries') or []
        if len(entries) != pack.get('target_count'):
            errors.append(f"{pack['slug']} target_count mismatch: {len(entries)} != {pack.get('target_count')}")
        seen = set()
        for idx, entry in enumerate(entries):
            validate_entry(entry, pack, errors, idx)
            qid = entry.get('question_bank_id')
            if qid in seen:
                errors.append(f"{pack['slug']} duplicate id: {qid}")
            seen.add(qid)
        total += len(entries)
    print(json.dumps({'total_entries': total, 'error_count': len(errors), 'errors': errors[:50]}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
