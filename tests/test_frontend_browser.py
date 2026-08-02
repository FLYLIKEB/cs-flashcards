from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from pyppeteer import launch
from pyppeteer.chromium_downloader import check_chromium, download_chromium


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_BROWSER_SERVER_PYTHON_ENV = 'CS_FRONTEND_BROWSER_PYTHON'
DEFAULT_MAIN_WORKSPACE_NAME = 'cs_flashcards'
MAIN_BRANCH_REF = 'refs/heads/main'
QUESTION_BANK_LAUNCH_KEY = 'csPendingQuestionBankLaunch:v1'
QUESTION_BANK_FILTER_STATE_KEY = 'csQuestionBankFilters:v1'
QUESTION_BANK_PRACTICE_COLLAPSED_KEY = 'csQuestionBankPracticeCollapsed:v1'

WIKI_SIDEBAR_STATE_KEY = 'csFlashcardsWikiSidebar:v1'
WAVE_ID_RE = re.compile(r'^(wave-\d+)')
CANONICAL_COMMAND = '.venv/bin/python -m unittest tests.test_frontend_browser'
TRANSCRIPT_DIR = ROOT / 'artifacts' / 'frontend-browser'


def python_executable_path(worktree_root: Path) -> Path:
    return worktree_root / '.venv' / 'bin' / 'python'


