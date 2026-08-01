import io
import os
import re
import sqlite3
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app as flashcard_app

ROOT = Path(__file__).resolve().parents[1]
BACKEND_SOURCE = (ROOT / 'flashcards_backend.py').read_text(encoding='utf-8')
DEPLOY_SCRIPT = (ROOT / 'scripts' / 'deploy_lightsail_flashcards.sh').read_text(encoding='utf-8')
PULL_SCRIPT = (ROOT / 'scripts' / 'pull_remote_sqlite.sh').read_text(encoding='utf-8')
REMOTE_SQL_SCRIPT = (ROOT / 'scripts' / 'remote_sqlite_sql.sh').read_text(encoding='utf-8')
DEPLOY_SKILL = (ROOT / '.codex/skills/cs-flashcards-deploy-guard/SKILL.md').read_text(encoding='utf-8')
DEPLOY_CHECKLIST = (ROOT / '.codex/skills/cs-flashcards-deploy-guard/references/deploy-checklist.md').read_text(encoding='utf-8')
REMOTE_AI_SKILL = (ROOT / '.gjc/skills/cs-remote-ai-batch/SKILL.md').read_text(encoding='utf-8')
DEPLOY_GUARD_PATTERN = re.compile(r'^ensure_stage_has_no_sqlite_payload\(\) \{\n(?P<body>.*?)^\}\n', re.MULTILINE | re.DOTALL)
DEPLOY_GUARD_CALL = 'ensure_stage_has_no_sqlite_payload "$TMP_STAGE" "$TMP_ARCHIVE"'
REMOTE_SQL_VALIDATE_PATTERN = re.compile(r'^validate_sql_text\(\) \{\n(?P<body>.*?)^\}\n', re.MULTILINE | re.DOTALL)
REMOTE_SQL_REMOTE_BLOCK_PATTERN = re.compile(r"<<'REMOTE'\n(?P<body>.*?)^REMOTE$", re.MULTILINE | re.DOTALL)



def write_tar_gz(path: Path, members: dict[str, str]) -> None:
    with tarfile.open(path, 'w:gz') as archive:
        for name, content in members.items():
            payload = content.encode('utf-8')
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


def run_deploy_sqlite_guard(stage_dir: Path, archive_path: Path) -> subprocess.CompletedProcess[str]:
    match = DEPLOY_GUARD_PATTERN.search(DEPLOY_SCRIPT)
    if match is None:
        raise AssertionError('deploy sqlite guard function not found')
    script = f"set -euo pipefail\n{match.group(0)}\nensure_stage_has_no_sqlite_payload \"$1\" \"$2\"\n"
    return subprocess.run(
        ['bash', '-c', script, 'deploy-guard-test', str(stage_dir), str(archive_path)],
        capture_output=True,
        text=True,
        check=False,
    )

def write_cards_sqlite(path: Path, *, cards_count: int) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute('CREATE TABLE cards (id INTEGER PRIMARY KEY, front TEXT NOT NULL)')
        for index in range(cards_count):
            conn.execute('INSERT INTO cards (front) VALUES (?)', (f'card-{index}',))
        conn.commit()
    finally:
        conn.close()

def run_remote_sql_block(db_path: Path, sql_text: str) -> subprocess.CompletedProcess[str]:
    match = REMOTE_SQL_REMOTE_BLOCK_PATTERN.search(REMOTE_SQL_SCRIPT)
    if match is None:
        raise AssertionError('remote sqlite body not found')
    script = match.group('body')
    return subprocess.run(
        ['bash', '-c', script, 'remote-sql-test', str(db_path)],
        env={**os.environ, 'SQL_TEXT': sql_text},
        capture_output=True,
        text=True,
        check=False,
    )



def run_remote_sql_validation(sql_text: str) -> subprocess.CompletedProcess[str]:
    match = REMOTE_SQL_VALIDATE_PATTERN.search(REMOTE_SQL_SCRIPT)
    if match is None:
        raise AssertionError('remote sqlite validator not found')
    script = f"set -euo pipefail\n{match.group(0)}\nvalidate_sql_text \"$SQL_TEXT\"\n"
    return subprocess.run(
        ['bash', '-c', script, 'remote-sql-validate-test'],
        env={**os.environ, 'SQL_TEXT': sql_text},
        capture_output=True,
        text=True,
        check=False,
    )



def write_named_rows_sqlite(path: Path, *names: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)')
        conn.executemany('INSERT INTO items (name) VALUES (?)', [(name,) for name in names])
        conn.commit()


