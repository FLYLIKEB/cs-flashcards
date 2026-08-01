import io
import os
import re
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
        self.assertIn('배포 번들에 SQLite 파일을 포함하지 않습니다.', DEPLOY_SCRIPT)
        self.assertIn('CS_FLASHCARD_PROGRESS_DB_MUST_EXIST=1', DEPLOY_SCRIPT)
        self.assertIn('원격 SQLite 파일이 없으면 배포를 중단합니다', DEPLOY_SCRIPT)

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
            (stage_dir / 'static' / 'placeholder.txt').write_text('ok', encoding='utf-8')
            (stage_dir / 'data' / 'recruitment_schedule_2026.json').write_text('{}\n', encoding='utf-8')
            archive_path = Path(td) / 'bundle.tar.gz'
            write_tar_gz(
                archive_path,
                {
                    './app.py': 'print("ok")\n',
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

    def test_remote_sql_script_executes_direct_sql_only(self):
        self.assertNotIn('[--remote-db PATH]', REMOTE_SQL_SCRIPT)
        self.assertNotIn('scp ', REMOTE_SQL_SCRIPT)
        self.assertNotIn('PAYLOAD_FILE', REMOTE_SQL_SCRIPT)
        self.assertNotIn('INSERT INTO {table}', REMOTE_SQL_SCRIPT)
        self.assertIn('원격 DB 경로 변경은 금지됩니다', REMOTE_SQL_SCRIPT)
        self.assertIn('sqlite3 "$REMOTE_DB_PATH"', REMOTE_SQL_SCRIPT)

    def test_skill_docs_use_direct_remote_sql_policy(self):
        self.assertIn('./scripts/remote_sqlite_sql.sh', DEPLOY_SKILL)
        self.assertNotIn('sync_remote_sqlite_rows.sh', DEPLOY_SKILL)
        self.assertNotIn('not Git-managed', DEPLOY_CHECKLIST)
        self.assertIn('may be Git-tracked locally', DEPLOY_CHECKLIST)
        self.assertNotIn('Never edit or commit `state/progress.sqlite`', REMOTE_AI_SKILL)
        self.assertIn('direct remote SQL is the only allowed path', REMOTE_AI_SKILL)


if __name__ == '__main__':
    unittest.main()
