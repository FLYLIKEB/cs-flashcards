from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import app as flashcard_app


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_bundles.py <wave-dir>", file=sys.stderr)
        return 2
    wave_dir = Path(sys.argv[1]).expanduser().resolve()
    if not wave_dir.is_dir():
        print(f"wave dir not found: {wave_dir}", file=sys.stderr)
        return 2
    db_path = (Path(__file__).resolve().parents[2] / "state" / "progress.sqlite").resolve()
    flashcard_app.ensure_progress_db(db_path)
    updated = 0
    unchanged = 0
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        for bundle_path in sorted(wave_dir.glob("*.json")):
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            proposed = dict(bundle.get("proposed_row") or {})
            normalized = flashcard_app.normalize_question_bank_entry(proposed, db_path)
            current = conn.execute("SELECT * FROM question_bank WHERE id = ?", (normalized["question_bank_id"],)).fetchone()
            if current is None:
                raise RuntimeError(f"missing question row: {normalized['question_bank_id']}")
            current_payload = {
                "question_bank_id": current["id"],
                "card_id": current["card_id"] or "",
                "question_type": current["question_type"] or "",
                "prompt": current["prompt"] or "",
                "body": current["body"] or "",
                "answer": current["answer"] or "",
                "explanation": current["explanation"] or "",
                "rubric": flashcard_app.question_bank_json_list(current["rubric_json"]),
                "choices": flashcard_app.question_bank_json_list(current["choices_json"]),
                "answer_index": current["answer_index"],
                "topic": current["topic"] or "",
                "field_name": current["field_name"] or "",
                "category": current["category"] or "",
                "keywords": flashcard_app.question_bank_json_list(current["keywords_json"]),
                "difficulty": current["difficulty"] or "",
                "issuer": current["issuer"] or "",
                "source_location": current["source_location"] or "",
                "section": current["section"] or "",
                "points": current["points"],
                "expected_time_seconds": current["expected_time_seconds"],
                "answer_guide": current["answer_guide"] or "",
                "session_mode": current["session_mode"] or "practice",
            }
            current_normalized = flashcard_app.normalize_question_bank_entry(current_payload, db_path)
            if normalized == current_normalized:
                unchanged += 1
                continue
            dup = conn.execute(
                "SELECT id FROM question_bank WHERE fingerprint = ? AND id <> ?",
                (normalized["fingerprint"], normalized["question_bank_id"]),
            ).fetchone()
            if dup:
                raise RuntimeError(
                    f"fingerprint collision for {normalized['question_bank_id']} with existing {dup['id']}"
                )
            conn.execute(
                """
                UPDATE question_bank
                SET fingerprint = ?,
                    card_id = ?,
                    question_type = ?,
                    prompt = ?,
                    body = ?,
                    answer = ?,
                    explanation = ?,
                    rubric_json = ?,
                    choices_json = ?,
                    answer_index = ?,
                    topic = ?,
                    field_name = ?,
                    category = ?,
                    keywords_json = ?,
                    difficulty = ?,
                    issuer = ?,
                    source_location = ?,
                    section = ?,
                    points = ?,
                    expected_time_seconds = ?,
                    answer_guide = ?,
                    session_mode = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    normalized["fingerprint"],
                    normalized["card_id"] or None,
                    normalized["question_type"],
                    normalized["prompt"],
                    normalized["body"],
                    normalized["answer"],
                    normalized["explanation"],
                    flashcard_app.question_bank_json_text(normalized["rubric"], item_limit=2000),
                    flashcard_app.question_bank_json_text(normalized["choices"], item_limit=2000),
                    normalized["answer_index"],
                    normalized["topic"],
                    normalized["field_name"],
                    normalized["category"],
                    flashcard_app.question_bank_json_text(normalized["keywords"], item_limit=255),
                    normalized["difficulty"],
                    normalized["issuer"],
                    normalized["source_location"],
                    normalized["section"],
                    normalized["points"],
                    normalized["expected_time_seconds"],
                    normalized["answer_guide"],
                    normalized["session_mode"],
                    flashcard_app.utc_now_iso(),
                    normalized["question_bank_id"],
                ),
            )
            updated += 1
        conn.commit()
    print(json.dumps({"wave": wave_dir.name, "updated": updated, "unchanged": unchanged}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
