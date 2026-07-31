from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    entries: list[dict] = []
    pack_count = 0
    for path in sorted(root.glob('*.json')):
        if path.name == 'card_reference.json':
            continue
        payload = json.loads(path.read_text(encoding='utf-8'))
        pack_entries = payload.get('entries') or []
        if not isinstance(pack_entries, list):
            raise ValueError(f'entries must be a list: {path}')
        entries.extend(pack_entries)
        pack_count += 1
    saved = app.upsert_question_bank_entries(entries, ROOT / 'state/progress.sqlite')
    print(json.dumps({'packs': pack_count, 'count': saved['count']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
