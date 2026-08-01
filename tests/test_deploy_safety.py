import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app as flashcard_app

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = (ROOT / 'scripts' / 'deploy_lightsail_flashcards.sh').read_text(encoding='utf-8')
PULL_SCRIPT = (ROOT / 'scripts' / 'pull_remote_sqlite.sh').read_text(encoding='utf-8')
REMOTE_SQL_SCRIPT = (ROOT / 'scripts' / 'remote_sqlite_sql.sh').read_text(encoding='utf-8')
DEPLOY_SKILL = (ROOT / '.codex/skills/cs-flashcards-deploy-guard/SKILL.md').read_text(encoding='utf-8')
DEPLOY_CHECKLIST = (ROOT / '.codex/skills/cs-flashcards-deploy-guard/references/deploy-checklist.md').read_text(encoding='utf-8')
REMOTE_AI_SKILL = (ROOT / '.gjc/skills/cs-remote-ai-batch/SKILL.md').read_text(encoding='utf-8')




class DeploySafetyTests(unittest.TestCase):
    def test_connect_progress_db_refuses_missing_file_when_guard_enabled(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / 'missing.sqlite'
            with mock.patch.dict(os.environ, {flashcard_app.PROGRESS_DB_MUST_EXIST_ENV: '1'}, clear=False):
                with self.assertRaises(FileNotFoundError):
                    flashcard_app.connect_progress_db(db_path)
            self.assertFalse(db_path.exists())

    def test_deploy_script_removes_db_copy_and_sqlite_touch_path(self):
        self.assertNotIn('CS_FLASHCARDS_FORCE_DB_REPLACE', DEPLOY_SCRIPT)
        self.assertNotIn('cp state/progress.sqlite', DEPLOY_SCRIPT)
        self.assertNotIn('import sqlite3', DEPLOY_SCRIPT)
        self.assertNotIn('read_card_content(app.PROGRESS_DB_PATH)', DEPLOY_SCRIPT)
        self.assertIn('배포 번들에 SQLite 파일을 포함하지 않습니다.', DEPLOY_SCRIPT)
        self.assertIn('CS_FLASHCARD_PROGRESS_DB_MUST_EXIST=1', DEPLOY_SCRIPT)
        self.assertIn('원격 SQLite 파일이 없으면 배포를 중단합니다', DEPLOY_SCRIPT)

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
