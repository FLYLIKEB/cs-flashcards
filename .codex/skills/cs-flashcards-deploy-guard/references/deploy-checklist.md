# Deploy Checklist

## Local files

- `app.py` owns FastAPI routes and SQLite state behavior.
- `data/CS_encyclopedia_300plus.csv` owns the CSV bootstrap content.
- `state/progress.sqlite` is the local state DB snapshot; it may be Git-tracked locally, but deploys must never replace the live remote DB file wholesale.
- `scripts/deploy_lightsail_flashcards.sh` packages `app.py`, `requirements.txt`, `static`, and the CSV.

## Required checks

1. CSV exists and has unique `id` values.
2. CSV has required content columns.
3. Progress columns, if present, are ignored for runtime progress restore except initial migration behavior.
4. `.venv/bin/python -m unittest discover -s tests` passes.
5. `/api/health` returns `ok: true`, `csv_exists: true`, and `progress_db_exists: true` after app has read cards at least once.
6. `/api/cards` returns expected card count and categories.

## Remote notes

- Default domain: `https://cs.chamung.com`.
- Default remote DB path documented by README: `/home/ubuntu/cs-flashcards/state/progress.sqlite`.
- Do not print passwords in final output.
- If public endpoint returns 401, retry with Basic Auth rather than weakening app auth.