class DeploySafetyTests(unittest.TestCase):
    def test_connect_progress_db_refuses_missing_file_when_guard_enabled(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / 'missing.sqlite'
            with mock.patch.dict(os.environ, {flashcard_app.PROGRESS_DB_MUST_EXIST_ENV: '1'}, clear=False):
                with self.assertRaises(FileNotFoundError):
                    flashcard_app.connect_progress_db(db_path)
            self.assertFalse(db_path.exists())

    def test_flashcards_backend_is_app_independent_and_keeps_missing_db_guard(self):
        self.assertNotIn('import app', BACKEND_SOURCE)
        self.assertNotIn('from app import', BACKEND_SOURCE)
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / 'missing.sqlite'
            with self.assertRaises(FileNotFoundError):
                flashcard_app.flashcards_backend.connect_progress_db(db_path, must_exist=True)
            self.assertFalse(db_path.exists())
    def test_deploy_script_removes_db_copy_and_sqlite_touch_path(self):
        self.assertNotIn('CS_FLASHCARDS_FORCE_DB_REPLACE', DEPLOY_SCRIPT)
        self.assertNotIn('cp state/progress.sqlite', DEPLOY_SCRIPT)
        self.assertNotIn('import sqlite3', DEPLOY_SCRIPT)
        self.assertNotIn('read_card_content(app.PROGRESS_DB_PATH)', DEPLOY_SCRIPT)
        self.assertIn('cp app.py flashcards_backend.py question_generator.py requirements.txt "$TMP_STAGE/"', DEPLOY_SCRIPT)
        self.assertIn('배포 번들에 SQLite 파일을 포함하지 않습니다.', DEPLOY_SCRIPT)
        self.assertIn('CS_FLASHCARD_PROGRESS_DB_MUST_EXIST=1', DEPLOY_SCRIPT)
        self.assertIn('원격 SQLite 파일이 없으면 배포를 중단합니다', DEPLOY_SCRIPT)

    def test_deploy_script_has_valid_bash_syntax(self):
        result = subprocess.run(
            ['bash', '-n', str(ROOT / 'scripts' / 'deploy_lightsail_flashcards.sh')],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_deploy_guard_rejects_staged_state_directory(self):
        with tempfile.TemporaryDirectory() as td:
            stage_dir = Path(td) / 'stage'
            stage_dir.mkdir()
            (stage_dir / 'state').mkdir()
            archive_path = Path(td) / 'bundle.tar.gz'
            write_tar_gz(archive_path, {'./app.py': 'ok'})

            result = run_deploy_sqlite_guard(stage_dir, archive_path)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn('배포 스테이지에 state 디렉터리가 포함되면 원격 SQLite를 덮어쓸 수 있으므로 중단합니다', result.stderr)

    def test_deploy_guard_rejects_sqlite_payload_in_archive(self):
        with tempfile.TemporaryDirectory() as td:
            stage_dir = Path(td) / 'stage'
            stage_dir.mkdir()
            (stage_dir / 'static').mkdir()
            (stage_dir / 'static' / 'placeholder.txt').write_text('ok', encoding='utf-8')
            archive_path = Path(td) / 'bundle.tar.gz'
            write_tar_gz(archive_path, {'./app.py': 'ok', './rogue.sqlite': 'sqlite-bytes'})

            result = run_deploy_sqlite_guard(stage_dir, archive_path)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn('배포 아카이브에 SQLite/state payload가 감지되면 중단합니다', result.stderr)

    def test_deploy_guard_allows_normal_bundle_and_runs_before_upload(self):
        with tempfile.TemporaryDirectory() as td:
            stage_dir = Path(td) / 'stage'
            (stage_dir / 'static').mkdir(parents=True)
            (stage_dir / 'data').mkdir()
            (stage_dir / 'app.py').write_text('print("ok")\n', encoding='utf-8')
            (stage_dir / 'flashcards_backend.py').write_text('def connect_progress_db(*args, **kwargs):\n    raise NotImplementedError\n', encoding='utf-8')
            (stage_dir / 'static' / 'placeholder.txt').write_text('ok', encoding='utf-8')
            (stage_dir / 'data' / 'recruitment_schedule_2026.json').write_text('{}\n', encoding='utf-8')
            archive_path = Path(td) / 'bundle.tar.gz'
            write_tar_gz(
                archive_path,
                {
                    './app.py': 'print("ok")\n',
                    './flashcards_backend.py': 'def connect_progress_db(*args, **kwargs):\n    raise NotImplementedError\n',
                    './static/placeholder.txt': 'ok',
                    './data/recruitment_schedule_2026.json': '{}\n',
                },
            )

            result = run_deploy_sqlite_guard(stage_dir, archive_path)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, '')
            self.assertLess(DEPLOY_SCRIPT.index(DEPLOY_GUARD_CALL), DEPLOY_SCRIPT.index('"${SCP[@]}" "$TMP_ARCHIVE"'))
    def test_pull_script_uses_fixed_remote_db_path(self):
        self.assertNotIn('[--remote-db PATH]', PULL_SCRIPT)
        self.assertIn('원격 DB 경로 변경은 금지됩니다', PULL_SCRIPT)
        self.assertIn('REMOTE_DB_PATH="$REMOTE_DIR/state/progress.sqlite"', PULL_SCRIPT)

    def test_pull_script_validates_download_before_replacing_output(self):
        self.assertIn("sqlite3.connect(f'file:{path}?mode=ro', uri=True)", PULL_SCRIPT)
        self.assertIn("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cards'", PULL_SCRIPT)
        self.assertIn("SELECT COUNT(*) FROM cards", PULL_SCRIPT)
        self.assertLess(PULL_SCRIPT.index('validate_downloaded_sqlite "$TMP_FILE"'), PULL_SCRIPT.index('mv "$TMP_FILE" "$OUTPUT_PATH"'))

    def test_pull_script_keeps_existing_output_when_downloaded_db_is_empty(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            output_path = temp_root / 'state' / 'progress.sqlite'
            output_path.parent.mkdir(parents=True)
            write_cards_sqlite(output_path, cards_count=2)
            baseline_bytes = output_path.read_bytes()

            downloaded_db = temp_root / 'downloaded.sqlite'
            write_cards_sqlite(downloaded_db, cards_count=0)

            fake_key = temp_root / 'fake-key.pem'
            fake_key.write_text('fake-key\n', encoding='utf-8')

            fake_bin = temp_root / 'bin'
            fake_bin.mkdir()
            fake_scp = fake_bin / 'scp'
            fake_scp.write_text(
                '#!/usr/bin/env bash\n'
                'set -euo pipefail\n'
                'dest="${@: -1}"\n'
                'cp "$FAKE_REMOTE_DB_SOURCE" "$dest"\n',
                encoding='utf-8',
            )
            fake_scp.chmod(0o755)

            env = os.environ.copy()
            env.update(
                {
                    'CS_FLASHCARDS_LIGHTSAIL_HOST': 'example.com',
                    'CS_FLASHCARDS_LIGHTSAIL_KEY': str(fake_key),
                    'CS_FLASHCARDS_REMOTE_CONFIG': str(temp_root / 'missing-config'),
                    'FAKE_REMOTE_DB_SOURCE': str(downloaded_db),
                    'PATH': f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
                }
            )

            result = subprocess.run(
                ['bash', str(ROOT / 'scripts' / 'pull_remote_sqlite.sh'), '--output', str(output_path)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn('다운로드한 SQLite 검증에 실패했습니다: cards 테이블이 비어 있습니다.', result.stderr)
            self.assertIn(f'기존 로컬 SQLite는 유지됩니다: {output_path}', result.stderr)
            self.assertEqual(output_path.read_bytes(), baseline_bytes)

    def test_remote_sql_script_executes_direct_sql_only(self):
        self.assertNotIn('[--remote-db PATH]', REMOTE_SQL_SCRIPT)
        self.assertNotIn('scp ', REMOTE_SQL_SCRIPT)
        self.assertNotIn('PAYLOAD_FILE', REMOTE_SQL_SCRIPT)
        self.assertNotIn('INSERT INTO {table}', REMOTE_SQL_SCRIPT)
        self.assertIn('원격 DB 경로 변경은 금지됩니다', REMOTE_SQL_SCRIPT)
        self.assertIn('sqlite3 -bail "$REMOTE_DB_PATH"', REMOTE_SQL_SCRIPT)

    def test_remote_sql_script_wraps_sql_in_transaction_and_bails_on_error(self):
        self.assertIn("BEGIN IMMEDIATE;", REMOTE_SQL_SCRIPT)
        self.assertIn('sqlite3 -bail "$REMOTE_DB_PATH"', REMOTE_SQL_SCRIPT)

    def test_remote_sql_script_rejects_sqlite_meta_and_transaction_commands(self):
        self.assertIn('sqlite dot-command는 허용되지 않습니다.', REMOTE_SQL_SCRIPT)
        self.assertIn('트랜잭션 제어 SQL은 허용되지 않습니다.', REMOTE_SQL_SCRIPT)
        self.assertIn('SQLite 실행 경계를 변경하는 SQL은 허용되지 않습니다.', REMOTE_SQL_SCRIPT)
        self.assertLess(REMOTE_SQL_SCRIPT.index('validate_sql_text "$SQL_TEXT"'), REMOTE_SQL_SCRIPT.index('SSH=('))

    def test_remote_sql_script_rejects_unsafe_sql_before_ssh_or_sqlite(self):
        cases = [
            ('BEGIN IMMEDIATE;\nUPDATE items SET name=\'changed\';\n', '트랜잭션 제어 SQL은 허용되지 않습니다.'),
            ('commit;\nUPDATE items SET name=\'changed\';\n', '트랜잭션 제어 SQL은 허용되지 않습니다.'),
            ('ROLLBACK;\n', '트랜잭션 제어 SQL은 허용되지 않습니다.'),
            ('SAVEPOINT keep_me;\n', '트랜잭션 제어 SQL은 허용되지 않습니다.'),
            ('RELEASE keep_me;\n', '트랜잭션 제어 SQL은 허용되지 않습니다.'),
            ('ATTACH DATABASE \'other.sqlite\' AS other;\n', 'SQLite 실행 경계를 변경하는 SQL은 허용되지 않습니다.'),
            ('detach database other;\n', 'SQLite 실행 경계를 변경하는 SQL은 허용되지 않습니다.'),
            ('PRAGMA journal_mode=WAL;\n', 'SQLite 실행 경계를 변경하는 SQL은 허용되지 않습니다.'),
            ('.read /tmp/payload.sql\n', 'sqlite dot-command는 허용되지 않습니다.'),
        ]

        for sql_text, expected_message in cases:
            with self.subTest(sql_text=sql_text):
                result = run_remote_sql_validation(sql_text)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected_message, result.stderr)

    def test_remote_sql_script_rolls_back_partial_changes_on_failure(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / 'remote.sqlite'
            write_named_rows_sqlite(db_path, 'before')

            result = run_remote_sql_block(db_path, "UPDATE items SET name='changed';\nINVALID SQL;\n")

            self.assertNotEqual(result.returncode, 0)
            with sqlite3.connect(db_path) as conn:
                self.assertEqual(conn.execute('SELECT name FROM items ORDER BY id').fetchall(), [('before',)])

    def test_remote_sql_script_rejects_outer_transaction_escape_hatches(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / 'remote.sqlite'
            write_named_rows_sqlite(db_path, 'before')

            result = run_remote_sql_block(db_path, "COMMIT;\nUPDATE items SET name='changed';\nINVALID SQL;\n")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn('트랜잭션 제어 SQL은 허용되지 않습니다.', result.stderr)
            with sqlite3.connect(db_path) as conn:
                self.assertEqual(conn.execute('SELECT name FROM items ORDER BY id').fetchall(), [('before',)])

    def test_remote_sql_script_applies_all_statements_when_transaction_succeeds(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / 'remote.sqlite'
            write_named_rows_sqlite(db_path, 'before')

            result = run_remote_sql_block(db_path, "UPDATE items SET name='changed';\nINSERT INTO items (name) VALUES ('after');\n")

            self.assertEqual(result.returncode, 0, result.stderr)
            with sqlite3.connect(db_path) as conn:
                self.assertEqual(conn.execute('SELECT name FROM items ORDER BY id').fetchall(), [('changed',), ('after',)])

    def test_skill_docs_use_direct_remote_sql_policy(self):
        self.assertIn('./scripts/remote_sqlite_sql.sh', DEPLOY_SKILL)
        self.assertNotIn('sync_remote_sqlite_rows.sh', DEPLOY_SKILL)
        self.assertNotIn('not Git-managed', DEPLOY_CHECKLIST)
        self.assertIn('may be Git-tracked locally', DEPLOY_CHECKLIST)
        self.assertNotIn('Never edit or commit `state/progress.sqlite`', REMOTE_AI_SKILL)
        self.assertIn('direct remote SQL is the only allowed path', REMOTE_AI_SKILL)


if __name__ == '__main__':
    unittest.main()