def usable_python(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def parse_git_worktree_entries(output: str) -> list[tuple[Path, str | None]]:
    entries: list[tuple[Path, str | None]] = []
    current_path: Path | None = None
    current_branch: str | None = None
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            if current_path is not None:
                entries.append((current_path, current_branch))
            current_path = None
            current_branch = None
            continue
        if line.startswith('worktree '):
            current_path = Path(line.removeprefix('worktree ').strip())
            continue
        if line.startswith('branch '):
            current_branch = line.removeprefix('branch ').strip()
    if current_path is not None:
        entries.append((current_path, current_branch))
    return entries


def git_worktree_entries(root: Path = ROOT) -> list[tuple[Path, str | None]]:
    try:
        result = subprocess.run(
            ['git', 'worktree', 'list', '--porcelain'],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    return parse_git_worktree_entries(result.stdout)


def main_workspace_root(root: Path = ROOT, *, worktree_entries: list[tuple[Path, str | None]] | None = None) -> Path | None:
    entries = git_worktree_entries(root) if worktree_entries is None else worktree_entries
    for worktree_root, branch in entries:
        if branch == MAIN_BRANCH_REF:
            return worktree_root
    for worktree_root, _branch in entries:
        if worktree_root.name == DEFAULT_MAIN_WORKSPACE_NAME:
            return worktree_root
    fallback = root.parent / DEFAULT_MAIN_WORKSPACE_NAME
    return fallback if fallback != root else None


def frontend_browser_server_python_candidates(
    root: Path = ROOT,
    *,
    env: dict[str, str] | None = None,
    worktree_entries: list[tuple[Path, str | None]] | None = None,
) -> list[Path]:
    resolved_env = os.environ if env is None else env
    candidates: list[Path] = []
    override = resolved_env.get(FRONTEND_BROWSER_SERVER_PYTHON_ENV, '').strip()
    if override:
        candidates.append(Path(override).expanduser())

    candidates.append(python_executable_path(root))
    main_root = main_workspace_root(root, worktree_entries=worktree_entries)
    if main_root is not None:
        candidates.append(python_executable_path(main_root))

    repo_names = [DEFAULT_MAIN_WORKSPACE_NAME]
    if main_root is not None and main_root.name not in repo_names:
        repo_names.insert(0, main_root.name)
    for base_dir in (root.parent, root.parent.parent):
        for repo_name in repo_names:
            candidates.append(base_dir / repo_name / '.venv' / 'bin' / 'python')

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def frontend_browser_server_python(
    root: Path = ROOT,
    *,
    env: dict[str, str] | None = None,
    worktree_entries: list[tuple[Path, str | None]] | None = None,
) -> Path:
    candidates = frontend_browser_server_python_candidates(root, env=env, worktree_entries=worktree_entries)
    for candidate in candidates:
        if usable_python(candidate):
            return candidate
    checked_paths = ', '.join(str(candidate) for candidate in candidates)
    raise RuntimeError(
        'Could not find a usable Python for the frontend browser harness. '
        f'Set {FRONTEND_BROWSER_SERVER_PYTHON_ENV} to a valid executable or create a repo-local .venv. '
        f'Checked: {checked_paths}'
    )


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def browser_executable() -> str | None:
    candidates = [
        os.environ.get('CHROME_BIN', '').strip(),
        os.environ.get('PUPPETEER_EXECUTABLE_PATH', '').strip(),
        shutil.which('google-chrome'),
        shutil.which('google-chrome-stable'),
        shutil.which('chromium-browser'),
        shutil.which('chromium'),
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def branch_name_candidates() -> list[str]:
    candidates = [
        os.environ.get('CS_FRONTEND_BROWSER_BRANCH', '').strip(),
        os.environ.get('GITHUB_HEAD_REF', '').strip(),
        os.environ.get('GITHUB_REF_NAME', '').strip(),
    ]
    try:
        result = subprocess.run(
            ['git', 'branch', '--show-current'],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        candidates.append(result.stdout.strip())
    except subprocess.CalledProcessError:
        pass
    return [candidate for candidate in candidates if candidate]


def current_branch_name() -> str:
    candidates = branch_name_candidates()
    return candidates[0] if candidates else 'detached-head'


def transcript_wave_id() -> str:
    explicit_wave_id = os.environ.get('CS_FRONTEND_BROWSER_WAVE_ID', '').strip()
    if explicit_wave_id:
        return explicit_wave_id
    for candidate in branch_name_candidates():
        match = WAVE_ID_RE.match(candidate)
        if match:
            return match.group(1)
    return 'manual-run'


def transcript_path() -> Path:
    return TRANSCRIPT_DIR / f'{transcript_wave_id()}-transcript.json'



def write_test_wiki_book(root: Path) -> Path:
    book = root / 'wiki_book'
    pages = book / 'pages'
    pages.mkdir(parents=True, exist_ok=True)
    (book / 'README.md').write_text('# 테스트 위키\n', encoding='utf-8')
    (book / 'TOC.md').write_text('# 목차\n\n- [소개 문서](pages/intro.md)\n- [심화 문서](pages/deep-dive.md)\n', encoding='utf-8')
    (pages / 'intro.md').write_text(
        '# 소개 문서\n\n'
        '문제은행과 위키 상호작용을 브라우저 하네스로 검증한다.\n\n'
        '## 기초 흐름\n\n'
        '필터를 열고, 검색하고, 상태 텍스트를 확인한다.\n',
        encoding='utf-8',
    )
    (pages / 'deep-dive.md').write_text(
        '# 심화 문서\n\n'
        '사이드바와 검색 상태를 재검증하는 두 번째 페이지다.\n',
        encoding='utf-8',
    )
    return book


def wait_for_http_ok(url: str, *, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if 200 <= response.status < 500:
                    return
        except Exception as exc:  # pragma: no cover - transient startup polling
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f'Server did not start: {url} ({last_error})')


class FrontendBrowserHarnessPythonDiscoveryTests(unittest.TestCase):
    @staticmethod
    def make_fake_python(path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
        path.chmod(0o755)
        return path

    def test_env_override_wins_when_valid(self):
        with tempfile.TemporaryDirectory(prefix='cs-frontend-browser-python-') as td:
            root = Path(td) / 'issue-32-browser-harness-portability'
            root.mkdir()
            override_python = self.make_fake_python(Path(td) / 'custom-python')
            self.make_fake_python(root / '.venv' / 'bin' / 'python')

            selected = frontend_browser_server_python(
                root,
                env={FRONTEND_BROWSER_SERVER_PYTHON_ENV: str(override_python)},
                worktree_entries=[],
            )

            self.assertEqual(selected, override_python)

    def test_current_worktree_venv_beats_main_workspace_venv(self):
        with tempfile.TemporaryDirectory(prefix='cs-frontend-browser-python-') as td:
            parent = Path(td)
            root = parent / 'issue-32-browser-harness-portability'
            root.mkdir()
            main_root = parent / 'cs_flashcards'
            main_root.mkdir()
            current_python = self.make_fake_python(root / '.venv' / 'bin' / 'python')
            self.make_fake_python(main_root / '.venv' / 'bin' / 'python')

            selected = frontend_browser_server_python(
                root,
                env={},
                worktree_entries=[
                    (main_root, MAIN_BRANCH_REF),
                    (root, 'refs/heads/issue-32-browser-harness-portability'),
                ],
            )

            self.assertEqual(selected, current_python)

    def test_main_workspace_worktree_venv_is_used_before_name_based_fallbacks(self):
        with tempfile.TemporaryDirectory(prefix='cs-frontend-browser-python-') as td:
            parent = Path(td)
            root = parent / 'review-worktree'
            root.mkdir()
            main_root = parent / 'authoritative-main-worktree'
            main_root.mkdir()
            main_python = self.make_fake_python(main_root / '.venv' / 'bin' / 'python')
            fallback_python = self.make_fake_python(parent / 'cs_flashcards' / '.venv' / 'bin' / 'python')

            selected = frontend_browser_server_python(
                root,
                env={},
                worktree_entries=[
                    (main_root, MAIN_BRANCH_REF),
                    (root, 'refs/heads/review-worktree'),
                ],
            )

            self.assertEqual(selected, main_python)
            self.assertNotEqual(selected, fallback_python)

    def test_missing_python_error_lists_checked_paths(self):
        with tempfile.TemporaryDirectory(prefix='cs-frontend-browser-python-') as td:
            root = Path(td) / 'issue-32-browser-harness-portability'
            root.mkdir()
            override = Path(td) / 'missing-python'

            with self.assertRaises(RuntimeError) as raised:
                frontend_browser_server_python(
                    root,
                    env={FRONTEND_BROWSER_SERVER_PYTHON_ENV: str(override)},
                    worktree_entries=[],
                )

            message = str(raised.exception)
            self.assertIn(FRONTEND_BROWSER_SERVER_PYTHON_ENV, message)
            self.assertIn(str(override), message)
            self.assertIn(str(root / '.venv' / 'bin' / 'python'), message)


class FrontendBrowserHarnessTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.browser_executable_path = browser_executable()
        if cls.browser_executable_path is None and not check_chromium():
            download_chromium()
        cls._temp_dir = tempfile.TemporaryDirectory(prefix='cs-frontend-browser-')
        cls.temp_root = Path(cls._temp_dir.name)
        cls.progress_db_path = cls.temp_root / 'progress.sqlite'
        shutil.copy2(ROOT / 'state' / 'progress.sqlite', cls.progress_db_path)
        cls.difficulty_regression_prompt = 'difficulty fallback browser regression'
        cls.difficulty_regression_question_id = 'qb-browser-difficulty-fallback'
        with sqlite3.connect(cls.progress_db_path) as conn:
            now = '2026-08-01T00:00:00Z'
            conn.execute(
                """
                INSERT OR REPLACE INTO cards (card_id, term, category, difficulty, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ('CARD-BROWSER-DIFFICULTY', '브라우저 난이도 카드', '테스트', '상', now),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO card_progress (card_id, known_status, updated_at)
                VALUES (?, ?, ?)
                """,
                ('CARD-BROWSER-DIFFICULTY', 'X', now),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO question_bank (
                    id, fingerprint, card_id, question_type, prompt, body, answer, explanation,
                    difficulty, issuer, source_location, category, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cls.difficulty_regression_question_id,
                    'fp-browser-difficulty-fallback',
                    'CARD-BROWSER-DIFFICULTY',
                    'short',
                    cls.difficulty_regression_prompt,
                    'difficulty fallback body',
                    'difficulty fallback answer',
                    'difficulty fallback explanation',
                    '어려움',
                    '테스트기관',
                    '브라우저 회귀',
                    '테스트',
                    now,
                    now,
                ),
            )
            conn.commit()

        cls.wiki_book_dir = write_test_wiki_book(cls.temp_root)
        cls.port = free_port()
        cls.base_url = f'http://127.0.0.1:{cls.port}'
        env = os.environ.copy()
        env.update(
            {
                'CS_FLASHCARD_PROGRESS_DB': str(cls.progress_db_path),
                'CS_FLASHCARD_BACKUP_DIR': str(cls.temp_root / 'backups'),
                'CS_FLASHCARDS_WIKI_BOOK_DIR': str(cls.wiki_book_dir),
                'CS_FLASHCARDS_USERNAME': 'cs',
                'CS_FLASHCARDS_PASSWORD': '',
                'PYTHONUNBUFFERED': '1',
            }
        )
        python_path = frontend_browser_server_python(ROOT)
        cls.server = subprocess.Popen(
            [str(python_path), '-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', str(cls.port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_for_http_ok(f'{cls.base_url}/api/health')
        cls.transcript_cases: list[dict[str, object]] = []

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            if hasattr(cls, 'server') and cls.server.poll() is None:
                cls.server.terminate()
                try:
                    cls.server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    cls.server.kill()
                    cls.server.wait(timeout=10)
            if getattr(cls, 'transcript_cases', None):
                payload = {
                    'schema_version': 1,
                    'wave_id': transcript_wave_id(),
                    'branch': current_branch_name(),
                    'command': CANONICAL_COMMAND,
                    'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    'base_url': cls.base_url,
                    'cases': cls.transcript_cases,
                }
                TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
                transcript_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        finally:
            if hasattr(cls, '_temp_dir'):
                cls._temp_dir.cleanup()
            super().tearDownClass()

    async def asyncSetUp(self) -> None:
        launch_options = {
            'headless': True,
            'args': ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
            'handleSIGINT': False,
            'handleSIGTERM': False,
            'handleSIGHUP': False,
            'autoClose': False,
        }
        if self.__class__.browser_executable_path:
            launch_options['executablePath'] = self.__class__.browser_executable_path
        self.browser = await launch(**launch_options)

    async def asyncTearDown(self) -> None:
        await self.browser.close()

    async def new_page(self, *, viewport: dict[str, int] | None = None, local_storage: dict[str, str] | None = None):
        page = await self.browser.newPage()
        if viewport:
            await page.setViewport(viewport)
        if local_storage:
            script = """
            (entries) => {
              for (const [key, value] of Object.entries(entries || {})) {
                window.localStorage.setItem(key, value);
              }
            }
            """
            await page.evaluateOnNewDocument(script, local_storage)
        return page

    async def text(self, page, selector: str) -> str:
        return await page.Jeval(selector, '(node) => (node.textContent || "").trim()')

    async def attr(self, page, selector: str, name: str) -> str:
        return await page.Jeval(selector, '(node, attributeName) => node.getAttribute(attributeName) || ""', name)

    async def install_delayed_json_route(self, page, *, route_path: str, key_param: str, responses: dict[str, dict[str, object]]) -> None:
        await page.evaluate(
            """
            ({ routePath, keyParam, responses }) => {
              const originalFetch = window.fetch.bind(window);
              window.fetch = (input, init = undefined) => {
                const url = typeof input === 'string' ? input : input.url;
                const parsed = new URL(url, window.location.origin);
                if (parsed.pathname !== routePath) return originalFetch(input, init);
                const key = parsed.searchParams.get(keyParam) || '';
                const config = responses[key];
                if (!config) return originalFetch(input, init);
                return new Promise((resolve) => {
                  window.setTimeout(() => {
                    resolve(new Response(JSON.stringify(config.payload), {
                      status: 200,
                      headers: {'Content-Type': 'application/json'},
                    }));
                  }, Number(config.delayMs || 0));
                });
              };
            }
            """,
            {'routePath': route_path, 'keyParam': key_param, 'responses': responses},
        )

    async def set_input_value(self, page, selector: str, value: str, *, submit: bool = False) -> None:
        await page.evaluate(
            """
            ({ selector, value, submit }) => {
              const input = document.querySelector(selector);
              if (!input) return;
              input.focus();
              input.value = value;
              input.dispatchEvent(new Event('input', {bubbles: true}));
              if (submit) {
                input.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
              }
            }
            """,
            {'selector': selector, 'value': value, 'submit': submit},
        )

    def question_bank_item(self, label: str, *, status: str = 'unseen', **overrides: object) -> dict[str, object]:
        status_labels = {'unseen': '안푼', 'wrong': '틀린', 'correct': '맞은'}
        item: dict[str, object] = {
            'question_bank_id': f'{label}-1',
            'prompt': f'{label} prompt',
            'body': f'{label} body',
            'answer': f'{label} answer',
            'explanation': f'{label} explanation',
            'question_type': 'subjective',
            'keywords': [label],
            'difficulty': '중',
            'issuer': '테스트기관',
            'source_location': '테스트출처',
            'category': '테스트',
            'field_name': '테스트분야',
            'question_attempt_status': status,
            'question_attempt_status_label': status_labels[status],
        }
        item.update(overrides)
        return item

    def question_bank_payload(self, label: str, *, items: list[dict[str, object]] | None = None) -> dict[str, object]:
        payload_items = list(items) if items is not None else [self.question_bank_item(label)]
        available_topics: list[str] = []
        for item in payload_items:
            for keyword in item.get('keywords') or []:
                text = str(keyword or '').strip()
                if text and text not in available_topics:
                    available_topics.append(text)
        return {
            'items': payload_items,
            'summary': {
                'total': len(payload_items),
                'returned': len(payload_items),
                'available_topics': available_topics or [label],
                'available_field_names': ['테스트분야'],
                'available_issuers': ['테스트기관'],
                'available_categories': ['테스트'],
                'category_breakdown': [],
            },
        }

    def question_history_payload(self, title: str, result_key: str) -> dict[str, object]:
        return {
            'items': [
                {
                    'card_id': 'CS-001',
                    'term': title,
                    'card_category': '테스트',
                    'question_type': 'subjective',
                    'prompt': f'{title} prompt',
                    'body': f'{title} body',
                    'result_key': result_key,
                    'result_label': title,
                    'user_answer': title,
                    'updated_at': '2026-08-01T00:00:00Z',
                }
            ],
            'summary': {
                'selected_card_count': 1,
                'total': 1,
                'correct': 1 if result_key == 'correct' else 0,
                'ambiguous': 0,
                'wrong': 1 if result_key == 'wrong' else 0,
                'unknown': 0,
                'pending': 0,
                'returned': 1,
                'filter': result_key,
            },
        }


    def record_case(self, *, case_id: str, status: str, observations: dict[str, object]) -> None:
        self.__class__.transcript_cases.append(
            {
                'id': case_id,
                'status': status,
                'url': self.base_url,
                'observations': observations,
            }
        )

    async def test_flashcard_dialog_focus_trap_and_question_panel_restore_opener(self):
        case = {'path': '/'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.waitForSelector('#menuBtn')
            await page.focus('#menuBtn')
            await page.evaluate('toggleQuestionMode(true)')
            await page.waitForFunction("document.querySelector('#questionPanel').hidden === false")
            case['question_panel_focus_on_open'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['question_panel_focus_on_open'], 'closeQuestionModeBtn')

            await page.click('#openQuestionImportBtn')
            await page.waitForFunction("document.querySelector('#questionImportDialog').hidden === false")
            case['question_import_focus_on_open'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['question_import_focus_on_open'], 'questionImportInput')

            await page.focus('#questionImportApplyBtn')
            await page.keyboard.press('Tab')
            case['question_import_focus_after_wrap'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['question_import_focus_after_wrap'], 'questionImportCloseBtn')

            await page.keyboard.press('Escape')
            await page.waitForFunction("document.querySelector('#questionImportDialog').hidden === true")
            case['question_import_focus_after_close'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['question_import_focus_after_close'], 'openQuestionImportBtn')

            await page.keyboard.press('Escape')
            await page.waitForFunction("document.querySelector('#questionPanel').hidden === true")
            case['question_panel_focus_after_close'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['question_panel_focus_after_close'], 'menuBtn')

            await page.click('#menuBtn')
            await page.click('#memoListBtn')
            await page.waitForFunction("document.querySelector('#memoListDialog').hidden === false")
            case['memo_dialog_focus_on_open'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['memo_dialog_focus_on_open'], 'memoListCloseBtn')

            await page.keyboard.press('Escape')
            await page.waitForFunction("document.querySelector('#memoListDialog').hidden === true")
            case['memo_dialog_focus_after_close'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['memo_dialog_focus_after_close'], 'menuBtn')
            status = 'passed'
        finally:
            self.record_case(case_id='modal-focus-restore', status=status, observations=case)
            await page.close()

    async def test_concept_image_dialog_focus_traps_embedded_media_and_restores_opener(self):
        case = {'path': '/'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.waitForSelector('#conceptImageZoomBtn')
            await page.keyboard.press(' ')
            await page.waitForFunction("document.querySelector('#card').classList.contains('flipped')")
            await page.waitForFunction("document.querySelector('#conceptMediaEditBtn') && !document.querySelector('#conceptMediaEditBtn').closest('[hidden]')")
            await page.evaluate("document.querySelector('#conceptMediaEditBtn')?.click()")
            await page.waitForFunction("document.querySelector('#conceptMediaDialog').hidden === false")
            await page.select('#conceptMediaTypeInput', 'html')
            await self.set_input_value(
                page,
                '#conceptMediaPayloadInput',
                '<div style="padding:12px;display:grid;gap:12px;"><button type="button" id="embeddedHtmlButton">임베디드 버튼</button><video id="embeddedHtmlVideo" controls aria-label="임베디드 비디오"></video></div>',
            )
            await self.set_input_value(page, '#conceptMediaAltInput', '임베디드 HTML 비디오')
            await page.evaluate("document.querySelector('#conceptMediaDialogSaveBtn')?.click()")
            await page.waitForFunction("document.querySelector('#conceptMediaDialog').hidden === true")
            await page.waitForFunction("document.querySelector('#backConceptHtmlFrame') && document.querySelector('#backConceptHtmlFrame').hidden === false")
            await page.focus('#conceptImageZoomBtn')
            await page.evaluate("document.querySelector('#conceptImageZoomBtn')?.click()")
            await page.waitForFunction("document.querySelector('#conceptImageDialog').hidden === false")
            case['html_focus_on_open'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['html_focus_on_open'], 'conceptImageDialogCloseBtn')

            await page.keyboard.press('Tab')
            case['html_focus_after_tab'] = await page.evaluate(
                'document.activeElement ? `${document.activeElement.tagName}:${document.activeElement.className || ""}` : ""'
            )
            self.assertEqual(case['html_focus_after_tab'], 'IFRAME:concept-image-modal-iframe')

            await page.keyboard.down('Shift')
            await page.keyboard.press('Tab')
            await page.keyboard.up('Shift')
            case['html_focus_after_shift_tab'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['html_focus_after_shift_tab'], 'conceptImageDialogCloseBtn')

            await page.keyboard.press('Escape')
            await page.waitForFunction("document.querySelector('#conceptImageDialog').hidden === true")
            case['html_focus_after_close'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['html_focus_after_close'], 'conceptImageZoomBtn')

            await page.focus('#conceptImageZoomBtn')
            await page.evaluate("document.querySelector('#conceptImageZoomBtn')?.click()")
            await page.waitForFunction("document.querySelector('#conceptImageDialog').hidden === false")
            await page.evaluate(
                """
                () => {
                  const stage = document.querySelector('#conceptImageDialogStage');
                  if (!stage) return;
                  stage.innerHTML = '<video class="concept-image-modal-video" controls aria-label="모달 비디오"></video>';
                }
                """
            )
            case['video_focus_on_open'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['video_focus_on_open'], 'conceptImageDialogCloseBtn')

            await page.keyboard.press('Tab')
            case['video_focus_after_tab'] = await page.evaluate(
                'document.activeElement ? `${document.activeElement.tagName}:${document.activeElement.className || ""}` : ""'
            )
            self.assertEqual(case['video_focus_after_tab'], 'VIDEO:concept-image-modal-video')

            await page.keyboard.down('Shift')
            await page.keyboard.press('Tab')
            await page.keyboard.up('Shift')
            case['video_focus_after_shift_tab'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['video_focus_after_shift_tab'], 'conceptImageDialogCloseBtn')

            await page.keyboard.press('Escape')
            await page.waitForFunction("document.querySelector('#conceptImageDialog').hidden === true")
            case['video_focus_after_close'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['video_focus_after_close'], 'conceptImageZoomBtn')
            status = 'passed'
        finally:
            self.record_case(case_id='concept-image-modal-focus', status=status, observations=case)
            await page.close()
    async def test_question_bank_page_loads_filters_and_launches_embedded_practice(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            case['initial_summary'] = await self.text(page, '#bankPageSummary')
            self.assertIn('문항', case['initial_summary'])
            case['filters_collapsed_initially'] = await page.evaluate("document.body.classList.contains('question-bank-filters-collapsed')")
            self.assertTrue(case['filters_collapsed_initially'])
            await page.click('#bankPageToggleFiltersBtn')
            await page.waitForFunction("!document.body.classList.contains('question-bank-filters-collapsed')")
            await page.type('#bankPageQueryInput', '데이터베이스')
            await page.waitForFunction("window.location.search.includes('q=%EB%8D%B0%EC%9D%B4%ED%84%B0%EB%B2%A0%EC%9D%B4%EC%8A%A4')")
            await page.waitForFunction("document.querySelector('#bankPageActiveFilters').textContent.includes('통합 검색')")
            case['active_filters'] = await self.text(page, '#bankPageActiveFilters')
            await page.click('#bankPageLaunchBtn')
            await page.waitForFunction("!document.querySelector('#bankPagePracticeFrame').hidden")
            case['practice_frame_src'] = await page.Jeval('#bankPagePracticeFrame', '(node) => node.getAttribute("src") || ""')
            self.assertIn('question-bank-embed=1', case['practice_frame_src'])
            await page.waitForFunction(
                '(key) => !window.sessionStorage.getItem(key)',
                {},
                QUESTION_BANK_LAUNCH_KEY,
            )
            case['launch_state_present'] = await page.evaluate(
                '(key) => Boolean(window.sessionStorage.getItem(key))',
                QUESTION_BANK_LAUNCH_KEY,
            )
            self.assertFalse(case['launch_state_present'])
            case['practice_status'] = await self.text(page, '#bankPagePracticeStatus')
            self.assertIn('현재 1 /', case['practice_status'])
            await page.evaluate('document.querySelector("#bankPageRefreshBtn").click()')
            await page.waitForFunction("document.querySelector('#bankPageSummary').textContent.includes('총')")
            case['practice_frame_src_after_refresh'] = await page.Jeval('#bankPagePracticeFrame', '(node) => node.getAttribute("src") || ""')
            self.assertEqual(case['practice_frame_src_after_refresh'], case['practice_frame_src'])
            case['practice_status_after_refresh'] = await self.text(page, '#bankPagePracticeStatus')
            self.assertIn('현재 1 /', case['practice_status_after_refresh'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-load-launch', status=status, observations=case)
            await page.close()

    async def test_question_bank_filter_refresh_keeps_hidden_practice_inert_until_explicit_launch(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.evaluateOnNewDocument(
                """
                () => {
                  window.__confirmCalls = [];
                  window.confirm = (message) => {
                    window.__confirmCalls.push({message, allow: false});
                    return false;
                  };
                }
                """
            )
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 1")
            await page.click('#bankPageLaunchBtn')
            await page.waitForFunction("!document.querySelector('#bankPagePracticeFrame').hidden")
            case['initial_frame_src'] = await page.Jeval('#bankPagePracticeFrame', '(node) => node.getAttribute("src") || ""')

            embed_frame = next(frame for frame in page.frames if 'question-bank-embed=1' in frame.url)
            case['draft_mode'] = await embed_frame.evaluate(
                """
                () => {
                  const answerInput = document.getElementById('questionAnswerInput');
                  if (answerInput) {
                    answerInput.value = 'draft answer';
                    answerInput.dispatchEvent(new Event('input', {bubbles: true}));
                    return 'text';
                  }
                  const choiceButton = document.querySelector('.question-choice');
                  if (choiceButton) {
                    choiceButton.click();
                    return 'choice';
                  }
                  return 'none';
                }
                """
            )
            self.assertNotEqual(case['draft_mode'], 'none')

            await page.evaluate('document.getElementById("bankPageTogglePracticeBtn").click()')
            await page.waitForFunction("document.body.classList.contains('question-bank-practice-collapsed')")
            case['practice_collapsed_after_toggle'] = await page.evaluate("document.body.classList.contains('question-bank-practice-collapsed')")
            self.assertTrue(case['practice_collapsed_after_toggle'])

            await page.click('#bankPageToggleFiltersBtn')
            await page.waitForFunction("!document.body.classList.contains('question-bank-filters-collapsed')")
            await page.type('#bankPageQueryInput', '데이터베이스')
            await page.waitForFunction("window.location.search.includes('q=%EB%8D%B0%EC%9D%B4%ED%84%B0%EB%B2%A0%EC%9D%B4%EC%8A%A4')")
            await page.waitForFunction("document.querySelector('#bankPageSummary').textContent.includes('총')")
            case['confirm_calls_after_filter'] = await page.evaluate('window.__confirmCalls.length')
            case['frame_src_after_filter'] = await page.Jeval('#bankPagePracticeFrame', '(node) => node.getAttribute("src") || ""')
            self.assertEqual(case['confirm_calls_after_filter'], 0)
            self.assertEqual(case['frame_src_after_filter'], case['initial_frame_src'])

            await page.click('#bankPageResetFiltersBtn')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 1")
            await page.evaluate('document.querySelector("#bankPageList tbody tr:nth-child(2) .question-bank-row-trigger").click()')
            await page.waitForFunction('window.__confirmCalls.length === 1')
            case['frame_src_after_launch_cancel'] = await page.Jeval('#bankPagePracticeFrame', '(node) => node.getAttribute("src") || ""')
            self.assertEqual(case['frame_src_after_launch_cancel'], case['initial_frame_src'])

            await page.evaluate(
                """
                () => {
                  window.confirm = (message) => {
                    window.__confirmCalls.push({message, allow: true});
                    return true;
                  };
                }
                """
            )
            await page.evaluate('document.querySelector("#bankPageList tbody tr:nth-child(2) .question-bank-row-trigger").click()')
            await page.waitForFunction('window.__confirmCalls.length === 2')
            await page.waitForFunction(
                '(initialSrc) => (document.querySelector("#bankPagePracticeFrame")?.getAttribute("src") || "") !== initialSrc',
                {},
                case['initial_frame_src'],
            )
            case['frame_src_after_launch_confirm'] = await page.Jeval('#bankPagePracticeFrame', '(node) => node.getAttribute("src") || ""')
            self.assertNotEqual(case['frame_src_after_launch_confirm'], case['initial_frame_src'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-hidden-practice-refresh', status=status, observations=case)
            await page.close()

    async def test_question_bank_row_change_confirms_before_discarding_in_progress_state(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.evaluateOnNewDocument(
                """
                () => {
                  window.__confirmCalls = [];
                  window.confirm = (message) => {
                    window.__confirmCalls.push({message, allow: false});
                    return false;
                  };
                }
                """
            )
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 1")
            await page.click('#bankPageLaunchBtn')
            await page.waitForFunction("!document.querySelector('#bankPagePracticeFrame').hidden")
            case['initial_frame_src'] = await page.Jeval('#bankPagePracticeFrame', '(node) => node.getAttribute("src") || ""')
            case['initial_active_row'] = await page.evaluate("document.querySelector('#bankPageList [aria-current=\"true\"]')?.getAttribute('data-table-row-id') || ''")

            embed_frame = next(frame for frame in page.frames if 'question-bank-embed=1' in frame.url)
            case['draft_mode'] = await embed_frame.evaluate(
                """
                () => {
                  const answerInput = document.getElementById('questionAnswerInput');
                  if (answerInput) {
                    answerInput.value = 'draft answer';
                    answerInput.dispatchEvent(new Event('input', {bubbles: true}));
                    return 'text';
                  }
                  const choiceButton = document.querySelector('.question-choice');
                  if (choiceButton) {
                    choiceButton.click();
                    return 'choice';
                  }
                  return 'none';
                }
                """
            )
            self.assertNotEqual(case['draft_mode'], 'none')

            await page.evaluate('document.querySelector("#bankPageList tbody tr:nth-child(2) .question-bank-row-trigger").click()')
            await page.waitForFunction('window.__confirmCalls.length === 1')
            case['frame_src_after_cancel'] = await page.Jeval('#bankPagePracticeFrame', '(node) => node.getAttribute("src") || ""')
            case['active_row_after_cancel'] = await page.evaluate("document.querySelector('#bankPageList [aria-current=\"true\"]')?.getAttribute('data-table-row-id') || ''")
            self.assertEqual(case['frame_src_after_cancel'], case['initial_frame_src'])
            self.assertEqual(case['active_row_after_cancel'], case['initial_active_row'])

            await page.evaluate(
                """
                () => {
                  window.confirm = (message) => {
                    window.__confirmCalls.push({message, allow: true});
                    return true;
                  };
                }
                """
            )
            await page.evaluate('document.querySelector("#bankPageList tbody tr:nth-child(2) .question-bank-row-trigger").click()')
            await page.waitForFunction('window.__confirmCalls.length === 2')
            await page.waitForFunction(
                '(initialSrc) => (document.querySelector("#bankPagePracticeFrame")?.getAttribute("src") || "") !== initialSrc',
                {},
                case['initial_frame_src'],
            )
            case['frame_src_after_confirm'] = await page.Jeval('#bankPagePracticeFrame', '(node) => node.getAttribute("src") || ""')
            case['active_row_after_confirm'] = await page.evaluate("document.querySelector('#bankPageList [aria-current=\"true\"]')?.getAttribute('data-table-row-id') || ''")
            self.assertNotEqual(case['frame_src_after_confirm'], case['initial_frame_src'])
            self.assertNotEqual(case['active_row_after_confirm'], case['initial_active_row'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-row-change-confirm', status=status, observations=case)
            await page.close()

    async def test_question_bank_embed_consumes_pending_launch_before_cards_fetch_resolves(self):
        case = {'path': '/?question-bank-embed=1'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        pending_item = self.question_bank_item('embed bootstrap')
        pending_payload = {'items': [pending_item], 'startIndex': 0}
        try:
            await page.evaluateOnNewDocument(
                """
                ({ launchKey, payload }) => {
                  window.__cardsFetchStarted = 0;
                  window.__cardsFetchResolved = 0;
                  window.__releaseCardsFetch = null;
                  const originalFetch = window.fetch.bind(window);
                  const pendingCardsFetch = new Promise((resolve) => {
                    window.__releaseCardsFetch = resolve;
                  });
                  window.sessionStorage.setItem(launchKey, JSON.stringify(payload));
                  window.fetch = (input, init = undefined) => {
                    const url = typeof input === 'string' ? input : input.url;
                    const parsed = new URL(url, window.location.origin);
                    if (parsed.pathname === '/api/cards') {
                      window.__cardsFetchStarted += 1;
                      return pendingCardsFetch.then(() => {
                        window.__cardsFetchResolved += 1;
                        return originalFetch(input, init);
                      });
                    }
                    return originalFetch(input, init);
                  };
                }
                """,
                {'launchKey': QUESTION_BANK_LAUNCH_KEY, 'payload': pending_payload},
            )
            await page.goto(f'{self.base_url}/?question-bank-embed=1', waitUntil='domcontentloaded')
            await page.waitForFunction("document.getElementById('questionPanel') && document.getElementById('questionPanel').hidden === false")
            await page.waitForFunction("document.querySelector('.question-prompt') && document.querySelector('.question-prompt').textContent.includes('embed bootstrap prompt')")
            case['cards_fetch_started_before_prompt'] = await page.evaluate('window.__cardsFetchStarted')
            self.assertEqual(case['cards_fetch_started_before_prompt'], 1)
            case['question_prompt'] = await page.Jeval('.question-prompt', '(node) => (node.textContent || "").trim()')
            self.assertIn('embed bootstrap prompt', case['question_prompt'])
            await page.evaluate('window.__releaseCardsFetch()')
            await page.waitForFunction('window.__cardsFetchResolved === 1')
            await page.waitForFunction("document.getElementById('questionPanel') && document.getElementById('questionPanel').hidden === false")
            case['question_panel_hidden_after_cards_fetch'] = await page.evaluate("document.getElementById('questionPanel')?.hidden ?? true")
            case['question_prompt_after_cards_fetch'] = await page.Jeval('.question-prompt', '(node) => (node.textContent || "").trim()')
            self.assertFalse(case['question_panel_hidden_after_cards_fetch'])
            self.assertIn('embed bootstrap prompt', case['question_prompt_after_cards_fetch'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-embed-bootstrap', status=status, observations=case)
            await page.close()
    async def test_question_bank_category_guide_traps_focus_and_restores_opener(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await page.focus('#bankPageCategoryGuideBtn')
            await page.click('#bankPageCategoryGuideBtn')
            await page.waitForFunction("document.getElementById('bankPageCategoryGuideDialog').hidden === false")
            await page.waitForFunction("document.activeElement && document.activeElement.id === 'bankPageCategoryGuideCloseBtn'")
            case['initial_focus'] = await page.evaluate("document.activeElement && document.activeElement.id")
            self.assertEqual(case['initial_focus'], 'bankPageCategoryGuideCloseBtn')
            case['focus_inside_after_open'] = await page.evaluate(
                "document.getElementById('bankPageCategoryGuideDialog').contains(document.activeElement)"
            )
            self.assertTrue(case['focus_inside_after_open'])

            await page.keyboard.press('Tab')
            case['focus_after_tab'] = await page.evaluate("document.activeElement && document.activeElement.id")
            case['focus_inside_after_tab'] = await page.evaluate(
                "document.getElementById('bankPageCategoryGuideDialog').contains(document.activeElement)"
            )
            self.assertEqual(case['focus_after_tab'], 'bankPageCategoryGuideCloseBtn')
            self.assertTrue(case['focus_inside_after_tab'])

            await page.keyboard.down('Shift')
            await page.keyboard.press('Tab')
            await page.keyboard.up('Shift')
            case['focus_after_shift_tab'] = await page.evaluate("document.activeElement && document.activeElement.id")
            case['focus_inside_after_shift_tab'] = await page.evaluate(
                "document.getElementById('bankPageCategoryGuideDialog').contains(document.activeElement)"
            )
            self.assertEqual(case['focus_after_shift_tab'], 'bankPageCategoryGuideCloseBtn')
            self.assertTrue(case['focus_inside_after_shift_tab'])

            await page.keyboard.press('Escape')
            await page.waitForFunction("document.getElementById('bankPageCategoryGuideDialog').hidden === true")
            case['focus_after_escape'] = await page.evaluate("document.activeElement && document.activeElement.id")
            self.assertEqual(case['focus_after_escape'], 'bankPageCategoryGuideBtn')
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-category-guide-focus', status=status, observations=case)
            await page.close()

    async def test_question_bank_status_column_tracks_saved_attempt_state_across_filters_and_refresh(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        unseen_item = self.question_bank_item('안푼 문항', status='unseen')
        wrong_item = self.question_bank_item('틀린 문항', status='wrong')
        correct_item = self.question_bank_item('맞은 문항', status='correct')
        initial_payload = self.question_bank_payload('status-initial', items=[unseen_item, wrong_item, correct_item])
        reordered_payload = self.question_bank_payload('status-reordered', items=[correct_item, unseen_item, wrong_item])
        filtered_payload = self.question_bank_payload('status-filtered', items=[correct_item])
        table_snapshot = """
            () => {
              const headers = [...document.querySelectorAll('#bankPageList thead th')].map((node) => (node.textContent || '').trim());
              const statusIndex = headers.indexOf('풀이상태');
              const promptIndex = headers.indexOf('문제');
              return [...document.querySelectorAll('#bankPageList tbody tr')].map((row) => {
                const cells = [...row.querySelectorAll('td')].map((node) => (node.textContent || '').replace(/\\s+/g, ' ').trim());
                return {
                  prompt: promptIndex >= 0 ? (cells[promptIndex] || '') : '',
                  status: statusIndex >= 0 ? (cells[statusIndex] || '') : '',
                };
              });
            }
        """
        try:
            await page.evaluateOnNewDocument(
                """
                ({ initialPayload, reorderedPayload, filteredPayload }) => {
                  const originalFetch = window.fetch.bind(window);
                  const queues = {
                    '': [initialPayload, reorderedPayload, reorderedPayload],
                    correct: [filteredPayload],
                  };
                  window.fetch = (input, init = undefined) => {
                    const url = typeof input === 'string' ? input : input.url;
                    const parsed = new URL(url, window.location.origin);
                    if (parsed.pathname !== '/api/question-bank') return originalFetch(input, init);
                    const key = parsed.searchParams.get('attempt_status') || '';
                    const queue = queues[key];
                    if (!queue || !queue.length) return originalFetch(input, init);
                    const payload = queue.shift();
                    return Promise.resolve(new Response(JSON.stringify(payload), {
                      status: 200,
                      headers: {'Content-Type': 'application/json'},
                    }));
                  };
                }
                """,
                {
                    'initialPayload': initial_payload,
                    'reorderedPayload': reordered_payload,
                    'filteredPayload': filtered_payload,
                },
            )
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList tbody tr').length === 3")
            case['headers'] = await page.evaluate("() => [...document.querySelectorAll('#bankPageList thead th')].map((node) => (node.textContent || '').trim())")
            self.assertIn('풀이상태', case['headers'])
            case['initial_rows'] = await page.evaluate(table_snapshot)
            self.assertEqual([row['status'] for row in case['initial_rows']], ['안푼', '틀린', '맞은'])
            self.assertTrue(case['initial_rows'][0]['prompt'].startswith('안푼 문항 prompt'))
            await page.click('#bankPageToggleFiltersBtn')
            await page.waitForFunction("!document.body.classList.contains('question-bank-filters-collapsed')")
            await page.select('#bankPageAttemptStatusSelect', 'correct')
            await page.waitForFunction("document.querySelectorAll('#bankPageList tbody tr').length === 1")
            case['filtered_rows'] = await page.evaluate(table_snapshot)
            self.assertEqual([row['status'] for row in case['filtered_rows']], ['맞은'])
            self.assertTrue(case['filtered_rows'][0]['prompt'].startswith('맞은 문항 prompt'))
            await page.select('#bankPageAttemptStatusSelect', '')
            await page.waitForFunction(
                """
                () => {
                  const titles = [...document.querySelectorAll('#bankPageList tbody tr .question-bank-item-title')].map((node) => (node.textContent || '').trim());
                  return titles.length === 3 && titles[0] === '맞은 문항 prompt';
                }
                """
            )
            case['reloaded_rows'] = await page.evaluate(table_snapshot)
            self.assertEqual([row['status'] for row in case['reloaded_rows']], ['맞은', '안푼', '틀린'])
            await page.click('#bankPageRefreshBtn')
            await page.waitForFunction(
                """
                () => {
                  const titles = [...document.querySelectorAll('#bankPageList tbody tr .question-bank-item-title')].map((node) => (node.textContent || '').trim());
                  return titles.length === 3 && titles[0] === '맞은 문항 prompt';
                }
                """
            )
            case['refreshed_rows'] = await page.evaluate(table_snapshot)
            self.assertEqual(case['refreshed_rows'], case['reloaded_rows'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-status-column', status=status, observations=case)
            await page.close()

    async def test_question_bank_finish_grading_shows_score_and_wrong_highlights(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        wrong_item = self.question_bank_item(
            '첫 오답',
            question_type='multiple_choice',
            choices=['내 답', '정답'],
            answer='정답',
            answer_index=1,
            points=50,
        )
        correct_item = self.question_bank_item(
            '둘째 정답',
            question_type='multiple_choice',
            choices=['정답', '오답'],
            answer='정답',
            answer_index=0,
            points=50,
        )
        payload = self.question_bank_payload('finish-grading', items=[wrong_item, correct_item])
        try:
            await page.evaluateOnNewDocument(
                """
                (payload) => {
                  const originalFetch = window.fetch.bind(window);
                  window.fetch = (input, init = undefined) => {
                    const url = typeof input === 'string' ? input : input.url;
                    const parsed = new URL(url, window.location.origin);
                    if (parsed.pathname !== '/api/question-bank') return originalFetch(input, init);
                    return Promise.resolve(new Response(JSON.stringify(payload), {
                      status: 200,
                      headers: {'Content-Type': 'application/json'},
                    }));
                  };
                }
                """,
                payload,
            )
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList tbody tr').length === 2")
            await page.click('#bankPageLaunchBtn')
            await page.waitForFunction("!document.querySelector('#bankPagePracticeFrame').hidden")
            embed_frame = next(frame for frame in page.frames if 'question-bank-embed=1' in frame.url)

            await embed_frame.click('[data-choice-index="0"]')
            await embed_frame.click('[data-question-nav="next"]')
            await embed_frame.waitForFunction("document.querySelector('.question-prompt') && document.querySelector('.question-prompt').textContent.includes('둘째 정답 prompt')")
            await embed_frame.click('[data-choice-index="0"]')
            await embed_frame.evaluate("document.getElementById('finishQuestionSessionBtn').click()")

            await page.waitForFunction("document.querySelector('#bankPagePracticeStatus').textContent.includes('점수 50 / 100점')")
            case['practice_status'] = await self.text(page, '#bankPagePracticeStatus')
            case['header_summary'] = await self.text(page, '#bankPageHeaderSummary')
            case['overview_cards'] = await page.evaluate(
                "() => [...document.querySelectorAll('#bankPageOverviewCards .question-bank-metric-card')].map((node) => (node.textContent || '').replace(/\\s+/g, ' ').trim())"
            )
            case['table_rows'] = await page.evaluate(
                """
                () => [...document.querySelectorAll('#bankPageList tbody tr')].map((row) => ({
                  className: row.className,
                  status: (row.children[1]?.textContent || '').replace(/\s+/g, ' ').trim(),
                  numberClass: row.querySelector('.question-bank-row-number')?.className || '',
                }))
                """
            )
            self.assertIn('점수 50 / 100점', case['practice_status'])
            self.assertIn('채점 완료', case['header_summary'])
            self.assertTrue(any('50 / 100점' in card for card in case['overview_cards']))
            self.assertEqual(case['table_rows'][0]['status'], '틀린')
            self.assertIn('question-bank-row-state-wrong', case['table_rows'][0]['className'])
            self.assertIn('is-wrong', case['table_rows'][0]['numberClass'])
            self.assertEqual(case['table_rows'][1]['status'], '맞은')

            await embed_frame.evaluate("document.querySelector('[data-question-nav=\"prev\"]')?.click()")
            await embed_frame.waitForFunction("document.querySelector('.question-prompt') && document.querySelector('.question-prompt').textContent.includes('첫 오답 prompt')")
            case['choice_classes'] = await embed_frame.evaluate(
                "() => [...document.querySelectorAll('[data-choice-index]')].map((node) => ({text: (node.textContent || '').trim(), className: node.className}))"
            )
            self.assertIn('wrong', case['choice_classes'][0]['className'])
            self.assertIn('selected', case['choice_classes'][0]['className'])
            self.assertIn('answer', case['choice_classes'][1]['className'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-finish-grading-ui', status=status, observations=case)
            await page.close()

    async def test_question_bank_page_preserves_filters_across_reload_until_reset(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await page.click('#bankPageToggleFiltersBtn')
            await page.waitForFunction("!document.body.classList.contains('question-bank-filters-collapsed')")
            await page.type('#bankPageQueryInput', '데이터베이스')
            await page.select('#bankPageDifficultySelect', '중')
            await page.waitForFunction(
                "document.querySelector('#bankPageActiveFilters').textContent.includes('데이터베이스') && document.querySelector('#bankPageActiveFilters').textContent.includes('중')"
            )
            case['stored_filter_state_before_reload'] = await page.evaluate(
                '(key) => JSON.parse(window.localStorage.getItem(key) || "null")',
                QUESTION_BANK_FILTER_STATE_KEY,
            )
            self.assertEqual(case['stored_filter_state_before_reload']['filters']['q'], '데이터베이스')
            self.assertEqual(case['stored_filter_state_before_reload']['filters']['difficulty'], '중')
            self.assertFalse(case['stored_filter_state_before_reload']['filtersCollapsed'])

            await page.reload({'waitUntil': 'networkidle2'})
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await page.waitForFunction(
                "document.querySelector('#bankPageQueryInput').value === '데이터베이스' && document.querySelector('#bankPageDifficultySelect').value === '중'"
            )
            case['filters_expanded_after_reload'] = await page.evaluate(
                "!document.body.classList.contains('question-bank-filters-collapsed')"
            )
            case['query_after_reload'] = await page.Jeval('#bankPageQueryInput', '(node) => node.value')
            case['difficulty_after_reload'] = await page.Jeval('#bankPageDifficultySelect', '(node) => node.value')
            self.assertTrue(case['filters_expanded_after_reload'])
            self.assertEqual(case['query_after_reload'], '데이터베이스')
            self.assertEqual(case['difficulty_after_reload'], '중')

            await page.click('#bankPageActiveFilters [data-filter-key="q"]')
            await page.waitForFunction(
                "document.querySelector('#bankPageQueryInput').value === '' && document.querySelector('#bankPageDifficultySelect').value === '중' && !document.querySelector('#bankPageActiveFilters').textContent.includes('데이터베이스')"
            )
            case['stored_filter_state_after_chip_clear'] = await page.evaluate(
                '(key) => JSON.parse(window.localStorage.getItem(key) || "null")',
                QUESTION_BANK_FILTER_STATE_KEY,
            )
            self.assertEqual(case['stored_filter_state_after_chip_clear']['filters']['q'], '')
            self.assertEqual(case['stored_filter_state_after_chip_clear']['filters']['difficulty'], '중')

            await page.reload({'waitUntil': 'networkidle2'})
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await page.waitForFunction(
                "document.querySelector('#bankPageQueryInput').value === '' && document.querySelector('#bankPageDifficultySelect').value === '중'"
            )
            case['query_after_chip_clear_reload'] = await page.Jeval('#bankPageQueryInput', '(node) => node.value')
            case['difficulty_after_chip_clear_reload'] = await page.Jeval('#bankPageDifficultySelect', '(node) => node.value')
            case['active_filters_after_chip_clear_reload'] = await self.text(page, '#bankPageActiveFilters')
            self.assertEqual(case['query_after_chip_clear_reload'], '')
            self.assertEqual(case['difficulty_after_chip_clear_reload'], '중')
            self.assertNotIn('데이터베이스', case['active_filters_after_chip_clear_reload'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-filter-reload', status=status, observations=case)
            await page.close()

    async def test_question_bank_page_restores_filter_and_practice_pane_state_across_reload(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await page.click('#bankPageToggleFiltersBtn')
            await page.waitForFunction("!document.body.classList.contains('question-bank-filters-collapsed')")
            await page.evaluate('document.querySelector("#bankPageList tbody tr:nth-child(2) .question-bank-row-trigger").click()')
            await page.waitForFunction(
                "!document.body.classList.contains('question-bank-practice-collapsed') && !document.querySelector('#bankPagePracticeFrame').hidden"
            )
            case['practice_status_before_reload'] = await self.text(page, '#bankPagePracticeStatus')
            self.assertIn('현재 2 /', case['practice_status_before_reload'])
            case['active_row_before_reload'] = await page.evaluate(
                "document.querySelector('#bankPageList [aria-current=\"true\"]')?.getAttribute('data-table-row-id') || ''"
            )
            embed_frame = next(frame for frame in page.frames if 'question-bank-embed=1' in frame.url)
            case['practice_prompt_before_reload'] = await embed_frame.Jeval('.question-prompt', '(node) => (node.textContent || "").trim()')
            case['stored_open_state'] = await page.evaluate(
                """
                (filterKey, practiceKey) => ({
                  filterState: JSON.parse(window.localStorage.getItem(filterKey) || 'null'),
                  practiceCollapsed: window.localStorage.getItem(practiceKey),
                })
                """,
                QUESTION_BANK_FILTER_STATE_KEY,
                QUESTION_BANK_PRACTICE_COLLAPSED_KEY,
            )
            self.assertTrue(case['stored_open_state']['filterState']['practice']['loaded'])

            await page.reload({'waitUntil': 'networkidle2'})
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await page.waitForFunction(
                "!document.body.classList.contains('question-bank-filters-collapsed') && !document.body.classList.contains('question-bank-practice-collapsed') && !document.querySelector('#bankPagePracticeFrame').hidden"
            )
            case['open_state_after_reload'] = await page.evaluate(
                """
                () => ({
                  filtersCollapsed: document.body.classList.contains('question-bank-filters-collapsed'),
                  practiceCollapsed: document.body.classList.contains('question-bank-practice-collapsed'),
                  practiceFrameHidden: document.querySelector('#bankPagePracticeFrame').hidden,
                })
                """
            )
            case['practice_status_after_reload'] = await self.text(page, '#bankPagePracticeStatus')
            case['active_row_after_reload'] = await page.evaluate(
                "document.querySelector('#bankPageList [aria-current=\"true\"]')?.getAttribute('data-table-row-id') || ''"
            )
            reloaded_embed_frame = next(frame for frame in page.frames if 'question-bank-embed=1' in frame.url)
            case['practice_prompt_after_reload'] = await reloaded_embed_frame.Jeval('.question-prompt', '(node) => (node.textContent || "").trim()')
            self.assertFalse(case['open_state_after_reload']['filtersCollapsed'])
            self.assertFalse(case['open_state_after_reload']['practiceCollapsed'])
            self.assertFalse(case['open_state_after_reload']['practiceFrameHidden'])
            self.assertIn('현재 2 /', case['practice_status_after_reload'])
            self.assertEqual(case['active_row_after_reload'], case['active_row_before_reload'])
            self.assertEqual(case['practice_prompt_after_reload'], case['practice_prompt_before_reload'])
            await page.click('#bankPagePracticeExitBtn')
            await page.waitForFunction("document.body.classList.contains('question-bank-practice-collapsed')")
            await page.click('#bankPageToggleFiltersBtn')
            await page.waitForFunction("document.body.classList.contains('question-bank-filters-collapsed')")
            case['stored_closed_state'] = await page.evaluate(
                """
                (filterKey, practiceKey) => ({
                  filterState: JSON.parse(window.localStorage.getItem(filterKey) || 'null'),
                  practiceCollapsed: window.localStorage.getItem(practiceKey),
                })
                """,
                QUESTION_BANK_FILTER_STATE_KEY,
                QUESTION_BANK_PRACTICE_COLLAPSED_KEY,
            )
            self.assertTrue(case['stored_closed_state']['filterState']['filtersCollapsed'])
            self.assertTrue(case['stored_closed_state']['filterState']['practice']['loaded'])
            self.assertEqual(case['stored_closed_state']['practiceCollapsed'], '1')


            await page.reload({'waitUntil': 'networkidle2'})
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await page.waitForFunction(
                "document.body.classList.contains('question-bank-filters-collapsed') && document.body.classList.contains('question-bank-practice-collapsed') && document.querySelector('#bankPagePracticeFrame').hidden"
            )
            case['closed_state_after_reload'] = await page.evaluate(
                """
                () => ({
                  filtersCollapsed: document.body.classList.contains('question-bank-filters-collapsed'),
                  practiceCollapsed: document.body.classList.contains('question-bank-practice-collapsed'),
                  practiceFrameHidden: document.querySelector('#bankPagePracticeFrame').hidden,
                })
                """
            )
            case['active_row_after_collapsed_reload'] = await page.evaluate(
                "document.querySelector('#bankPageList [aria-current=\"true\"]')?.getAttribute('data-table-row-id') || ''"
            )
            self.assertTrue(case['closed_state_after_reload']['filtersCollapsed'])
            self.assertTrue(case['closed_state_after_reload']['practiceCollapsed'])
            self.assertTrue(case['closed_state_after_reload']['practiceFrameHidden'])
            self.assertEqual(case['active_row_after_collapsed_reload'], case['active_row_before_reload'])
            await page.click('#bankPageLaunchSelectedBtn')
            await page.waitForFunction(
                "!document.body.classList.contains('question-bank-practice-collapsed') && !document.querySelector('#bankPagePracticeFrame').hidden"
            )
            reopened_embed_frame = next(frame for frame in page.frames if 'question-bank-embed=1' in frame.url)
            case['practice_prompt_after_collapsed_reopen'] = await reopened_embed_frame.Jeval('.question-prompt', '(node) => (node.textContent || "").trim()')
            self.assertEqual(case['practice_prompt_after_collapsed_reopen'], case['practice_prompt_before_reload'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-pane-state-reload', status=status, observations=case)
            await page.close()

    async def test_question_bank_page_does_not_reopen_practice_from_stale_open_bit_without_session(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await page.evaluate(
                """
                (filterKey, practiceKey) => {
                  window.localStorage.setItem(filterKey, JSON.stringify({
                    filters: {},
                    filtersCollapsed: false,
                    practice: {loaded: false, selectedId: '', startIndex: 1},
                  }));
                  window.localStorage.setItem(practiceKey, '0');
                }
                """,
                QUESTION_BANK_FILTER_STATE_KEY,
                QUESTION_BANK_PRACTICE_COLLAPSED_KEY,
            )
            await page.reload({'waitUntil': 'networkidle2'})
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await page.waitForFunction(
                "!document.body.classList.contains('question-bank-filters-collapsed') && document.body.classList.contains('question-bank-practice-collapsed') && document.querySelector('#bankPagePracticeFrame').hidden"
            )
            case['state_after_reload'] = await page.evaluate(
                """
                () => ({
                  filtersCollapsed: document.body.classList.contains('question-bank-filters-collapsed'),
                  practiceCollapsed: document.body.classList.contains('question-bank-practice-collapsed'),
                  practiceFrameHidden: document.querySelector('#bankPagePracticeFrame').hidden,
                  practiceToggleDisabled: document.querySelector('#bankPageTogglePracticeBtn').disabled,
                })
                """
            )
            self.assertFalse(case['state_after_reload']['filtersCollapsed'])
            self.assertTrue(case['state_after_reload']['practiceCollapsed'])
            self.assertTrue(case['state_after_reload']['practiceFrameHidden'])
            self.assertTrue(case['state_after_reload']['practiceToggleDisabled'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-stale-open-bit', status=status, observations=case)
            await page.close()

    async def test_question_bank_page_renders_runtime_fallback_difficulty_label(self):
        case = {'path': '/question-bank', 'query': self.__class__.difficulty_regression_prompt}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await page.click('#bankPageToggleFiltersBtn')
            await page.waitForFunction("!document.body.classList.contains('question-bank-filters-collapsed')")
            await self.set_input_value(page, '#bankPageQueryInput', self.__class__.difficulty_regression_prompt)
            await page.waitForFunction(
                """
                (expectedPrompt, expectedId) => {
                  const rows = document.querySelectorAll('#bankPageList [data-table-row-id]');
                  const pill = document.querySelector('#bankPageList .question-bank-difficulty-pill');
                  return rows.length === 1
                    && rows[0].getAttribute('data-table-row-id') === expectedId
                    && document.querySelector('#bankPageList').textContent.includes(expectedPrompt)
                    && pill
                    && pill.textContent.trim() === '상';
                }
                """,
                {},
                self.__class__.difficulty_regression_prompt,
                self.__class__.difficulty_regression_question_id,
            )
            case['summary'] = await self.text(page, '#bankPageSummary')
            case['difficulty_label'] = await self.text(page, '#bankPageList .question-bank-difficulty-pill')
            self.assertIn('현재 1문항', case['summary'])
            self.assertEqual(case['difficulty_label'], '상')
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-runtime-difficulty-label', status=status, observations=case)
            await page.close()
    async def test_question_bank_page_rejects_stale_query_responses(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await self.install_delayed_json_route(
                page,
                route_path='/api/question-bank',
                key_param='q',
                responses={
                    'first': {'delayMs': 450, 'payload': self.question_bank_payload('first')},
                    'second': {'delayMs': 0, 'payload': self.question_bank_payload('second')},
                },
            )
            await self.set_input_value(page, '#bankPageQueryInput', 'first', submit=True)
            await self.set_input_value(page, '#bankPageQueryInput', 'second', submit=True)
            await page.waitForFunction("document.querySelector('#bankPageActiveFilters').textContent.includes('second')")
            await page.waitForFunction("document.querySelector('#bankPageList').textContent.includes('second prompt')")
            await asyncio.sleep(0.6)
            case['active_filters'] = await self.text(page, '#bankPageActiveFilters')
            case['summary'] = await self.text(page, '#bankPageSummary')
            case['first_row_text'] = await self.text(page, '#bankPageList')
            self.assertIn('second', case['active_filters'])
            self.assertIn('second prompt', case['first_row_text'])
            self.assertNotIn('first prompt', case['first_row_text'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-stale-query', status=status, observations=case)
            await page.close()

    async def test_embedded_question_bank_and_history_reject_stale_responses(self):
        case = {'path': '/'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.evaluate('toggleQuestionMode(true)')
            await page.waitForFunction("document.querySelector('#questionPanel').hidden === false")
            await page.click('#questionBankToggleBtn')
            await page.waitForFunction("document.querySelector('#questionBankBrowser').hidden === false")
            await self.install_delayed_json_route(
                page,
                route_path='/api/question-bank',
                key_param='q',
                responses={
                    'alpha': {'delayMs': 450, 'payload': self.question_bank_payload('alpha')},
                    'beta': {'delayMs': 0, 'payload': self.question_bank_payload('beta')},
                },
            )
            await self.set_input_value(page, '#questionBankQueryInput', 'alpha')
            await self.set_input_value(page, '#questionBankQueryInput', 'beta')
            await page.waitForFunction("document.querySelector('#questionBankList').textContent.includes('beta prompt')")
            await asyncio.sleep(0.6)
            case['embedded_question_bank_text'] = await self.text(page, '#questionBankList')
            self.assertIn('beta prompt', case['embedded_question_bank_text'])
            self.assertNotIn('alpha prompt', case['embedded_question_bank_text'])

            await self.install_delayed_json_route(
                page,
                route_path='/api/questions/attempts',
                key_param='result',
                responses={
                    'correct': {'delayMs': 450, 'payload': self.question_history_payload('늦은 정답', 'correct')},
                    'wrong': {'delayMs': 0, 'payload': self.question_history_payload('최신 오답', 'wrong')},
                },
            )
            await page.click('#questionHistoryBtn')
            await page.waitForFunction("document.querySelector('#questionHistoryDialog').hidden === false")
            await page.click('[data-question-history-filter="correct"]')
            await page.click('[data-question-history-filter="wrong"]')
            await page.waitForFunction("document.querySelector('#questionHistoryBody').textContent.includes('최신 오답')")
            await asyncio.sleep(0.6)
            case['question_history_text'] = await self.text(page, '#questionHistoryBody')
            self.assertIn('최신 오답', case['question_history_text'])
            self.assertNotIn('늦은 정답', case['question_history_text'])
            status = 'passed'
        finally:
            self.record_case(case_id='embedded-stale-response', status=status, observations=case)
            await page.close()
    async def test_calendar_tabs_and_detail_drawer_restore_focus(self):
        case = {'path': '/calendar'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(f'{self.base_url}/calendar', waitUntil='networkidle2')
            await page.waitForSelector('#mainTabCalendarBtn')
            await page.focus('#mainTabCalendarBtn')
            await page.keyboard.press('ArrowRight')
            await page.waitForFunction("document.querySelector('#mainTabListBtn').getAttribute('aria-selected') === 'true'")
            case['active_tab_after_keyboard'] = await self.attr(page, '#mainTabListBtn', 'aria-selected')
            await page.waitForFunction("document.querySelectorAll('#eventList [data-event-id]').length > 0")
            first_selector = '#eventList [data-event-id]'
            case['first_event_id'] = await page.Jeval(first_selector, '(node) => node.dataset.eventId || ""')
            await page.focus(first_selector)
            await page.keyboard.press('Enter')
            await page.waitForFunction("document.querySelector('#calendarDetailDrawer').hidden === false")
            case['drawer_hidden_after_open'] = await page.Jeval('#calendarDetailDrawer', '(node) => node.hidden')
            self.assertFalse(case['drawer_hidden_after_open'])
            case['focused_after_open'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['focused_after_open'], 'calendarDetailCloseBtn')
            await page.keyboard.press('Escape')
            await page.waitForFunction("document.querySelector('#calendarDetailDrawer').hidden === true")
            await page.waitForFunction(
                '() => { const drawer = document.querySelector("#calendarDetailDrawer"); return !drawer || !drawer.contains(document.activeElement); }'
            )
            case['focus_within_drawer_after_close'] = await page.evaluate(
                '() => { const drawer = document.querySelector("#calendarDetailDrawer"); return Boolean(drawer && drawer.contains(document.activeElement)); }'
            )
            self.assertFalse(case['focus_within_drawer_after_close'])
            case['focused_after_close'] = await page.evaluate(
                'document.activeElement && document.activeElement.id ? document.activeElement.id : (document.activeElement && document.activeElement.dataset ? (document.activeElement.dataset.eventId || (document.activeElement.tagName ? document.activeElement.tagName.toLowerCase() : "")) : (document.activeElement && document.activeElement.tagName ? document.activeElement.tagName.toLowerCase() : ""))'
            )
            status = 'passed'
        finally:
            self.record_case(case_id='calendar-drawer-focus', status=status, observations=case)
            await page.close()

    async def test_wiki_sidebar_state_restores_and_status_updates(self):
        case = {'path': '/wiki'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(f'{self.base_url}/wiki', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#wikiToc .wiki-toc-link').length > 0")
            await page.evaluate(
                '(key) => window.localStorage.setItem(key, "closed")',
                WIKI_SIDEBAR_STATE_KEY,
            )
            await page.reload({'waitUntil': 'networkidle2'})
            await page.waitForFunction("document.querySelectorAll('#wikiToc .wiki-toc-link').length > 0")
            case['sidebar_closed_after_reload'] = await page.evaluate(
                "document.querySelector('#wikiSidebarToggleBtn').getAttribute('aria-expanded') === 'false'"
            )
            self.assertTrue(case['sidebar_closed_after_reload'])
            await page.click('#wikiSidebarToggleBtn')
            await page.waitForFunction("document.querySelector('#wikiSidebarToggleBtn').getAttribute('aria-expanded') === 'true'")
            await page.reload({'waitUntil': 'networkidle2'})
            await page.waitForFunction("document.querySelectorAll('#wikiToc .wiki-toc-link').length > 0")
            case['sidebar_open_after_reload'] = await page.evaluate(
                "document.querySelector('#wikiSidebarToggleBtn').getAttribute('aria-expanded') === 'true'"
            )
            self.assertTrue(case['sidebar_open_after_reload'])
            await page.click('#wikiSearchToggleBtn')
            await page.type('#wikiSearchInput', '없는 검색어')
            await page.keyboard.press('Enter')
            await page.waitForFunction("document.querySelector('#wikiStatus').textContent.includes('일치하는 문서가 없습니다.')")
            case['wiki_status'] = await self.text(page, '#wikiStatus')
            case['wiki_status_role'] = await page.Jeval('#wikiStatus', '(node) => node.getAttribute("role") || ""')
            case['wiki_status_live'] = await page.Jeval('#wikiStatus', '(node) => node.getAttribute("aria-live") || ""')
            case['wiki_status_atomic'] = await page.Jeval('#wikiStatus', '(node) => node.getAttribute("aria-atomic") || ""')
            case['wiki_article_live'] = await page.Jeval('#wikiArticle', '(node) => node.getAttribute("aria-live") || ""')
            self.assertIn('일치하는 문서가 없습니다.', case['wiki_status'])
            self.assertEqual(case['wiki_status_role'], 'status')
            self.assertEqual(case['wiki_status_live'], 'polite')
            self.assertEqual(case['wiki_status_atomic'], 'true')
            self.assertEqual(case['wiki_article_live'], '')
            status = 'passed'
        finally:
            self.record_case(case_id='wiki-sidebar-status', status=status, observations=case)
            await page.close()


if __name__ == '__main__':
    unittest.main()
