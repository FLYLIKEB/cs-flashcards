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

CONTROLS_COLLAPSED_KEY = 'controlsCollapsed'

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

    async def wait_for_embed_frame(self, page, url_part: str = 'question-bank-embed=1'):
        ready_expr = "Boolean(document.getElementById('questionAnswerInput') || document.querySelector('.question-choice') || document.querySelector('.question-prompt'))"
        for _ in range(60):
            for frame in page.frames:
                if url_part not in frame.url:
                    continue
                try:
                    await frame.waitForFunction(ready_expr, {'timeout': 250})
                    return frame
                except Exception:
                    pass
            await asyncio.sleep(0.05)
        self.fail(f'Embed frame containing {url_part!r} did not appear.')

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
                window.__testRouteFetchLog = window.__testRouteFetchLog || {};
                const bucket = Array.isArray(window.__testRouteFetchLog[routePath]) ? window.__testRouteFetchLog[routePath] : [];
                bucket.push({key: parsed.searchParams.get(keyParam) || '', url: parsed.toString(), at: Date.now()});
                window.__testRouteFetchLog[routePath] = bucket;
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

    def test_question_bank_source_keeps_single_launch_and_review_helpers(self) -> None:
        source = (ROOT / 'static' / 'question-bank.js').read_text(encoding='utf-8')
        helper_names = (
            'persistPracticeLaunch',
            'restartPracticeFrame',
            'confirmPracticeRestart',
            'bindQuestionBankReviewActions',
            'reviewFieldHtml',
            'renderQuestionBankReview',
        )
        helper_counts = {
            name: len(re.findall(rf'\bfunction {name}\s*\(', source))
            for name in helper_names
        }
        self.assertEqual(helper_counts, {name: 1 for name in helper_names})

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

    async def test_header_menu_keyboard_focus_and_escape_restore(self):
        case = {'path': '/'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.waitForSelector('#menuBtn')
            case['card_bookmark_before'] = await self.attr(page, '#bookmarkBtn', 'aria-pressed')
            if case['card_bookmark_before'] != 'true':
                await page.click('#bookmarkBtn')
                await page.waitForFunction("document.querySelector('#bookmarkBtn').getAttribute('aria-pressed') === 'true'")
            case['card_bookmark_after'] = await self.attr(page, '#bookmarkBtn', 'aria-pressed')
            self.assertEqual(case['card_bookmark_after'], 'true')

            await page.focus('#menuBtn')
            await page.keyboard.press('Enter')
            await page.waitForFunction("document.querySelector('#menuPopover').hidden === false")
            await page.waitForFunction("document.activeElement && document.activeElement.id === 'wikiHomeLink'")
            case['focus_after_keyboard_open'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['focus_after_keyboard_open'], 'wikiHomeLink')

            for _ in range(7):
                await page.keyboard.press('Tab')
            await page.waitForFunction("document.activeElement && document.activeElement.id === 'bookmarkFilterBtn'")
            case['focus_before_bookmark_filter_activate'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['focus_before_bookmark_filter_activate'], 'bookmarkFilterBtn')

            case['card_totals_before_filter'] = await page.evaluate('() => ({ total: state.cards.length, filtered: state.filtered.length })')
            await page.keyboard.press('Enter')
            await page.waitForFunction("document.querySelector('#menuPopover').hidden === true")
            await page.waitForFunction("document.activeElement && document.activeElement.id === 'menuBtn'")
            await page.waitForFunction("document.querySelector('#bookmarkFilterBtn').getAttribute('aria-pressed') === 'true'")
            case['focus_after_bookmark_filter_activate'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['focus_after_bookmark_filter_activate'], 'menuBtn')
            case['bookmark_filter_state_after_keyboard_activate'] = await page.evaluate(
                """
                () => ({
                  menuHidden: document.querySelector('#menuPopover').hidden,
                  menuExpanded: document.querySelector('#menuBtn')?.getAttribute('aria-expanded') || '',
                  pressed: document.querySelector('#bookmarkFilterBtn')?.getAttribute('aria-pressed') || '',
                  bookmarkFilter: state.bookmarkFilter,
                  filteredCount: state.filtered.length,
                  allFilteredBookmarked: state.filtered.every((card) => isCardBookmarked(card)),
                })
                """
            )
            self.assertTrue(case['bookmark_filter_state_after_keyboard_activate']['menuHidden'])
            self.assertEqual(case['bookmark_filter_state_after_keyboard_activate']['menuExpanded'], 'false')
            self.assertEqual(case['bookmark_filter_state_after_keyboard_activate']['pressed'], 'true')
            self.assertTrue(case['bookmark_filter_state_after_keyboard_activate']['bookmarkFilter'])
            self.assertGreaterEqual(case['bookmark_filter_state_after_keyboard_activate']['filteredCount'], 1)
            self.assertLessEqual(
                case['bookmark_filter_state_after_keyboard_activate']['filteredCount'],
                case['card_totals_before_filter']['total'],
            )
            self.assertTrue(case['bookmark_filter_state_after_keyboard_activate']['allFilteredBookmarked'])

            await page.focus('#menuBtn')
            await page.keyboard.press('Enter')
            await page.waitForFunction("document.querySelector('#menuPopover').hidden === false")
            await page.waitForFunction("document.activeElement && document.activeElement.id === 'wikiHomeLink'")
            await page.keyboard.press('Escape')
            await page.waitForFunction("document.querySelector('#menuPopover').hidden === true")
            case['focus_after_escape'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['focus_after_escape'], 'menuBtn')

            await page.click('#menuBtn')
            await page.click('#memoListBtn')
            await page.waitForFunction("document.querySelector('#memoListDialog').hidden === false")
            case['memo_dialog_opened_via_click'] = await page.evaluate("document.querySelector('#memoListDialog').hidden === false")
            self.assertTrue(case['memo_dialog_opened_via_click'])
            status = 'passed'
        finally:
            self.record_case(case_id='header-menu-keyboard-focus', status=status, observations=case)
            await page.close()

    async def test_controls_panel_collapse_updates_hidden_state_and_tab_order(self):
        case = {'path': '/'}
        page = await self.new_page(
            viewport={'width': 1440, 'height': 1100},
            local_storage={CONTROLS_COLLAPSED_KEY: '1'},
        )
        status = 'failed'
        try:
            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.waitForSelector('#controlsToggle')
            await page.waitForFunction("document.querySelector('#controlsBody').hidden === true")
            case['initial_collapsed'] = await page.evaluate(
                """
                () => ({
                  bodyHidden: document.querySelector('#controlsBody')?.hidden,
                  toggleExpanded: document.querySelector('#controlsToggle')?.getAttribute('aria-expanded') || '',
                  storedValue: window.localStorage.getItem('controlsCollapsed') || '',
                })
                """
            )
            self.assertTrue(case['initial_collapsed']['bodyHidden'])
            self.assertEqual(case['initial_collapsed']['toggleExpanded'], 'false')
            self.assertEqual(case['initial_collapsed']['storedValue'], '1')

            await page.focus('#controlsToggle')
            await page.keyboard.press('Enter')
            await page.waitForFunction("document.querySelector('#controlsBody').hidden === false")
            case['expanded_state'] = await page.evaluate(
                """
                () => ({
                  bodyHidden: document.querySelector('#controlsBody')?.hidden,
                  toggleExpanded: document.querySelector('#controlsToggle')?.getAttribute('aria-expanded') || '',
                  storedValue: window.localStorage.getItem('controlsCollapsed') || '',
                })
                """
            )
            self.assertFalse(case['expanded_state']['bodyHidden'])
            self.assertEqual(case['expanded_state']['toggleExpanded'], 'true')
            self.assertEqual(case['expanded_state']['storedValue'], '0')

            await page.reload({'waitUntil': 'networkidle2'})
            await page.waitForFunction("document.querySelector('#controlsBody').hidden === false")
            case['reloaded_open_state'] = await page.evaluate(
                """
                () => ({
                  bodyHidden: document.querySelector('#controlsBody')?.hidden,
                  toggleExpanded: document.querySelector('#controlsToggle')?.getAttribute('aria-expanded') || '',
                })
                """
            )
            self.assertFalse(case['reloaded_open_state']['bodyHidden'])
            self.assertEqual(case['reloaded_open_state']['toggleExpanded'], 'true')

            await page.focus('#controlsToggle')
            await page.keyboard.press('Tab')
            await page.waitForFunction("document.activeElement && document.activeElement.id === 'speakTerm'")
            case['focus_after_tab_when_open'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['focus_after_tab_when_open'], 'speakTerm')

            await page.focus('#controlsToggle')
            await page.keyboard.press('Enter')
            await page.waitForFunction("document.querySelector('#controlsBody').hidden === true")
            case['recollapsed_state'] = await page.evaluate(
                """
                () => ({
                  bodyHidden: document.querySelector('#controlsBody')?.hidden,
                  toggleExpanded: document.querySelector('#controlsToggle')?.getAttribute('aria-expanded') || '',
                  storedValue: window.localStorage.getItem('controlsCollapsed') || '',
                  focusedId: document.activeElement && document.activeElement.id ? document.activeElement.id : '',
                })
                """
            )
            self.assertTrue(case['recollapsed_state']['bodyHidden'])
            self.assertEqual(case['recollapsed_state']['toggleExpanded'], 'false')
            self.assertEqual(case['recollapsed_state']['storedValue'], '1')
            self.assertEqual(case['recollapsed_state']['focusedId'], 'controlsToggle')

            await page.keyboard.press('Tab')
            await page.waitForFunction("document.activeElement && document.activeElement.id === 'positionInput'")
            case['focus_after_tab_when_collapsed'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertEqual(case['focus_after_tab_when_collapsed'], 'positionInput')
            status = 'passed'
        finally:
            self.record_case(case_id='controls-panel-collapse-hidden', status=status, observations=case)
            await page.close()

    async def test_main_symbolic_buttons_expose_explicit_accessible_names(self):
        case = {'path': '/'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.waitForSelector('#menuBtn')
            case['controls'] = await page.evaluate(
                """
                () => {
                  const specs = [
                    ['filterAllBtn', '전체', '전체', 'Σ'],
                    ['filterKnownBtn', '안다', '안다', 'O'],
                    ['filterUnknownBtn', '모른다', '모른다', 'X'],
                    ['filterUnreviewedBtn', '미학습', '미학습', '–'],
                    ['questionPracticeBtn', '문제 풀이', '문제 풀이', 'Q'],
                    ['menuBtn', '메뉴', '메뉴', '☰'],
                    ['collapsedPlayBtn', '자동 듣기 재생', '재생', '▶'],
                    ['collapsedStopBtn', '자동 듣기 정지', '정지', '■'],
                    ['playAudioBtn', '자동 듣기 재생', '재생', '▶'],
                    ['stopAudioBtn', '자동 듣기 정지', '정지', '■'],
                    ['prevQuestionBtn', '이전 문제', '이전 문제', '←'],
                    ['nextQuestionBtn', '다음 문제', '다음 문제', '→'],
                    ['knownBtn', '안다', '안다', 'O'],
                    ['unknownBtn', '모른다', '모른다', 'X'],
                    ['unreviewedBtn', '미학습으로 되돌리기', '미학습으로 되돌리기', '–'],
                  ];
                  return Object.fromEntries(
                    specs.map(([id, expectedLabel, expectedTitle, expectedText]) => {
                      const node = document.getElementById(id);
                      return [
                        id,
                        {
                          exists: Boolean(node),
                          ariaLabel: node?.getAttribute('aria-label') || '',
                          title: node?.getAttribute('title') || '',
                          text: (node?.textContent || '').replace(/\s+/g, ' ').trim(),
                          expectedLabel,
                          expectedTitle,
                          expectedText,
                        },
                      ];
                    }),
                  );
                }
                """
            )
            for control_id, snapshot in case['controls'].items():
                self.assertTrue(snapshot['exists'], control_id)
                self.assertEqual(snapshot['ariaLabel'], snapshot['expectedLabel'], control_id)
                self.assertEqual(snapshot['title'], snapshot['expectedTitle'], control_id)
                self.assertTrue(snapshot['text'].startswith(snapshot['expectedText']), control_id)
            status = 'passed'
        finally:
            self.record_case(case_id='main-symbolic-button-a11y', status=status, observations=case)
            await page.close()

    async def test_main_filter_and_history_toggles_expose_pressed_state(self):
        case = {'path': '/'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.waitForSelector('#bookmarkFilterBtn')
            case['bookmark_initial'] = await self.attr(page, '#bookmarkFilterBtn', 'aria-pressed')
            self.assertEqual(case['bookmark_initial'], 'false')
            await page.evaluate("document.querySelector('#bookmarkFilterBtn').click()")
            await page.waitForFunction("document.querySelector('#bookmarkFilterBtn').getAttribute('aria-pressed') === 'true'")
            case['bookmark_after_click'] = await self.attr(page, '#bookmarkFilterBtn', 'aria-pressed')
            self.assertEqual(case['bookmark_after_click'], 'true')

            case['status_initial'] = await page.evaluate(
                """
                () => ({
                  all: document.querySelector('#filterAllBtn')?.getAttribute('aria-pressed') || '',
                  known: document.querySelector('#filterKnownBtn')?.getAttribute('aria-pressed') || '',
                  unknown: document.querySelector('#filterUnknownBtn')?.getAttribute('aria-pressed') || '',
                  unreviewed: document.querySelector('#filterUnreviewedBtn')?.getAttribute('aria-pressed') || '',
                })
                """
            )
            self.assertEqual(case['status_initial']['all'], 'true')
            self.assertEqual(case['status_initial']['known'], 'false')
            self.assertEqual(case['status_initial']['unknown'], 'false')
            self.assertEqual(case['status_initial']['unreviewed'], 'false')

            await page.evaluate("document.querySelector('#filterUnknownBtn').click()")
            await page.waitForFunction("document.querySelector('#filterUnknownBtn').getAttribute('aria-pressed') === 'true'")
            case['status_after_unknown'] = await page.evaluate(
                """
                () => ({
                  all: document.querySelector('#filterAllBtn')?.getAttribute('aria-pressed') || '',
                  known: document.querySelector('#filterKnownBtn')?.getAttribute('aria-pressed') || '',
                  unknown: document.querySelector('#filterUnknownBtn')?.getAttribute('aria-pressed') || '',
                  unreviewed: document.querySelector('#filterUnreviewedBtn')?.getAttribute('aria-pressed') || '',
                })
                """
            )
            self.assertEqual(case['status_after_unknown']['all'], 'false')
            self.assertEqual(case['status_after_unknown']['known'], 'false')
            self.assertEqual(case['status_after_unknown']['unknown'], 'true')
            self.assertEqual(case['status_after_unknown']['unreviewed'], 'false')

            await page.evaluate("document.querySelector('#questionHistoryBtn').click()")
            await page.waitForFunction("document.querySelector('#questionHistoryDialog').hidden === false")
            case['history_initial'] = await page.evaluate(
                """
                () => ({
                  all: document.querySelector('[data-question-history-filter="all"]')?.getAttribute('aria-pressed') || '',
                  correct: document.querySelector('[data-question-history-filter="correct"]')?.getAttribute('aria-pressed') || '',
                  wrong: document.querySelector('[data-question-history-filter="wrong"]')?.getAttribute('aria-pressed') || '',
                })
                """
            )
            self.assertEqual(case['history_initial']['all'], 'true')
            self.assertEqual(case['history_initial']['correct'], 'false')
            self.assertEqual(case['history_initial']['wrong'], 'false')

            await page.evaluate("document.querySelector('[data-question-history-filter=\"wrong\"]').click()")
            await page.waitForFunction("document.querySelector('[data-question-history-filter=\"wrong\"]').getAttribute('aria-pressed') === 'true'")
            case['history_after_wrong'] = await page.evaluate(
                """
                () => ({
                  all: document.querySelector('[data-question-history-filter="all"]')?.getAttribute('aria-pressed') || '',
                  correct: document.querySelector('[data-question-history-filter="correct"]')?.getAttribute('aria-pressed') || '',
                  wrong: document.querySelector('[data-question-history-filter="wrong"]')?.getAttribute('aria-pressed') || '',
                })
                """
            )
            self.assertEqual(case['history_after_wrong']['all'], 'false')
            self.assertEqual(case['history_after_wrong']['correct'], 'false')
            self.assertEqual(case['history_after_wrong']['wrong'], 'true')
            status = 'passed'
        finally:
            self.record_case(case_id='main-filter-toggle-pressed-state', status=status, observations=case)
            await page.close()

    async def test_question_history_pending_filter_and_inline_judgment_update(self):
        case = {'path': '/'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        history_items = [
            {
                'question_id': 'history-pending-1',
                'question_bank_id': 'history-qb-1',
                'card_id': 'CS-001',
                'term': '미채점 기록',
                'category': '테스트',
                'question_type': 'subjective',
                'prompt': '미채점 기록 prompt',
                'body': '미채점 기록 body',
                'result_key': 'pending',
                'result_label': '미채점',
                'user_answer': '임시 답안',
                'wrong_note': '',
                'session_title': '문제 기록 세트',
                'session_mode': 'practice',
                'question_order': 1,
                'updated_at': '2026-08-01T00:00:00Z',
            },
            {
                'question_id': 'history-wrong-1',
                'question_bank_id': 'history-qb-2',
                'card_id': 'CS-002',
                'term': '오답 기록',
                'category': '테스트',
                'question_type': 'subjective',
                'prompt': '오답 기록 prompt',
                'body': '오답 기록 body',
                'result_key': 'wrong',
                'result_label': '틀림',
                'user_answer': '오답',
                'wrong_note': '개념 확인',
                'session_title': '문제 기록 세트',
                'session_mode': 'practice',
                'question_order': 2,
                'updated_at': '2026-08-01T00:05:00Z',
            },
        ]
        try:
            await page.evaluateOnNewDocument(
                """
                ({ historyItems }) => {
                  const originalFetch = window.fetch.bind(window);
                  const items = historyItems.map((item) => ({...item}));
                  const summarize = () => ({
                    selected_card_count: 2,
                    total: items.length,
                    correct: items.filter((item) => item.result_key === 'correct').length,
                    ambiguous: items.filter((item) => item.result_key === 'ambiguous').length,
                    wrong: items.filter((item) => item.result_key === 'wrong').length,
                    unknown: items.filter((item) => item.result_key === 'unknown').length,
                    pending: items.filter((item) => item.result_key === 'pending').length,
                    returned: items.length,
                  });
                  window.__historyAttemptCalls = [];
                  window.fetch = (input, init = undefined) => {
                    const url = typeof input === 'string' ? input : input.url;
                    const method = ((init && init.method) || (typeof input !== 'string' && input.method) || 'GET').toUpperCase();
                    const parsed = new URL(url, window.location.origin);
                    if (parsed.pathname === '/api/questions/attempts' && method === 'GET') {
                      const result = (parsed.searchParams.get('result') || 'all').toLowerCase();
                      const filtered = result === 'all' ? items : items.filter((item) => item.result_key === result);
                      return Promise.resolve(new Response(JSON.stringify({
                        items: filtered,
                        summary: {...summarize(), filter: result, returned: filtered.length},
                      }), {
                        status: 200,
                        headers: {'Content-Type': 'application/json'},
                      }));
                    }
                    if (parsed.pathname === '/api/questions/attempt' && method === 'POST') {
                      const payload = JSON.parse((init && init.body) || '{}');
                      window.__historyAttemptCalls.push(payload);
                      const index = items.findIndex((item) => item.question_id === payload.question_id);
                      if (index >= 0) {
                        items[index] = {
                          ...items[index],
                          ...payload,
                          result_key: payload.judgment,
                          result_label: payload.judgment === 'correct' ? '맞음' : payload.judgment === 'ambiguous' ? '애매함' : payload.judgment === 'wrong' ? '틀림' : payload.judgment,
                          wrong_note: payload.judgment === 'correct' ? '' : (items[index].wrong_note || ''),
                          updated_at: '2026-08-01T00:10:00Z',
                          answered_at: payload.answered_at || '2026-08-01T00:10:00Z',
                        };
                      }
                      return Promise.resolve(new Response(JSON.stringify({
                        attempt: {
                          ...payload,
                          result_key: payload.judgment,
                          updated_at: '2026-08-01T00:10:00Z',
                          answered_at: payload.answered_at || '2026-08-01T00:10:00Z',
                        },
                      }), {
                        status: 200,
                        headers: {'Content-Type': 'application/json'},
                      }));
                    }
                    return originalFetch(input, init);
                  };
                }
                """,
                {'historyItems': history_items},
            )
            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.evaluate("document.querySelector('#questionHistoryBtn').click()")
            await page.waitForFunction("document.querySelector('#questionHistoryDialog').hidden === false")

            await page.click('[data-question-history-filter="pending"]')
            await page.waitForFunction(
                """
                () => document.querySelector('[data-question-history-filter="pending"]')?.getAttribute('aria-pressed') === 'true'
                  && document.querySelectorAll('#questionHistoryBody .question-history-item').length === 1
                  && document.querySelector('#questionHistoryBody')?.textContent.includes('미채점 기록 prompt')
                """
            )
            await page.click('[data-question-history-judgment="correct"]')
            await page.waitForFunction("document.querySelector('#questionHistoryBody')?.textContent.includes('선택한 조건에 해당하는 문제 기록이 없습니다.')")
            await page.click('[data-question-history-filter="all"]')
            await page.waitForFunction(
                """
                () => document.querySelector('[data-question-history-filter="all"]')?.getAttribute('aria-pressed') === 'true'
                  && document.querySelector('#questionHistoryBody .question-history-result')?.textContent.includes('맞음')
                """
            )
            case['after_inline_judgment'] = await page.evaluate(
                """
                () => ({
                  chip: document.querySelector('#questionHistoryBody .question-history-result')?.textContent.trim() || '',
                  pendingPressed: document.querySelector('[data-question-history-filter="pending"]')?.getAttribute('aria-pressed') || '',
                  allPressed: document.querySelector('[data-question-history-filter="all"]')?.getAttribute('aria-pressed') || '',
                  calls: window.__historyAttemptCalls || [],
                })
                """
            )
            self.assertEqual(case['after_inline_judgment']['chip'], '맞음')
            self.assertEqual(case['after_inline_judgment']['pendingPressed'], 'false')
            self.assertEqual(case['after_inline_judgment']['allPressed'], 'true')
            self.assertEqual(len(case['after_inline_judgment']['calls']), 1)
            self.assertEqual(case['after_inline_judgment']['calls'][0]['judgment'], 'correct')
            status = 'passed'
        finally:
            self.record_case(case_id='question-history-pending-inline-judgment', status=status, observations=case)
            await page.close()

    async def test_card_state_toggles_expose_pressed_state(self):
        case = {'path': '/'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(self.base_url, waitUntil='networkidle2')
            case['table_render_contract'] = await page.evaluate(
                """
                () => {
                  const render = FLASHCARD_TABLE_COLUMNS?.status?.render;
                  const wrapper = document.createElement('div');
                  wrapper.innerHTML = typeof render === 'function' ? render({id: 'CS-TEST', known_status: 'X'}) : '';
                  const pick = (value) => {
                    const node = wrapper.querySelector(`[data-status-value="${value}"]`);
                    return {
                      pressed: node?.getAttribute('aria-pressed') || '',
                      active: Boolean(node?.classList.contains('active')),
                    };
                  };
                  return {
                    renderExists: typeof render === 'function',
                    known: pick('O'),
                    unknown: pick('X'),
                    unreviewed: pick(''),
                  };
                }
                """
            )
            self.assertTrue(case['table_render_contract']['renderExists'])
            self.assertEqual(case['table_render_contract']['known']['pressed'], 'false')
            self.assertEqual(case['table_render_contract']['unknown']['pressed'], 'true')
            self.assertEqual(case['table_render_contract']['unreviewed']['pressed'], 'false')
            for key in ('known', 'unknown', 'unreviewed'):
                self.assertEqual(case['table_render_contract'][key]['active'], case['table_render_contract'][key]['pressed'] == 'true')

            await page.evaluate(
                """
                () => {
                  const cardId = state.filtered[0]?.id || state.cards[0]?.id || 'CS-001';
                  state.questions = [{
                    card_id: cardId,
                    prompt: '상태 토글 prompt',
                    answer: '상태 토글 answer',
                    type: 'subjective',
                    answerRevealed: false,
                    judgment: 'pending',
                  }];
                  state.questionIndex = 0;
                  toggleQuestionMode(true);
                }
                """
            )
            await page.waitForFunction("document.querySelector('#questionPanel').hidden === false")
            await page.waitForFunction("document.querySelector('[data-question-mark=\"O\"]') && !document.querySelector('[data-question-mark=\"O\"]').disabled")
            case['question_initial'] = await page.evaluate(
                """
                () => {
                  const pick = (value) => {
                    const node = document.querySelector(`[data-question-mark="${value}"]`);
                    return {
                      pressed: node?.getAttribute('aria-pressed') || '',
                      active: Boolean(node?.classList.contains('active')),
                    };
                  };
                  return {known: pick('O'), unknown: pick('X'), unreviewed: pick('')};
                }
                """
            )
            for key in ('known', 'unknown', 'unreviewed'):
                self.assertEqual(case['question_initial'][key]['active'], case['question_initial'][key]['pressed'] == 'true')
            self.assertEqual(sum(case['question_initial'][key]['pressed'] == 'true' for key in ('known', 'unknown', 'unreviewed')), 1)

            await page.evaluate("document.querySelector('[data-question-mark=\"O\"]')?.click()")
            await page.waitForFunction(
                """
                () => document.querySelector('[data-question-mark="O"]')?.getAttribute('aria-pressed') === 'true'
                  && document.querySelector('[data-question-mark="X"]')?.getAttribute('aria-pressed') === 'false'
                  && document.querySelector('[data-question-mark=""]')?.getAttribute('aria-pressed') === 'false'
                """
            )
            case['question_after_known'] = await page.evaluate(
                """
                () => {
                  const pick = (value) => {
                    const node = document.querySelector(`[data-question-mark="${value}"]`);
                    return {
                      pressed: node?.getAttribute('aria-pressed') || '',
                      active: Boolean(node?.classList.contains('active')),
                    };
                  };
                  return {known: pick('O'), unknown: pick('X'), unreviewed: pick('')};
                }
                """
            )
            self.assertEqual(case['question_after_known']['known']['pressed'], 'true')
            self.assertEqual(case['question_after_known']['unknown']['pressed'], 'false')
            self.assertEqual(case['question_after_known']['unreviewed']['pressed'], 'false')
            status = 'passed'
        finally:
            self.record_case(case_id='card-state-toggle-pressed-state', status=status, observations=case)
            await page.close()

    async def test_flashcard_table_popup_stays_mounted_across_rerenders(self):
        case = {'path': '/'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        popup = None
        popup_name = 'csFlashcardTableWindow'
        status = 'failed'
        try:
            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.waitForFunction("document.querySelector('#flashcardTableBtn') && state.filtered.length > 0")
            await page.evaluate(
                """
                () => {
                  window.open = (url, name = '', _features = '') => {
                    const selector = `iframe[data-test-popup-name="${name}"]`;
                    document.querySelector(selector)?.remove();
                    const frame = document.createElement('iframe');
                    frame.dataset.testPopupName = name;
                    frame.setAttribute('aria-hidden', 'true');
                    frame.style.cssText = 'position:fixed;left:-9999px;top:-9999px;width:1280px;height:900px;border:0;';
                    document.body.appendChild(frame);
                    const popupWindow = frame.contentWindow;
                    try {
                      Object.defineProperty(popupWindow, 'opener', {value: window, configurable: true});
                    } catch (_error) {
                      try { popupWindow.opener = window; } catch (__error) {}
                    }
                    frame.src = url;
                    return popupWindow;
                  };
                }
                """
            )
            case['initial_main_state'] = await page.evaluate(
                """
                () => ({
                  filteredCount: state.filtered.length,
                  currentCardId: state.filtered[state.index]?.id || '',
                  currentTerm: state.filtered[state.index]?.term || '',
                  currentStatus: state.filtered[state.index]?.known_status || '',
                })
                """
            )
            self.assertGreater(case['initial_main_state']['filteredCount'], 0)
            self.assertTrue(case['initial_main_state']['currentCardId'])

            await page.click('#menuBtn')
            await page.waitForFunction("document.querySelector('#menuPopover') && document.querySelector('#menuPopover').hidden === false")
            await page.click('#flashcardTableBtn')
            await page.waitForSelector(f'iframe[data-test-popup-name="{popup_name}"]')
            popup_handle = await page.querySelector(f'iframe[data-test-popup-name="{popup_name}"]')
            self.assertIsNotNone(popup_handle)
            popup = await popup_handle.contentFrame()
            self.assertIsNotNone(popup)
            await popup.waitForFunction("document.querySelectorAll('#flashcardTableMount [data-row-card-id]').length > 0")
            case['popup_initial'] = await popup.evaluate(
                """
                () => ({
                  helperReady: typeof window.__csFlashcardTableRender === 'function',
                  summary: document.querySelector('.summary')?.textContent || '',
                  rowCount: document.querySelectorAll('#flashcardTableMount [data-row-card-id]').length,
                  currentRowCardId: document.querySelector('#flashcardTableMount .current-row')?.dataset.rowCardId || '',
                })
                """
            )
            self.assertTrue(case['popup_initial']['helperReady'])
            self.assertEqual(case['popup_initial']['rowCount'], case['initial_main_state']['filteredCount'])
            self.assertEqual(case['popup_initial']['currentRowCardId'], case['initial_main_state']['currentCardId'])

            next_status = 'X' if case['initial_main_state']['currentStatus'] == 'O' else 'O'
            case['status_toggle_target'] = {
                'cardId': case['initial_main_state']['currentCardId'],
                'nextStatus': next_status,
                'openerAvailable': await popup.evaluate(
                    """
                    () => Boolean(window.opener && typeof window.opener.__csFlashcardsSetStatusFromTable === 'function')
                    """
                ),
            }
            self.assertTrue(case['status_toggle_target']['openerAvailable'])
            await popup.evaluate(
                """
                (cardId, nextStatus) => window.opener.__csFlashcardsSetStatusFromTable(cardId, nextStatus)
                """,
                case['initial_main_state']['currentCardId'],
                next_status,
            )
            await page.waitForFunction(
                """
                (cardId, nextStatus) => state.cards.find((item) => item.id === cardId)?.known_status === nextStatus
                """,
                {},
                case['initial_main_state']['currentCardId'],
                next_status,
            )
            await popup.waitForFunction(
                """
                (cardId, nextStatus, expectedCount) => {
                  const rows = document.querySelectorAll('#flashcardTableMount [data-row-card-id]');
                  const pressed = document.querySelector(`[data-row-card-id="${cardId}"] [data-status-value="${nextStatus}"]`);
                  return rows.length === expectedCount
                    && rows.length > 0
                    && !!document.querySelector('#flashcardTableMount .cs-table')
                    && !!pressed
                    && pressed.getAttribute('aria-pressed') === 'true';
                }
                """,
                {},
                case['initial_main_state']['currentCardId'],
                next_status,
                case['initial_main_state']['filteredCount'],
            )
            case['popup_after_status_toggle'] = await popup.evaluate(
                """
                () => ({
                  summary: document.querySelector('.summary')?.textContent || '',
                  rowCount: document.querySelectorAll('#flashcardTableMount [data-row-card-id]').length,
                  currentRowCardId: document.querySelector('#flashcardTableMount .current-row')?.dataset.rowCardId || '',
                  tablePresent: Boolean(document.querySelector('#flashcardTableMount .cs-table')),
                })
                """
            )
            self.assertTrue(case['popup_after_status_toggle']['tablePresent'])
            self.assertEqual(case['popup_after_status_toggle']['rowCount'], case['initial_main_state']['filteredCount'])
            self.assertEqual(case['popup_after_status_toggle']['currentRowCardId'], case['initial_main_state']['currentCardId'])

            await self.set_input_value(page, '#searchInput', case['initial_main_state']['currentTerm'])
            await page.waitForFunction(
                """
                (term) => state.filtered.length > 0
                  && state.filtered.every((card) => String(card.term || '').includes(term))
                """,
                {},
                case['initial_main_state']['currentTerm'],
            )
            case['main_after_filter'] = await page.evaluate(
                """
                () => ({
                  filteredCount: state.filtered.length,
                  currentCardId: state.filtered[state.index]?.id || '',
                })
                """
            )
            await popup.waitForFunction(
                """
                (expectedCount, currentCardId, term) => {
                  const rows = document.querySelectorAll('#flashcardTableMount [data-row-card-id]');
                  const summary = document.querySelector('.summary')?.textContent || '';
                  return rows.length === expectedCount
                    && rows.length > 0
                    && !!document.querySelector('#flashcardTableMount .cs-table')
                    && document.querySelector('#flashcardTableMount .current-row')?.dataset.rowCardId === currentCardId
                    && summary.includes(`검색 ${term}`);
                }
                """,
                {},
                case['main_after_filter']['filteredCount'],
                case['main_after_filter']['currentCardId'],
                case['initial_main_state']['currentTerm'],
            )
            case['popup_after_filter'] = await popup.evaluate(
                """
                () => ({
                  summary: document.querySelector('.summary')?.textContent || '',
                  rowCount: document.querySelectorAll('#flashcardTableMount [data-row-card-id]').length,
                  currentRowCardId: document.querySelector('#flashcardTableMount .current-row')?.dataset.rowCardId || '',
                  tablePresent: Boolean(document.querySelector('#flashcardTableMount .cs-table')),
                })
                """
            )
            self.assertTrue(case['popup_after_filter']['tablePresent'])
            self.assertEqual(case['popup_after_filter']['rowCount'], case['main_after_filter']['filteredCount'])
            self.assertEqual(case['popup_after_filter']['currentRowCardId'], case['main_after_filter']['currentCardId'])
            self.assertIn(f"검색 {case['initial_main_state']['currentTerm']}", case['popup_after_filter']['summary'])
            status = 'passed'
        finally:
            self.record_case(case_id='flashcard-table-popup-rerender-regression', status=status, observations=case)
            await page.evaluate(
                """
                (name) => {
                  document.querySelector(`iframe[data-test-popup-name="${name}"]`)?.remove();
                }
                """,
                popup_name,
            )
            await page.close()

    async def test_filter_inputs_expose_explicit_accessible_names(self):
        case = {'path': '/'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.waitForSelector('#searchInput')
            await page.click('#questionPracticeBtn')
            await page.waitForFunction("document.querySelector('#questionPanel').hidden === false")
            case['controls'] = await page.evaluate(
                """
                () => {
                  const specs = [
                    ['searchInput', '카드 검색', 'aria-label'],
                    ['positionInput', '카드 번호 이동', 'aria-label'],
                    ['categorySelect', '카테고리', 'aria-label'],
                    ['importanceSelect', '중요도', 'aria-label'],
                    ['difficultySelect', '난이도', 'aria-label'],
                    ['bokSelect', '한국은행 기출 여부', 'aria-label'],
                    ['questionBankQueryInput', '문제/정답/키워드 검색', 'aria-label'],
                  ];
                  return Object.fromEntries(
                    specs.map(([id, expectedName, expectedSource]) => {
                      const node = document.getElementById(id);
                      const ariaLabel = node?.getAttribute('aria-label') || '';
                      return [
                        id,
                        {
                          exists: Boolean(node),
                          name: ariaLabel,
                          source: ariaLabel ? 'aria-label' : '',
                          expectedName,
                          expectedSource,
                        },
                      ];
                    }),
                  );
                }
                """
            )
            for control_id, snapshot in case['controls'].items():
                self.assertTrue(snapshot['exists'], control_id)
                self.assertEqual(snapshot['name'], snapshot['expectedName'], control_id)
                self.assertEqual(snapshot['source'], snapshot['expectedSource'], control_id)
            status = 'passed'
        finally:
            self.record_case(case_id='filter-input-accessible-names', status=status, observations=case)
            await page.close()

    async def test_question_bank_launch_path_avoids_duplicate_full_renders(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.evaluateOnNewDocument(
                """
                () => {
                  window.__questionBankRenderTableCalls = 0;
                  window.__questionBankRenderPracticePaneCalls = 0;
                  const wrapRenderFns = () => {
                    const originalRenderTable = window.renderTable;
                    if (typeof originalRenderTable === 'function' && !originalRenderTable.__wrappedQuestionBankCounter) {
                      const wrappedRenderTable = (...args) => {
                        window.__questionBankRenderTableCalls += 1;
                        return originalRenderTable(...args);
                      };
                      wrappedRenderTable.__wrappedQuestionBankCounter = true;
                      window.renderTable = wrappedRenderTable;
                    }
                    const originalRenderPracticePane = window.renderPracticePane;
                    if (typeof originalRenderPracticePane === 'function' && !originalRenderPracticePane.__wrappedQuestionBankCounter) {
                      const wrappedRenderPracticePane = (...args) => {
                        window.__questionBankRenderPracticePaneCalls += 1;
                        return originalRenderPracticePane(...args);
                      };
                      wrappedRenderPracticePane.__wrappedQuestionBankCounter = true;
                      window.renderPracticePane = wrappedRenderPracticePane;
                    }
                  };
                  document.addEventListener('DOMContentLoaded', () => {
                    window.setTimeout(wrapRenderFns, 0);
                  }, {once: true});
                }
                """
            )
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 1")
            await page.waitForFunction("typeof window.renderTable === 'function' && window.renderTable.__wrappedQuestionBankCounter === true")
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 1")
            await page.evaluate('window.__questionBankRenderTableCalls = 0; window.__questionBankRenderPracticePaneCalls = 0;')
            await page.evaluate('document.querySelector("#bankPageLaunchBtn")?.click()')
            await page.waitForFunction("!document.querySelector('#bankPagePracticeFrame').hidden")
            case['initial_launch_counts'] = await page.evaluate(
                """
                () => ({
                  renderTable: window.__questionBankRenderTableCalls,
                  renderPracticePane: window.__questionBankRenderPracticePaneCalls,
                })
                """
            )
            self.assertEqual(case['initial_launch_counts']['renderTable'], 1)
            self.assertEqual(case['initial_launch_counts']['renderPracticePane'], 1)

            await page.evaluate('window.__questionBankRenderTableCalls = 0; window.__questionBankRenderPracticePaneCalls = 0;')
            await page.evaluate('document.querySelector("#bankPageLaunchBtn")?.click()')
            await page.waitForFunction("!document.body.classList.contains('question-bank-practice-collapsed')")
            case['same_target_reveal_counts'] = await page.evaluate(
                """
                () => ({
                  renderTable: window.__questionBankRenderTableCalls,
                  renderPracticePane: window.__questionBankRenderPracticePaneCalls,
                })
                """
            )
            self.assertEqual(case['same_target_reveal_counts']['renderTable'], 0)
            self.assertEqual(case['same_target_reveal_counts']['renderPracticePane'], 0)

            await page.evaluate('window.__questionBankRenderTableCalls = 0; window.__questionBankRenderPracticePaneCalls = 0;')
            await page.evaluate('document.querySelector("#bankPageList tbody tr:nth-child(2) .question-bank-row-trigger").click()')
            await page.waitForFunction(
                '(counts) => window.__questionBankRenderTableCalls >= counts.table && window.__questionBankRenderPracticePaneCalls >= counts.pane',
                {},
                {'table': 1, 'pane': 1},
            )
            case['row_change_counts'] = await page.evaluate(
                """
                () => ({
                  renderTable: window.__questionBankRenderTableCalls,
                  renderPracticePane: window.__questionBankRenderPracticePaneCalls,
                })
                """
            )
            self.assertEqual(case['row_change_counts']['renderTable'], 1)
            self.assertEqual(case['row_change_counts']['renderPracticePane'], 1)
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-launch-render-dedupe', status=status, observations=case)
            await page.close()
    async def test_question_bank_page_loads_filters_and_launches_embedded_practice(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            case['initial_summary'] = await self.text(page, '#bankPageSummary')
            self.assertIn('총', case['initial_summary'])

            case['filter_region_initial'] = await page.evaluate(
                """
                () => ({
                  bodyCollapsed: document.body.classList.contains('question-bank-filters-collapsed'),
                  regionHidden: document.querySelector('#bankPageFiltersRegion')?.hidden,
                  toggleExpanded: document.querySelector('#bankPageToggleFiltersBtn')?.getAttribute('aria-expanded'),
                  toggleControls: document.querySelector('#bankPageToggleFiltersBtn')?.getAttribute('aria-controls'),
                })
                """
            )
            self.assertTrue(case['filter_region_initial']['bodyCollapsed'])
            self.assertTrue(case['filter_region_initial']['regionHidden'])
            self.assertEqual(case['filter_region_initial']['toggleExpanded'], 'false')
            self.assertEqual(case['filter_region_initial']['toggleControls'], 'bankPageFiltersRegion')
            await page.click('#bankPageToggleFiltersBtn')
            await page.waitForFunction("!document.body.classList.contains('question-bank-filters-collapsed') && !document.querySelector('#bankPageFiltersRegion').hidden")
            await page.type('#bankPageQueryInput', '데이터베이스')
            await page.waitForFunction("window.location.search.includes('q=%EB%8D%B0%EC%9D%B4%ED%84%B0%EB%B2%A0%EC%9D%B4%EC%8A%A4')")
            await page.waitForFunction("document.querySelector('#bankPageActiveFilters').textContent.includes('통합 검색')")
            case['active_filters'] = await self.text(page, '#bankPageActiveFilters')
            await page.click('#bankPageToggleFiltersBtn')
            await page.waitForFunction("document.body.classList.contains('question-bank-filters-collapsed') && document.querySelector('#bankPageFiltersRegion').hidden")
            case['filter_region_after_recollapse'] = await page.evaluate(
                """
                () => ({
                  regionHidden: document.querySelector('#bankPageFiltersRegion')?.hidden,
                  toggleExpanded: document.querySelector('#bankPageToggleFiltersBtn')?.getAttribute('aria-expanded'),
                })
                """
            )
            case['active_filters_after_recollapse'] = await self.text(page, '#bankPageActiveFilters')
            self.assertTrue(case['filter_region_after_recollapse']['regionHidden'])
            self.assertEqual(case['filter_region_after_recollapse']['toggleExpanded'], 'false')
            self.assertIn('통합 검색', case['active_filters_after_recollapse'])
            await page.click('#bankPageToggleFiltersBtn')
            await page.waitForFunction("!document.body.classList.contains('question-bank-filters-collapsed') && !document.querySelector('#bankPageFiltersRegion').hidden")
            case['practice_toggle_before_launch'] = await page.evaluate(
                """
                () => ({
                  pressed: document.querySelector('#bankPageTogglePracticeBtn')?.getAttribute('aria-pressed') || '',
                  disabled: Boolean(document.querySelector('#bankPageTogglePracticeBtn')?.disabled),
                })
                """
            )
            self.assertEqual(case['practice_toggle_before_launch']['pressed'], 'false')
            self.assertTrue(case['practice_toggle_before_launch']['disabled'])
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
            case['practice_toggle_after_launch'] = await page.evaluate(
                """
                () => ({
                  pressed: document.querySelector('#bankPageTogglePracticeBtn')?.getAttribute('aria-pressed') || '',
                  disabled: Boolean(document.querySelector('#bankPageTogglePracticeBtn')?.disabled),
                })
                """
            )
            self.assertEqual(case['practice_toggle_after_launch']['pressed'], 'true')
            self.assertFalse(case['practice_toggle_after_launch']['disabled'])
            case['practice_status'] = await self.text(page, '#bankPagePracticeStatus')
            self.assertIn('현재 1 /', case['practice_status'])
            await page.evaluate('document.querySelector("#bankPageRefreshBtn").click()')
            await page.waitForFunction("document.querySelector('#bankPageSummary').textContent.includes('총')")
            case['practice_frame_src_after_refresh'] = await page.Jeval('#bankPagePracticeFrame', '(node) => node.getAttribute("src") || ""')
            self.assertEqual(case['practice_frame_src_after_refresh'], case['practice_frame_src'])
            case['practice_status_after_refresh'] = await self.text(page, '#bankPagePracticeStatus')
            case['practice_toggle_after_refresh'] = await page.evaluate(
                """
                () => ({
                  pressed: document.querySelector('#bankPageTogglePracticeBtn')?.getAttribute('aria-pressed') || '',
                  disabled: Boolean(document.querySelector('#bankPageTogglePracticeBtn')?.disabled),
                })
                """
            )
            self.assertEqual(case['practice_toggle_after_refresh']['pressed'], 'true')
            self.assertFalse(case['practice_toggle_after_refresh']['disabled'])
            self.assertIn('현재 1 /', case['practice_status_after_refresh'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-load-launch', status=status, observations=case)
            await page.close()
    async def test_question_bank_responsive_layout_at_tablet_and_mobile_widths(self):
        case = {'path': '/question-bank', 'viewports': [900, 390]}
        page = await self.new_page(viewport={'width': 900, 'height': 1000})
        status = 'failed'
        try:
            for width, height in ((900, 1000), (390, 844)):
                await page.setViewport({'width': width, 'height': height})
                await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
                await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
                metrics = await page.evaluate(
                    """
                    () => {
                      const tops = (selector) => [...document.querySelectorAll(selector)]
                        .map((node) => Math.round(node.getBoundingClientRect().top))
                        .filter((top, index, values) => values.indexOf(top) === index);
                      const nodes = [
                        document.querySelector('.question-bank-shell-topbar-inner'),
                        document.querySelector('.cs-table-shell.question-bank-shell'),
                      ].filter(Boolean);
                      const rightmost = nodes.length
                        ? Math.max(...nodes.map((node) => node.getBoundingClientRect().right))
                        : 0;
                      return {
                        viewportWidth: document.documentElement.clientWidth,
                        documentScrollWidth: document.documentElement.scrollWidth,
                        shellRight: Math.round(rightmost),
                        primaryRows: tops('.question-bank-primary-actions .cs-table-button').length,
                        selectionRows: tops('.question-bank-selection-actions .cs-table-button').length,
                      };
                    }
                    """
                )
                case[str(width)] = metrics
                self.assertLessEqual(metrics['documentScrollWidth'], metrics['viewportWidth'] + 1)
                self.assertLessEqual(metrics['shellRight'], metrics['viewportWidth'] + 1)
                self.assertEqual(metrics['primaryRows'], 2 if width == 900 else 1)
                self.assertEqual(metrics['selectionRows'], 1 if width == 900 else 2)
                if width == 390:
                    await page.click('#bankPageCategoryGuideBtn')
                    await page.waitForFunction("!document.querySelector('#bankPageCategoryGuideDialog').hidden")
                    dialog_metrics = await page.evaluate(
                        """
                        () => {
                          const card = document.querySelector('.question-bank-dialog-card')?.getBoundingClientRect();
                          const close = document.querySelector('#bankPageCategoryGuideCloseBtn')?.getBoundingClientRect();
                          return {
                            cardWidth: Math.round(card?.width || 0),
                            closeWidth: Math.round(close?.width || 0),
                            viewportWidth: document.documentElement.clientWidth,
                          };
                        }
                        """
                    )
                    case['390_dialog'] = dialog_metrics
                    self.assertLessEqual(dialog_metrics['cardWidth'], dialog_metrics['viewportWidth'])
                    self.assertGreater(dialog_metrics['closeWidth'], 0)
                    await page.click('#bankPageCategoryGuideCloseBtn')
                    await page.waitForFunction("document.querySelector('#bankPageCategoryGuideDialog').hidden")

            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.evaluate('document.querySelector("#bankPageLaunchBtn")?.click()')
            await page.waitForFunction("!document.querySelector('#bankPagePracticeFrame').hidden")
            case['mobile_practice_scroll_y'] = await page.evaluate('window.scrollY')
            self.assertLessEqual(case['mobile_practice_scroll_y'], 1)
            await page.click('#bankPagePracticeExitBtn')
            await page.waitForFunction("document.body.classList.contains('question-bank-practice-collapsed')")
            case['mobile_selection_top'] = await page.Jeval(
                '.question-bank-table-selection',
                '(node) => node.getBoundingClientRect().top',
            )
            self.assertGreaterEqual(case['mobile_selection_top'], -20)
            self.assertLessEqual(case['mobile_selection_top'], 80)
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-responsive-layout', status=status, observations=case)
            await page.close()
    async def test_question_bank_embed_question_info_keywords_open_related_card(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            card_info = await page.evaluate(
                """
                async () => {
                  const res = await fetch('/api/cards', {cache: 'no-store'});
                  const data = await res.json();
                  const first = Array.isArray(data.cards)
                    ? data.cards.find((item) => item && String(item.id || '').trim() && String(item.term || '').trim())
                    : null;
                  return first ? {id: String(first.id || ''), term: String(first.term || '')} : null;
                }
                """
            )
            self.assertIsNotNone(card_info)
            await self.install_delayed_json_route(
                page,
                route_path='/api/question-bank',
                key_param='q',
                responses={
                    'keyword-nav': {
                        'delayMs': 0,
                        'payload': self.question_bank_payload(
                            'keyword-nav',
                            items=[
                                self.question_bank_item(
                                    'keyword-nav',
                                    card_id=card_info['id'],
                                    keywords=[card_info['term']],
                                    prompt='키워드 이동 prompt',
                                )
                            ],
                        ),
                    },
                },
            )
            await page.click('#bankPageToggleFiltersBtn')
            await page.waitForFunction("!document.querySelector('#bankPageFiltersRegion').hidden")
            await self.set_input_value(page, '#bankPageQueryInput', 'keyword-nav', submit=True)
            await page.waitForFunction("document.querySelector('#bankPageList').textContent.includes('키워드 이동 prompt')")
            await page.click('#bankPageLaunchBtn')
            await page.waitForFunction("!document.querySelector('#bankPagePracticeFrame').hidden")
            frame = await self.wait_for_embed_frame(page)
            await frame.waitForFunction("document.querySelector('.question-info-box .question-keyword-link') !== null")
            case['question_info_text'] = await frame.Jeval('.question-info-box', '(node) => (node.textContent || "").trim()')
            case['keyword_button_card_id'] = await frame.Jeval('.question-info-box .question-keyword-link', '(node) => node.getAttribute("data-question-card-id") || ""')
            self.assertIn('문항 정보', case['question_info_text'])
            self.assertIn(card_info['term'], case['question_info_text'])
            self.assertEqual(case['keyword_button_card_id'], card_info['id'])
            await frame.click('.question-info-box .question-keyword-link')
            await frame.waitForFunction(
                """
                (term) => !document.body.classList.contains('question-mode-active')
                  && ((document.querySelector('#backTerm')?.textContent || '').trim() === term)
                """,
                {},
                card_info['term'],
            )
            case['back_term_after_click'] = await frame.Jeval('#backTerm', '(node) => (node.textContent || "").trim()')
            self.assertEqual(case['back_term_after_click'], card_info['term'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-keyword-card-nav', status=status, observations=case)
            await page.close()
    async def test_question_bank_page_mobile_layout_stacks_actions_without_overflow(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 900, 'height': 1180})
        status = 'failed'
        try:
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await page.click('#bankPageToggleFiltersBtn')
            await page.waitForFunction("!document.querySelector('#bankPageFiltersRegion').hidden")
            case['initial_layout'] = await page.evaluate(
                """
                () => {
                  const viewportWidth = window.innerWidth;
                  const rect = (selector) => {
                    const node = document.querySelector(selector);
                    if (!node) return null;
                    const box = node.getBoundingClientRect();
                    return {left: box.left, right: box.right, width: box.width};
                  };
                  const fits = (selector) => [...document.querySelectorAll(selector)].every((node) => {
                    const box = node.getBoundingClientRect();
                    return box.left >= -1 && box.right <= viewportWidth + 1;
                  });
                  return {
                    pageOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                    primaryActionsDisplay: getComputedStyle(document.querySelector('.question-bank-primary-actions')).display,
                    filterActionsDisplay: getComputedStyle(document.querySelector('.question-bank-filter-actions')).display,
                    headerChipsDisplay: getComputedStyle(document.querySelector('#bankPageHeaderChips')).display,
                    filterGridColumns: getComputedStyle(document.querySelector('.cs-table-filter-grid')).gridTemplateColumns.split(' ').length,
                    primaryButtonsFit: fits('.question-bank-primary-actions .cs-table-button'),
                    filterButtonsFit: fits('.question-bank-filter-actions .cs-table-button'),
                    headerChipsFit: fits('#bankPageHeaderChips > *'),
                    shellRect: rect('.cs-table-shell.question-bank-shell'),
                    topbarRect: rect('.question-bank-shell-topbar-inner'),
                  };
                }
                """
            )
            self.assertLessEqual(case['initial_layout']['pageOverflow'], 2)
            self.assertEqual(case['initial_layout']['primaryActionsDisplay'], 'grid')
            self.assertEqual(case['initial_layout']['filterActionsDisplay'], 'grid')
            self.assertEqual(case['initial_layout']['headerChipsDisplay'], 'grid')
            self.assertEqual(case['initial_layout']['filterGridColumns'], 2)
            self.assertTrue(case['initial_layout']['primaryButtonsFit'])
            self.assertTrue(case['initial_layout']['filterButtonsFit'])
            self.assertTrue(case['initial_layout']['headerChipsFit'])
            self.assertLessEqual(case['initial_layout']['shellRect']['right'], 901)
            self.assertLessEqual(case['initial_layout']['topbarRect']['right'], 901)

            await page.click('#bankPageCategoryGuideBtn')
            await page.waitForFunction("document.querySelector('#bankPageCategoryGuideDialog') && !document.querySelector('#bankPageCategoryGuideDialog').hidden")
            case['dialog_layout'] = await page.evaluate(
                """
                () => {
                  const viewportWidth = window.innerWidth;
                  const card = document.querySelector('.question-bank-dialog-card');
                  const box = card.getBoundingClientRect();
                  return {
                    width: box.width,
                    right: box.right,
                    viewportWidth,
                  };
                }
                """
            )
            self.assertLessEqual(case['dialog_layout']['right'], case['dialog_layout']['viewportWidth'] + 1)
            await page.click('#bankPageCategoryGuideCloseBtn')
            await page.waitForFunction("document.querySelector('#bankPageCategoryGuideDialog').hidden")

            await page.click('#bankPageLaunchBtn')
            await page.waitForFunction("document.body.classList.contains('question-bank-practice-focus') && !document.querySelector('#bankPagePracticeFrame').hidden")
            case['practice_layout'] = await page.evaluate(
                """
                () => {
                  const viewportWidth = window.innerWidth;
                  const frame = document.querySelector('#bankPagePracticeFrame');
                  const exitButton = document.querySelector('#bankPagePracticeExitBtn');
                  const frameBox = frame.getBoundingClientRect();
                  const exitBox = exitButton.getBoundingClientRect();
                  return {
                    pageOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                    frameRight: frameBox.right,
                    frameWidth: frameBox.width,
                    exitRight: exitBox.right,
                    exitTop: exitBox.top,
                    viewportWidth,
                  };
                }
                """
            )
            self.assertLessEqual(case['practice_layout']['pageOverflow'], 2)
            self.assertLessEqual(case['practice_layout']['frameRight'], case['practice_layout']['viewportWidth'] + 1)
            self.assertLessEqual(case['practice_layout']['exitRight'], case['practice_layout']['viewportWidth'] + 1)
            self.assertGreater(case['practice_layout']['frameWidth'], 0)
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-mobile-layout', status=status, observations=case)
            await page.close()

    async def test_question_bank_mobile_overview_keeps_two_column_metrics(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 390, 'height': 844})
        status = 'failed'
        try:
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageOverviewCards > *').length === 4")
            case['overview_layout'] = await page.evaluate(
                """
() => {
  const grid = document.querySelector('#bankPageOverviewCards');
  const hero = document.querySelector('.question-bank-hero-card');
  const reviewCard = document.querySelector('.question-bank-review-card');
  const cards = [...document.querySelectorAll('#bankPageOverviewCards > *')];
  const buttons = [...document.querySelectorAll('.question-bank-primary-actions .cs-table-button')];
  const rowCount = (nodes) => new Set(nodes.map((node) => Math.round(node.getBoundingClientRect().top))).size;
  const firstTop = cards[0]?.getBoundingClientRect().top || 0;
  const secondTop = cards[1]?.getBoundingClientRect().top || 0;
  const heroHeight = hero?.getBoundingClientRect().height || 0;
  const gridHeight = grid?.getBoundingClientRect().height || 0;
  const reviewTop = reviewCard?.getBoundingClientRect().top || 0;
  return {
    metricCount: cards.length,
    buttonCount: buttons.length,
    columnCount: getComputedStyle(grid).gridTemplateColumns.split(' ').length,
    metricRows: rowCount(cards),
    actionRows: rowCount(buttons),
    firstRowSharesTop: Math.abs(firstTop - secondTop) < 2,
    heroViewportShare: Number((heroHeight / window.innerHeight).toFixed(3)),
    gridViewportShare: Number((gridHeight / window.innerHeight).toFixed(3)),
    reviewTopShare: Number((reviewTop / window.innerHeight).toFixed(3)),
    pageOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  };
}
"""
            )
            self.assertEqual(case['overview_layout']['metricCount'], 4)
            self.assertEqual(case['overview_layout']['buttonCount'], 3)
            self.assertEqual(case['overview_layout']['columnCount'], 2)
            self.assertEqual(case['overview_layout']['metricRows'], 2)
            self.assertTrue(case['overview_layout']['firstRowSharesTop'])
            self.assertEqual(case['overview_layout']['actionRows'], 1)
            self.assertLess(case['overview_layout']['heroViewportShare'], 0.27)
            self.assertLess(case['overview_layout']['gridViewportShare'], 0.13)
            self.assertLess(case['overview_layout']['reviewTopShare'], 0.34)
            self.assertLessEqual(case['overview_layout']['pageOverflow'], 2)
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-mobile-overview-compact', status=status, observations=case)
            await page.close()



    async def test_question_bank_review_filter_buttons_expose_pressed_state(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        review_payload = {
            'items': [
                {
                    'question_bank_id': 'review-wrong-1',
                    'prompt': '틀린 문항 prompt',
                    'term': '틀린 문항',
                    'category': '테스트',
                    'question_type': 'subjective',
                    'session_title': '복습 세트',
                    'updated_at': '2026-08-01T00:00:00Z',
                    'result_key': 'wrong',
                    'result_label': '틀림',
                    'user_answer': '오답',
                    'wrong_note': '개념 연결을 다시 볼 것',
                    'answer': '정답 해설',
                },
                {
                    'question_bank_id': 'review-correct-1',
                    'prompt': '맞은 문항 prompt',
                    'term': '맞은 문항',
                    'category': '테스트',
                    'question_type': 'subjective',
                    'session_title': '복습 세트',
                    'updated_at': '2026-08-01T00:05:00Z',
                    'result_key': 'correct',
                    'result_label': '맞음',
                    'user_answer': '정답',
                    'wrong_note': '',
                    'answer': '정답 해설',
                },
                {
                    'question_bank_id': 'review-pending-1',
                    'prompt': '미채점 문항 prompt',
                    'term': '미채점 문항',
                    'category': '테스트',
                    'question_type': 'subjective',
                    'session_title': '복습 세트',
                    'updated_at': '2026-08-01T00:10:00Z',
                    'result_key': 'pending',
                    'result_label': '미채점',
                    'user_answer': '보류 답안',
                    'wrong_note': '',
                    'answer': '미채점 정답 해설',
                },
            ],
            'summary': {
                'total': 3,
                'correct': 1,
                'ambiguous': 0,
                'wrong': 1,
                'unknown': 0,
                'pending': 1,
                'note_count': 1,
                'selected_question_bank_count': 3,
            },
        }
        try:
            await page.evaluateOnNewDocument(
                """
                (reviewPayload) => {
                  const originalFetch = window.fetch.bind(window);
                  window.fetch = (input, init = undefined) => {
                    const url = typeof input === 'string' ? input : input.url;
                    const method = ((init && init.method) || (typeof input !== 'string' && input.method) || 'GET').toUpperCase();
                    const parsed = new URL(url, window.location.origin);
                    if (parsed.pathname === '/api/question-bank/attempts/query' && method === 'POST') {
                      return Promise.resolve(new Response(JSON.stringify(reviewPayload), {
                        status: 200,
                        headers: {'Content-Type': 'application/json'},
                      }));
                    }
                    return originalFetch(input, init);
                  };
                }
                """,
                review_payload,
            )
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await page.click('#bankPageToggleReviewBtn')
            await page.waitForFunction(
                """
                () => {
                  const body = document.getElementById('bankPageReviewBody');
                  const filters = document.querySelectorAll('#bankPageReviewFilters [data-review-filter]');
                  const items = document.querySelectorAll('#bankPageReviewList .question-bank-review-item');
                  return body && body.hidden === false && filters.length === 4 && items.length === 3;
                }
                """
            )
            case['initial_filters'] = await page.evaluate(
                """
                () => Object.fromEntries(
                  [...document.querySelectorAll('#bankPageReviewFilters [data-review-filter]')].map((button) => [
                    button.dataset.reviewFilter,
                    {
                      pressed: button.getAttribute('aria-pressed') || '',
                      active: button.classList.contains('is-active'),
                    },
                  ])
                )
                """
            )
            self.assertEqual(case['initial_filters']['attempted']['pressed'], 'true')
            self.assertTrue(case['initial_filters']['attempted']['active'])
            self.assertEqual(case['initial_filters']['pending']['pressed'], 'false')
            self.assertEqual(case['initial_filters']['wrong']['pressed'], 'false')
            self.assertEqual(case['initial_filters']['note']['pressed'], 'false')

            await page.click('#bankPageReviewFilters [data-review-filter="pending"]')
            await page.waitForFunction(
                """
                () => document.querySelector('#bankPageReviewFilters [data-review-filter="pending"]')?.getAttribute('aria-pressed') === 'true'
                  && document.querySelectorAll('#bankPageReviewList .question-bank-review-item').length === 1
                  && document.querySelector('#bankPageReviewList')?.textContent.includes('미채점 문항 prompt')
                """
            )
            case['pending_filter'] = await page.evaluate(
                """
                () => ({
                  attempted: document.querySelector('#bankPageReviewFilters [data-review-filter="attempted"]')?.getAttribute('aria-pressed') || '',
                  pending: document.querySelector('#bankPageReviewFilters [data-review-filter="pending"]')?.getAttribute('aria-pressed') || '',
                  wrong: document.querySelector('#bankPageReviewFilters [data-review-filter="wrong"]')?.getAttribute('aria-pressed') || '',
                  note: document.querySelector('#bankPageReviewFilters [data-review-filter="note"]')?.getAttribute('aria-pressed') || '',
                  visibleCount: document.querySelectorAll('#bankPageReviewList .question-bank-review-item').length,
                })
                """
            )
            self.assertEqual(case['pending_filter']['attempted'], 'false')
            self.assertEqual(case['pending_filter']['pending'], 'true')
            self.assertEqual(case['pending_filter']['wrong'], 'false')
            self.assertEqual(case['pending_filter']['note'], 'false')
            self.assertEqual(case['pending_filter']['visibleCount'], 1)

            await page.click('#bankPageReviewFilters [data-review-filter="wrong"]')
            await page.waitForFunction(
                """
                () => document.querySelector('#bankPageReviewFilters [data-review-filter="wrong"]')?.getAttribute('aria-pressed') === 'true'
                  && document.querySelectorAll('#bankPageReviewList .question-bank-review-item').length === 1
                  && document.querySelector('#bankPageReviewList')?.textContent.includes('틀린 문항 prompt')
                """
            )
            case['wrong_filter'] = await page.evaluate(
                """
                () => ({
                  attempted: document.querySelector('#bankPageReviewFilters [data-review-filter="attempted"]')?.getAttribute('aria-pressed') || '',
                  pending: document.querySelector('#bankPageReviewFilters [data-review-filter="pending"]')?.getAttribute('aria-pressed') || '',
                  wrong: document.querySelector('#bankPageReviewFilters [data-review-filter="wrong"]')?.getAttribute('aria-pressed') || '',
                  note: document.querySelector('#bankPageReviewFilters [data-review-filter="note"]')?.getAttribute('aria-pressed') || '',
                  visibleCount: document.querySelectorAll('#bankPageReviewList .question-bank-review-item').length,
                })
                """
            )
            self.assertEqual(case['wrong_filter']['attempted'], 'false')
            self.assertEqual(case['wrong_filter']['pending'], 'false')
            self.assertEqual(case['wrong_filter']['wrong'], 'true')
            self.assertEqual(case['wrong_filter']['note'], 'false')
            self.assertEqual(case['wrong_filter']['visibleCount'], 1)

            await page.click('#bankPageReviewFilters [data-review-filter="note"]')
            await page.waitForFunction(
                """
                () => document.querySelector('#bankPageReviewFilters [data-review-filter="note"]')?.getAttribute('aria-pressed') === 'true'
                  && document.querySelectorAll('#bankPageReviewList .question-bank-review-item').length === 1
                  && document.querySelector('#bankPageReviewList')?.textContent.includes('틀린 문항 prompt')
                """
            )
            case['note_filter'] = await page.evaluate(
                """
                () => ({
                  attempted: document.querySelector('#bankPageReviewFilters [data-review-filter="attempted"]')?.getAttribute('aria-pressed') || '',
                  pending: document.querySelector('#bankPageReviewFilters [data-review-filter="pending"]')?.getAttribute('aria-pressed') || '',
                  wrong: document.querySelector('#bankPageReviewFilters [data-review-filter="wrong"]')?.getAttribute('aria-pressed') || '',
                  note: document.querySelector('#bankPageReviewFilters [data-review-filter="note"]')?.getAttribute('aria-pressed') || '',
                  visibleCount: document.querySelectorAll('#bankPageReviewList .question-bank-review-item').length,
                })
                """
            )
            self.assertEqual(case['note_filter']['attempted'], 'false')
            self.assertEqual(case['note_filter']['pending'], 'false')
            self.assertEqual(case['note_filter']['wrong'], 'false')
            self.assertEqual(case['note_filter']['note'], 'true')
            self.assertEqual(case['note_filter']['visibleCount'], 1)
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-review-filter-pressed-state', status=status, observations=case)
            await page.close()

    async def test_question_bank_review_inline_judgment_updates_pending_record(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        bank_item = self.question_bank_item(
            '인라인 채점',
            question_bank_id='review-inline-1',
            prompt='인라인 채점 prompt',
            answer='인라인 정답 해설',
            question_type='subjective',
        )
        question_bank_payload = self.question_bank_payload('review-inline', items=[bank_item])
        review_payload = {
            'items': [
                {
                    'question_id': 'review-inline-attempt-1',
                    'question_bank_id': 'review-inline-1',
                    'prompt': '인라인 채점 prompt',
                    'term': '인라인 채점',
                    'category': '테스트',
                    'question_type': 'subjective',
                    'card_id': 'review-inline-card-1',
                    'session_id': 'review-inline-session',
                    'session_title': '인라인 복습 세트',
                    'session_mode': 'practice',
                    'updated_at': '2026-08-01T00:00:00Z',
                    'result_key': 'pending',
                    'result_label': '미채점',
                    'user_answer': '임시 답안',
                    'wrong_note': '',
                    'answer': '인라인 정답 해설',
                    'question_order': 1,
                },
            ],
            'summary': {
                'total': 1,
                'correct': 0,
                'ambiguous': 0,
                'wrong': 0,
                'unknown': 0,
                'pending': 1,
                'note_count': 0,
                'selected_question_bank_count': 1,
            },
        }
        try:
            await page.evaluateOnNewDocument(
                """
                ({ questionBankPayload, reviewPayload }) => {
                  const originalFetch = window.fetch.bind(window);
                  window.__reviewAttemptCalls = [];
                  window.fetch = (input, init = undefined) => {
                    const url = typeof input === 'string' ? input : input.url;
                    const method = ((init && init.method) || (typeof input !== 'string' && input.method) || 'GET').toUpperCase();
                    const parsed = new URL(url, window.location.origin);
                    if (parsed.pathname === '/api/question-bank' && method === 'GET') {
                      return Promise.resolve(new Response(JSON.stringify(questionBankPayload), {
                        status: 200,
                        headers: {'Content-Type': 'application/json'},
                      }));
                    }
                    if (parsed.pathname === '/api/question-bank/attempts/query' && method === 'POST') {
                      return Promise.resolve(new Response(JSON.stringify(reviewPayload), {
                        status: 200,
                        headers: {'Content-Type': 'application/json'},
                      }));
                    }
                    if (parsed.pathname === '/api/questions/attempt' && method === 'POST') {
                      const payload = JSON.parse((init && init.body) || '{}');
                      window.__reviewAttemptCalls.push(payload);
                      reviewPayload.items = reviewPayload.items.map((item) => item.question_bank_id === payload.question_bank_id
                        ? {
                            ...item,
                            result_key: payload.judgment,
                            result_label: payload.judgment === 'correct' ? '맞음' : payload.judgment,
                            updated_at: '2026-08-01T00:10:00Z',
                            answered_at: payload.answered_at || '2026-08-01T00:10:00Z',
                            wrong_note: payload.judgment === 'correct' ? '' : (item.wrong_note || ''),
                          }
                        : item);
                      reviewPayload.summary = {
                        total: 1,
                        correct: payload.judgment === 'correct' ? 1 : 0,
                        ambiguous: payload.judgment === 'ambiguous' ? 1 : 0,
                        wrong: payload.judgment === 'wrong' ? 1 : 0,
                        unknown: payload.judgment === 'unknown' ? 1 : 0,
                        pending: payload.judgment === 'pending' ? 1 : 0,
                        note_count: 0,
                        selected_question_bank_count: 1,
                      };
                      return Promise.resolve(new Response(JSON.stringify({
                        attempt: {
                          ...payload,
                          updated_at: '2026-08-01T00:10:00Z',
                          answered_at: payload.answered_at || '2026-08-01T00:10:00Z',
                        },
                        card: {id: payload.card_id || 'review-inline-card-1'},
                      }), {
                        status: 200,
                        headers: {'Content-Type': 'application/json'},
                      }));
                    }
                    return originalFetch(input, init);
                  };
                }
                """,
                {'questionBankPayload': question_bank_payload, 'reviewPayload': review_payload},
            )
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length === 1")
            await page.click('#bankPageToggleReviewBtn')
            await page.waitForFunction(
                """
                () => document.querySelectorAll('#bankPageReviewList .question-bank-review-item').length === 1
                  && document.querySelector('#bankPageReviewList')?.textContent.includes('임시 답안')
                """
            )
            await page.click('#bankPageReviewFilters [data-review-filter="pending"]')
            await page.waitForFunction(
                """
                () => document.querySelector('#bankPageReviewFilters [data-review-filter="pending"]')?.getAttribute('aria-pressed') === 'true'
                  && document.querySelectorAll('#bankPageReviewList .question-bank-review-item').length === 1
                """
            )
            await page.click('[data-question-bank-review-judgment="correct"]')
            await page.waitForFunction(
                """
                () => document.querySelector('#bankPageReviewList')?.textContent.includes('선택한 필터에 해당하는 풀이 기록이 없습니다.')
                """
            )
            await page.click('#bankPageReviewFilters [data-review-filter="attempted"]')
            await page.waitForFunction(
                """
                () => document.querySelector('#bankPageReviewFilters [data-review-filter="attempted"]')?.getAttribute('aria-pressed') === 'true'
                  && document.querySelector('#bankPageReviewList .question-bank-review-result')?.textContent.includes('맞음')
                """
            )
            case['after_inline_save'] = await page.evaluate(
                """
                () => ({
                  chip: document.querySelector('#bankPageReviewList .question-bank-review-result')?.textContent.trim() || '',
                  pressed: document.querySelector('#bankPageReviewList [data-question-bank-review-judgment="correct"]')?.getAttribute('aria-pressed') || '',
                  attemptCalls: window.__reviewAttemptCalls || [],
                })
                """
            )
            self.assertEqual(case['after_inline_save']['chip'], '맞음')
            self.assertEqual(case['after_inline_save']['pressed'], 'true')
            self.assertEqual(len(case['after_inline_save']['attemptCalls']), 1)
            self.assertEqual(case['after_inline_save']['attemptCalls'][0]['judgment'], 'correct')
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-review-inline-judgment', status=status, observations=case)
            await page.close()


    async def test_question_bank_row_trigger_supports_tab_enter_and_space_activation(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 1")
            case['row_ids'] = await page.evaluate(
                """
                () => ({
                  first: document.querySelector('#bankPageList tbody tr:nth-child(1)')?.getAttribute('data-table-row-id') || '',
                  second: document.querySelector('#bankPageList tbody tr:nth-child(2)')?.getAttribute('data-table-row-id') || '',
                })
                """
            )

            await page.focus('#bankPageTogglePracticeBtn')
            case['focus_trace'] = []
            trigger_reached = False
            for _ in range(12):
                await page.keyboard.press('Tab')
                snapshot = await page.evaluate(
                    """
                    () => ({
                      tagName: document.activeElement?.tagName || '',
                      className: document.activeElement?.className || '',
                      rowIndex: document.activeElement?.getAttribute?.('data-question-bank-row-index') || '',
                    })
                    """
                )
                case['focus_trace'].append(snapshot)
                if 'question-bank-row-trigger' in str(snapshot.get('className') or '').split():
                    case['first_trigger_semantics'] = snapshot
                    trigger_reached = True
                    break
            self.assertTrue(trigger_reached)
            self.assertEqual(case['first_trigger_semantics']['tagName'], 'BUTTON')
            self.assertEqual(case['first_trigger_semantics']['rowIndex'], '0')

            await page.keyboard.press('Enter')
            await page.waitForFunction(
                """
                (expectedId) => {
                  const frame = document.querySelector('#bankPagePracticeFrame');
                  const activeRow = document.querySelector('#bankPageList [aria-current="true"]');
                  const summary = document.querySelector('#bankPageSelectionSummary');
                  const status = document.querySelector('#bankPagePracticeStatus');
                  return activeRow
                    && activeRow.getAttribute('data-table-row-id') === expectedId
                    && summary
                    && summary.textContent.includes('선택 1 /')
                    && status
                    && status.textContent.includes('현재 1 /')
                    && frame
                    && !frame.hidden;
                }
                """,
                {},
                case['row_ids']['first'],
            )
            case['enter_activation'] = await page.evaluate(
                """
                () => ({
                  activeRowId: document.querySelector('#bankPageList [aria-current="true"]')?.getAttribute('data-table-row-id') || '',
                  selectionSummary: document.querySelector('#bankPageSelectionSummary')?.textContent || '',
                  practiceStatus: document.querySelector('#bankPagePracticeStatus')?.textContent || '',
                  frameSrc: document.querySelector('#bankPagePracticeFrame')?.getAttribute('src') || '',
                })
                """
            )
            self.assertEqual(case['enter_activation']['activeRowId'], case['row_ids']['first'])
            self.assertIn('선택 1 /', case['enter_activation']['selectionSummary'])
            self.assertIn('현재 1 /', case['enter_activation']['practiceStatus'])
            self.assertIn('question-bank-embed=1', case['enter_activation']['frameSrc'])

            await page.click('#bankPagePracticeExitBtn')
            await page.waitForFunction("document.body.classList.contains('question-bank-practice-collapsed')")

            await page.focus('#bankPageList tbody tr:nth-child(2) .question-bank-row-trigger')
            case['focus_before_space'] = await page.evaluate(
                """
                () => ({
                  tagName: document.activeElement?.tagName || '',
                  rowIndex: document.activeElement?.getAttribute?.('data-question-bank-row-index') || '',
                })
                """
            )
            self.assertEqual(case['focus_before_space']['tagName'], 'BUTTON')
            self.assertEqual(case['focus_before_space']['rowIndex'], '1')

            await page.keyboard.press(' ')
            await page.waitForFunction(
                """
                (expectedId) => {
                  const frame = document.querySelector('#bankPagePracticeFrame');
                  const activeRow = document.querySelector('#bankPageList [aria-current="true"]');
                  const summary = document.querySelector('#bankPageSelectionSummary');
                  const status = document.querySelector('#bankPagePracticeStatus');
                  return activeRow
                    && activeRow.getAttribute('data-table-row-id') === expectedId
                    && summary
                    && summary.textContent.includes('선택 2 /')
                    && status
                    && status.textContent.includes('현재 2 /')
                    && frame
                    && !frame.hidden;
                }
                """,
                {},
                case['row_ids']['second'],
            )
            case['space_activation'] = await page.evaluate(
                """
                () => ({
                  activeRowId: document.querySelector('#bankPageList [aria-current="true"]')?.getAttribute('data-table-row-id') || '',
                  selectionSummary: document.querySelector('#bankPageSelectionSummary')?.textContent || '',
                  practiceStatus: document.querySelector('#bankPagePracticeStatus')?.textContent || '',
                  frameSrc: document.querySelector('#bankPagePracticeFrame')?.getAttribute('src') || '',
                })
                """
            )
            self.assertEqual(case['space_activation']['activeRowId'], case['row_ids']['second'])
            self.assertIn('선택 2 /', case['space_activation']['selectionSummary'])
            self.assertIn('현재 2 /', case['space_activation']['practiceStatus'])
            self.assertIn('question-bank-embed=1', case['space_activation']['frameSrc'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-row-trigger-keyboard', status=status, observations=case)
            await page.close()

    async def test_question_bank_filter_refresh_keeps_hidden_practice_inert_until_explicit_launch(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        hidden_item = self.question_bank_item(
            '숨긴 풀이',
            question_bank_id='hidden-practice-item',
            prompt='숨긴 풀이 prompt',
            keywords=['초기목록'],
        )
        visible_item = self.question_bank_item(
            '필터 잔류',
            question_bank_id='filtered-visible-item',
            prompt='필터 잔류 prompt',
            keywords=['hide-filter-reset'],
        )
        initial_payload = self.question_bank_payload('hidden-practice', items=[hidden_item, visible_item])
        filtered_payload = self.question_bank_payload('filtered-visible', items=[visible_item])
        try:
            await page.evaluateOnNewDocument(
                """
                ({ initialPayload, filteredPayload, filterValue }) => {
                  window.__confirmCalls = [];
                  window.confirm = (message) => {
                    window.__confirmCalls.push({message, allow: false});
                    return false;
                  };
                  const originalFetch = window.fetch.bind(window);
                  window.fetch = (input, init = undefined) => {
                    const url = typeof input === 'string' ? input : input.url;
                    const parsed = new URL(url, window.location.origin);
                    if (parsed.pathname !== '/api/question-bank') return originalFetch(input, init);
                    const payload = parsed.searchParams.get('q') === filterValue ? filteredPayload : initialPayload;
                    return Promise.resolve(new Response(JSON.stringify(payload), {
                      status: 200,
                      headers: {'Content-Type': 'application/json'},
                    }));
                  };
                }
                """,
                {'initialPayload': initial_payload, 'filteredPayload': filtered_payload, 'filterValue': 'hide-filter-reset'},
            )
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length === 2")
            await page.click('#bankPageLaunchBtn')
            await page.waitForFunction("!document.querySelector('#bankPagePracticeFrame').hidden")
            case['initial_frame_src'] = await page.Jeval('#bankPagePracticeFrame', '(node) => node.getAttribute("src") || ""')
            embed_frame = await self.wait_for_embed_frame(page)
            case['practice_prompt_before_filter'] = await embed_frame.Jeval('.question-prompt', '(node) => (node.textContent || "").trim()')
            self.assertEqual(case['practice_prompt_before_filter'], hidden_item['prompt'])
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
            case['practice_toggle_after_collapse'] = await page.evaluate(
                """
                () => ({
                  pressed: document.querySelector('#bankPageTogglePracticeBtn')?.getAttribute('aria-pressed') || '',
                  disabled: Boolean(document.querySelector('#bankPageTogglePracticeBtn')?.disabled),
                })
                """
            )
            self.assertEqual(case['practice_toggle_after_collapse']['pressed'], 'false')
            self.assertFalse(case['practice_toggle_after_collapse']['disabled'])

            await page.click('#bankPageToggleFiltersBtn')
            await page.waitForFunction("!document.body.classList.contains('question-bank-filters-collapsed')")
            await self.set_input_value(page, '#bankPageQueryInput', 'hide-filter-reset')
            await page.waitForFunction("window.location.search.includes('q=hide-filter-reset')")
            await page.waitForFunction(
                """
                (expectedId, expectedPrompt) => {
                  const rows = document.querySelectorAll('#bankPageList [data-table-row-id]');
                  const activeRow = document.querySelector('#bankPageList [aria-current="true"]');
                  const selectionTitle = document.querySelector('#bankPageSelectionSummary .question-bank-selection-title');
                  const practiceSummary = document.querySelector('#bankPagePracticeSummary');
                  const practicePlaceholder = document.querySelector('#bankPagePracticePlaceholder');
                  const frame = document.querySelector('#bankPagePracticeFrame');
                  const toggle = document.querySelector('#bankPageTogglePracticeBtn');
                  return rows.length === 1
                    && activeRow
                    && activeRow.getAttribute('data-table-row-id') === expectedId
                    && selectionTitle
                    && selectionTitle.textContent.includes(expectedPrompt)
                    && practiceSummary
                    && practiceSummary.textContent.includes('새 풀이를 시작하세요')
                    && practicePlaceholder
                    && practicePlaceholder.textContent.includes('현재 선택 문항으로 새 풀이를 시작하세요')
                    && frame
                    && frame.hidden === true
                    && toggle
                    && toggle.disabled === true;
                }
                """,
                {},
                visible_item['question_bank_id'],
                visible_item['prompt'],
            )
            case['confirm_calls_after_filter'] = await page.evaluate('window.__confirmCalls.length')
            case['state_after_filter'] = await page.evaluate(
                """
                () => ({
                  activeRowId: document.querySelector('#bankPageList [aria-current="true"]')?.getAttribute('data-table-row-id') || '',
                  selectionSummary: (document.querySelector('#bankPageSelectionSummary')?.textContent || '').replace(/\s+/g, ' ').trim(),
                  practiceSummary: (document.querySelector('#bankPagePracticeSummary')?.textContent || '').trim(),
                  practiceStatus: (document.querySelector('#bankPagePracticeStatus')?.textContent || '').replace(/\s+/g, ' ').trim(),
                  practicePlaceholder: (document.querySelector('#bankPagePracticePlaceholder')?.textContent || '').trim(),
                  frameSrc: document.querySelector('#bankPagePracticeFrame')?.getAttribute('src') || '',
                  frameHidden: Boolean(document.querySelector('#bankPagePracticeFrame')?.hidden),
                  practiceCollapsed: document.body.classList.contains('question-bank-practice-collapsed'),
                  practiceToggleDisabled: Boolean(document.querySelector('#bankPageTogglePracticeBtn')?.disabled),
                  errorText: (document.querySelector('#bankPageError')?.textContent || '').trim(),
                })
                """
            )
            self.assertEqual(case['confirm_calls_after_filter'], 0)
            self.assertEqual(case['state_after_filter']['activeRowId'], visible_item['question_bank_id'])
            self.assertIn(visible_item['prompt'], case['state_after_filter']['selectionSummary'])
            self.assertIn('새 풀이를 시작하세요', case['state_after_filter']['practiceSummary'])
            self.assertIn('선택 1 / 1', case['state_after_filter']['practiceStatus'])
            self.assertIn('현재 선택 문항으로 새 풀이를 시작하세요', case['state_after_filter']['practicePlaceholder'])
            self.assertIn('현재 선택 문항으로 새 풀이를 시작하세요', case['state_after_filter']['errorText'])
            self.assertEqual(case['state_after_filter']['frameSrc'], case['initial_frame_src'])
            self.assertTrue(case['state_after_filter']['frameHidden'])
            self.assertTrue(case['state_after_filter']['practiceCollapsed'])
            self.assertTrue(case['state_after_filter']['practiceToggleDisabled'])

            await page.click('#bankPageLaunchSelectedBtn')
            await page.waitForFunction(
                '(initialSrc) => !document.querySelector("#bankPagePracticeFrame").hidden && (document.querySelector("#bankPagePracticeFrame")?.getAttribute("src") || "") !== initialSrc',
                {},
                case['initial_frame_src'],
            )
            reopened_embed_frame = await self.wait_for_embed_frame(page)
            case['practice_prompt_after_restart'] = await reopened_embed_frame.Jeval('.question-prompt', '(node) => (node.textContent || "").trim()')
            case['practice_status_after_restart'] = await self.text(page, '#bankPagePracticeStatus')
            case['confirm_calls_after_restart'] = await page.evaluate('window.__confirmCalls.length')
            self.assertEqual(case['practice_prompt_after_restart'], visible_item['prompt'])
            self.assertIn('현재 1 / 1', case['practice_status_after_restart'])
            self.assertEqual(case['confirm_calls_after_restart'], 0)
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

    async def test_question_bank_saved_answer_skips_restart_confirm(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        items = [
            self.question_bank_item('저장 첫 문항', question_bank_id='saved-answer-1'),
            self.question_bank_item('저장 둘째 문항', question_bank_id='saved-answer-2'),
        ]
        payload = self.question_bank_payload('saved-answer', items=items)
        try:
            await page.evaluateOnNewDocument(
                """
                (questionBankPayload) => {
                  const root = window.top || window;
                  root.__confirmCalls = root.__confirmCalls || [];
                  root.__savedQuestionAttempts = root.__savedQuestionAttempts || [];
                  const originalFetch = window.fetch.bind(window);
                  window.confirm = (message) => {
                    root.__confirmCalls.push(message);
                    return false;
                  };
                  window.fetch = (input, init = undefined) => {
                    const url = typeof input === 'string' ? input : input.url;
                    const method = ((init && init.method) || (typeof input !== 'string' && input.method) || 'GET').toUpperCase();
                    const parsed = new URL(url, window.location.origin);
                    if (parsed.pathname === '/api/question-bank' && method === 'GET') {
                      return Promise.resolve(new Response(JSON.stringify(questionBankPayload), {
                        status: 200,
                        headers: {'Content-Type': 'application/json'},
                      }));
                    }
                    if (parsed.pathname === '/api/questions/attempt' && method === 'POST') {
                      const payload = JSON.parse((init && init.body) || '{}');
                      root.__savedQuestionAttempts.push(payload);
                      return Promise.resolve(new Response(JSON.stringify({
                        attempt: {
                          ...payload,
                          updated_at: '2026-08-01T00:10:00Z',
                          answered_at: payload.answered_at || '2026-08-01T00:10:00Z',
                          answer_revealed: Boolean(payload.answer_revealed),
                        },
                        card: {id: payload.card_id || 'saved-answer-card'},
                      }), {
                        status: 200,
                        headers: {'Content-Type': 'application/json'},
                      }));
                    }
                    return originalFetch(input, init);
                  };
                }
                """,
                payload,
            )
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 1")
            await page.click('#bankPageLaunchBtn')
            await page.waitForFunction("!document.querySelector('#bankPagePracticeFrame').hidden")
            case['initial_frame_src'] = await page.Jeval('#bankPagePracticeFrame', '(node) => node.getAttribute("src") || ""')

            embed_frame = await self.wait_for_embed_frame(page)
            await embed_frame.waitForSelector('#questionAnswerInput')
            await embed_frame.type('#questionAnswerInput', '저장된 초안 답안')
            await embed_frame.waitForFunction("document.querySelector('.question-card-shell')?.dataset.questionDirty === '1'")
            await embed_frame.click('#questionAnswerSaveBtn')
            await page.waitForFunction('window.__savedQuestionAttempts.length === 1')
            await embed_frame.waitForFunction(
                "document.querySelector('.question-card-shell')?.dataset.questionDirty === '0' && (document.querySelector('#questionAnswerSaveStatus')?.textContent || '').includes('저장됨')"
            )
            case['save_status'] = await embed_frame.Jeval('#questionAnswerSaveStatus', '(node) => (node.textContent || "").trim()')
            case['saved_attempt_payload'] = await page.evaluate('window.__savedQuestionAttempts[0]')
            await embed_frame.click('#revealAnswerBtn')
            await embed_frame.waitForFunction(
                "document.querySelector('.question-answer') && document.querySelector('.question-answer').textContent.includes('저장 첫 문항 answer')"
            )
            case['revealed_answer'] = await embed_frame.Jeval('.question-answer', '(node) => (node.textContent || "").trim()')
            self.assertIn('저장 첫 문항 answer', case['revealed_answer'])
            case['pane_names'] = await embed_frame.Jeval('.question-card-grid', '(node) => [...node.querySelectorAll(\':scope > .question-pane\')].map((pane) => pane.dataset.questionPane)')
            case['pane_resizers'] = await embed_frame.Jeval('.question-card-grid', '(node) => node.querySelectorAll("[data-question-pane-resize]").length')
            case['pane_tops'] = await embed_frame.Jeval('.question-card-grid', '(node) => [...node.querySelectorAll(\':scope > .question-pane\')].map((pane) => Math.round(pane.getBoundingClientRect().top))')
            self.assertEqual(len(set(case['pane_tops'])), 1)
            case['pane_overflow'] = await embed_frame.Jeval('.question-card-grid', '(node) => [...node.querySelectorAll(\':scope > .question-pane\')].map((pane) => getComputedStyle(pane).overflowY)')
            self.assertEqual(case['pane_overflow'], ['auto', 'auto', 'auto'])
            case['scroll_positions'] = await embed_frame.evaluate(
                """
                () => {
                  const panes = [...document.querySelectorAll('.question-card-grid > .question-pane')];
                  panes.forEach((pane) => {
                    const filler = document.createElement('div');
                    filler.style.height = '2000px';
                    filler.setAttribute('aria-hidden', 'true');
                    pane.appendChild(filler);
                    pane.scrollTop = 80;
                  });
                  return panes.map((pane) => pane.scrollTop);
                }
                """
            )
            self.assertTrue(all(position > 0 for position in case['scroll_positions']))
            self.assertEqual(case['pane_names'], ['problem', 'draft', 'answer'])
            self.assertEqual(case['pane_resizers'], 2)
            await embed_frame.click('[data-question-answer-pane-toggle="1"]')
            await embed_frame.waitForFunction("document.querySelectorAll('.question-card-grid > .question-pane').length === 2")
            self.assertEqual(await embed_frame.Jeval('[data-question-answer-pane-toggle="1"]', '(node) => (node.textContent || "").trim()'), '정답 섹터 보기')
            await embed_frame.click('[data-question-answer-pane-toggle="1"]')
            await embed_frame.waitForFunction("document.querySelectorAll('.question-card-grid > .question-pane').length === 3")

            await embed_frame.evaluate("currentQuestion().savedAnswerRevealed = true; refreshCurrentQuestionSaveState(currentQuestion())")
            await page.evaluate('document.querySelector("#bankPageList tbody tr:nth-child(2) .question-bank-row-trigger").click()')
            await page.waitForFunction(
                '(initialSrc) => (document.querySelector("#bankPagePracticeFrame")?.getAttribute("src") || "") !== initialSrc',
                {},
                case['initial_frame_src'],
            )
            case['confirm_calls'] = await page.evaluate('window.__confirmCalls.length')
            case['frame_src_after_row_change'] = await page.Jeval('#bankPagePracticeFrame', '(node) => node.getAttribute("src") || ""')
            self.assertEqual(case['confirm_calls'], 0)
            self.assertNotEqual(case['frame_src_after_row_change'], case['initial_frame_src'])
            self.assertEqual(case['saved_attempt_payload']['judgment'], 'pending')
            self.assertFalse(case['saved_attempt_payload']['answer_revealed'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-saved-answer-skip-confirm', status=status, observations=case)
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
            embed_frame = await self.wait_for_embed_frame(page)
            await embed_frame.waitForSelector('[data-choice-index="0"]')

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
            case['grade_state_on_finished_question'] = await embed_frame.evaluate(
                """
                () => ({
                  choices: [...document.querySelectorAll('[data-choice-index]')].map((node) => ({
                    text: (node.textContent || '').trim(),
                    pressed: node.getAttribute('aria-pressed') || '',
                    className: node.className,
                  })),
                  grades: Object.fromEntries(
                    [...document.querySelectorAll('[data-question-judgment]')].map((node) => [
                      node.getAttribute('data-question-judgment') || '',
                      {
                        pressed: node.getAttribute('aria-pressed') || '',
                        className: node.className,
                      },
                    ])
                  ),
                })
                """
            )
            self.assertEqual(case['grade_state_on_finished_question']['choices'][0]['pressed'], 'true')
            self.assertEqual(case['grade_state_on_finished_question']['choices'][1]['pressed'], 'false')
            self.assertEqual(case['grade_state_on_finished_question']['grades']['correct']['pressed'], 'true')
            self.assertEqual(case['grade_state_on_finished_question']['grades']['wrong']['pressed'], 'false')
            self.assertIn('active', case['grade_state_on_finished_question']['grades']['correct']['className'])

            await embed_frame.evaluate("moveQuestion(-1)")
            await embed_frame.waitForFunction("document.querySelector('.question-prompt') && document.querySelector('.question-prompt').textContent.includes('첫 오답 prompt')")
            case['choice_classes'] = await embed_frame.evaluate(
                "() => [...document.querySelectorAll('[data-choice-index]')].map((node) => ({text: (node.textContent || '').trim(), className: node.className}))"
            )
            self.assertIn('wrong', case['choice_classes'][0]['className'])
            self.assertIn('selected', case['choice_classes'][0]['className'])
            self.assertIn('answer', case['choice_classes'][1]['className'])
            case['grade_state_on_wrong_question'] = await embed_frame.evaluate(
                """
                () => ({
                  choices: [...document.querySelectorAll('[data-choice-index]')].map((node) => ({
                    text: (node.textContent || '').trim(),
                    pressed: node.getAttribute('aria-pressed') || '',
                    className: node.className,
                  })),
                  grades: Object.fromEntries(
                    [...document.querySelectorAll('[data-question-judgment]')].map((node) => [
                      node.getAttribute('data-question-judgment') || '',
                      {
                        pressed: node.getAttribute('aria-pressed') || '',
                        className: node.className,
                      },
                    ])
                  ),
                })
                """
            )
            self.assertEqual(case['grade_state_on_wrong_question']['choices'][0]['pressed'], 'true')
            self.assertEqual(case['grade_state_on_wrong_question']['choices'][1]['pressed'], 'false')
            self.assertEqual(case['grade_state_on_wrong_question']['grades']['wrong']['pressed'], 'true')
            self.assertEqual(case['grade_state_on_wrong_question']['grades']['correct']['pressed'], 'false')
            self.assertIn('active', case['grade_state_on_wrong_question']['grades']['wrong']['className'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-finish-grading-ui', status=status, observations=case)
            await page.close()

    async def test_question_bank_filter_reload_clears_stale_finished_summary(self):
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
        filtered_item = self.question_bank_item(
            '필터 후 새 문제',
            question_type='multiple_choice',
            choices=['정답', '오답'],
            answer='정답',
            answer_index=0,
            points=50,
        )
        payload = self.question_bank_payload('finish-grading-filter-clear', items=[wrong_item, correct_item])
        filtered_payload = self.question_bank_payload('finish-grading-filtered', items=[filtered_item])
        try:
            await page.evaluateOnNewDocument(
                """
                (payload, filteredPayload) => {
                  const originalFetch = window.fetch.bind(window);
                  window.fetch = (input, init = undefined) => {
                    const url = typeof input === 'string' ? input : input.url;
                    const parsed = new URL(url, window.location.origin);
                    if (parsed.pathname !== '/api/question-bank') return originalFetch(input, init);
                    const nextPayload = parsed.searchParams.get('q') === '필터테스트' ? filteredPayload : payload;
                    return Promise.resolve(new Response(JSON.stringify(nextPayload), {
                      status: 200,
                      headers: {'Content-Type': 'application/json'},
                    }));
                  };
                }
                """,
                payload,
                filtered_payload,
            )
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList tbody tr').length === 2")
            await page.click('#bankPageLaunchBtn')
            await page.waitForFunction("!document.querySelector('#bankPagePracticeFrame').hidden")
            embed_frame = await self.wait_for_embed_frame(page)
            await embed_frame.waitForSelector('[data-choice-index="0"]')

            await embed_frame.click('[data-choice-index="0"]')
            await embed_frame.click('[data-question-nav="next"]')
            await embed_frame.waitForFunction("document.querySelector('.question-prompt') && document.querySelector('.question-prompt').textContent.includes('둘째 정답 prompt')")
            await embed_frame.click('[data-choice-index="0"]')
            await embed_frame.evaluate("document.getElementById('finishQuestionSessionBtn').click()")

            await page.waitForFunction("document.querySelector('#bankPagePracticeStatus').textContent.includes('점수 50 / 100점')")
            await page.evaluate("document.getElementById('bankPageToggleFiltersBtn')?.click()")
            await page.waitForFunction("!document.body.classList.contains('question-bank-filters-collapsed')")
            await page.evaluate(
                """
                () => {
                  const input = document.getElementById('bankPageQueryInput');
                  input.value = '필터테스트';
                  input.dispatchEvent(new Event('input', {bubbles: true}));
                }
                """
            )
            await page.waitForFunction("document.querySelector('#bankPageActiveFilters').textContent.includes('필터테스트')")
            await page.waitForFunction("document.querySelectorAll('#bankPageList tbody tr').length === 1")
            await page.waitForFunction("!document.querySelector('#bankPagePracticeStatus').textContent.includes('50 / 100점')")

            case['header_summary_after_filter'] = await self.text(page, '#bankPageHeaderSummary')
            case['practice_status_after_filter'] = await self.text(page, '#bankPagePracticeStatus')
            case['overview_cards_after_filter'] = await page.evaluate(
                "() => [...document.querySelectorAll('#bankPageOverviewCards .question-bank-metric-card')].map((node) => (node.textContent || '').replace(/\\s+/g, ' ').trim())"
            )
            self.assertNotIn('채점 완료', case['header_summary_after_filter'])
            self.assertNotIn('50 / 100점', case['practice_status_after_filter'])
            self.assertTrue(all('50 / 100점' not in card for card in case['overview_cards_after_filter']))
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-finish-summary-clears-on-filter-change', status=status, observations=case)
            await page.close()

    async def test_question_bank_page_preserves_hash_and_query_filters_across_reload_until_reset(self):
        case = {'path': '/question-bank#review-anchor'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(f"{self.base_url}{case['path']}", waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            case['hash_after_initial_render'] = await page.evaluate('window.location.hash')
            self.assertEqual(case['hash_after_initial_render'], '#review-anchor')
            await page.click('#bankPageToggleFiltersBtn')
            await page.waitForFunction("!document.body.classList.contains('question-bank-filters-collapsed')")
            await page.type('#bankPageQueryInput', '데이터베이스')
            await page.select('#bankPageDifficultySelect', '중')
            await page.waitForFunction(
                "window.location.search.includes('q=%EB%8D%B0%EC%9D%B4%ED%84%B0%EB%B2%A0%EC%9D%B4%EC%8A%A4') && window.location.search.includes('difficulty=%EC%A4%91')"
            )
            await page.waitForFunction(
                "document.querySelector('#bankPageActiveFilters').textContent.includes('데이터베이스') && document.querySelector('#bankPageActiveFilters').textContent.includes('중')"
            )
            case['hash_after_filter_change'] = await page.evaluate('window.location.hash')
            self.assertEqual(case['hash_after_filter_change'], '#review-anchor')
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
                """
                () => ({
                  bodyCollapsed: document.body.classList.contains('question-bank-filters-collapsed'),
                  regionHidden: document.querySelector('#bankPageFiltersRegion')?.hidden,
                  toggleExpanded: document.querySelector('#bankPageToggleFiltersBtn')?.getAttribute('aria-expanded'),
                })
                """
            )
            case['hash_after_reload'] = await page.evaluate('window.location.hash')
            case['query_after_reload'] = await page.Jeval('#bankPageQueryInput', '(node) => node.value')
            case['difficulty_after_reload'] = await page.Jeval('#bankPageDifficultySelect', '(node) => node.value')
            self.assertFalse(case['filters_expanded_after_reload']['bodyCollapsed'])
            self.assertFalse(case['filters_expanded_after_reload']['regionHidden'])
            self.assertEqual(case['filters_expanded_after_reload']['toggleExpanded'], 'true')
            self.assertEqual(case['hash_after_reload'], '#review-anchor')
            self.assertEqual(case['query_after_reload'], '데이터베이스')
            self.assertEqual(case['difficulty_after_reload'], '중')

            await page.click('#bankPageActiveFilters [data-filter-key="q"]')
            await page.waitForFunction(
                "document.querySelector('#bankPageQueryInput').value === '' && document.querySelector('#bankPageDifficultySelect').value === '중' && !document.querySelector('#bankPageActiveFilters').textContent.includes('데이터베이스')"
            )
            case['hash_after_chip_clear'] = await page.evaluate('window.location.hash')
            self.assertEqual(case['hash_after_chip_clear'], '#review-anchor')
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
            case['hash_after_chip_clear_reload'] = await page.evaluate('window.location.hash')
            case['query_after_chip_clear_reload'] = await page.Jeval('#bankPageQueryInput', '(node) => node.value')
            case['difficulty_after_chip_clear_reload'] = await page.Jeval('#bankPageDifficultySelect', '(node) => node.value')
            case['active_filters_after_chip_clear_reload'] = await self.text(page, '#bankPageActiveFilters')
            self.assertEqual(case['hash_after_chip_clear_reload'], '#review-anchor')
            self.assertEqual(case['query_after_chip_clear_reload'], '')
            self.assertEqual(case['difficulty_after_chip_clear_reload'], '중')
            self.assertNotIn('데이터베이스', case['active_filters_after_chip_clear_reload'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-hash-and-filter-reload', status=status, observations=case)
            await page.close()

    async def test_question_bank_page_preserves_dynamic_select_filter_on_deep_link_and_reload(self):
        case = {'path': '/question-bank?field_name=전산학술'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        payload = self.question_bank_payload(
            'dynamic-field',
            items=[self.question_bank_item('전산학술 문항', field_name='전산학술', category='데이터베이스', issuer='한국은행')],
        )
        payload['summary']['available_field_names'] = ['전산학술', '테스트분야']
        payload['summary']['available_categories'] = ['데이터베이스']
        payload['summary']['available_issuers'] = ['한국은행']
        try:
            await page.evaluateOnNewDocument(
                """
                (responsePayload) => {
                  window.__questionBankRequestQueries = [];
                  const originalFetch = window.fetch.bind(window);
                  window.fetch = (input, init = undefined) => {
                    const url = typeof input === 'string' ? input : input.url;
                    const parsed = new URL(url, window.location.origin);
                    if (parsed.pathname !== '/api/question-bank') return originalFetch(input, init);
                    window.__questionBankRequestQueries.push({
                      field_name: parsed.searchParams.get('field_name') || '',
                      category: parsed.searchParams.get('category') || '',
                      issuer: parsed.searchParams.get('issuer') || '',
                      limit: parsed.searchParams.get('limit') || '',
                    });
                    return Promise.resolve(new Response(JSON.stringify(responsePayload), {
                      status: 200,
                      headers: {'Content-Type': 'application/json'},
                    }));
                  };
                }
                """,
                payload,
            )
            await page.goto(f'{self.base_url}/question-bank?field_name=%EC%A0%84%EC%82%B0%ED%95%99%EC%88%A0', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await page.waitForFunction("document.querySelector('#bankPageFieldInput').value === '전산학술'")
            case['initial_request'] = await page.evaluate('window.__questionBankRequestQueries[0]')
            case['initial_state'] = await page.evaluate(
                """
                () => ({
                  fieldName: document.querySelector('#bankPageFieldInput')?.value || '',
                  activeFilters: document.querySelector('#bankPageActiveFilters')?.textContent || '',
                  search: window.location.search,
                })
                """
            )
            self.assertEqual(case['initial_request']['field_name'], '전산학술')
            self.assertEqual(case['initial_state']['fieldName'], '전산학술')
            self.assertIn('전산학술', case['initial_state']['activeFilters'])
            self.assertIn('field_name=%EC%A0%84%EC%82%B0%ED%95%99%EC%88%A0', case['initial_state']['search'])

            await page.reload({'waitUntil': 'networkidle2'})
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await page.waitForFunction("document.querySelector('#bankPageFieldInput').value === '전산학술'")
            case['reload_request'] = await page.evaluate('window.__questionBankRequestQueries[0]')
            case['reload_state'] = await page.evaluate(
                """
                () => ({
                  fieldName: document.querySelector('#bankPageFieldInput')?.value || '',
                  activeFilters: document.querySelector('#bankPageActiveFilters')?.textContent || '',
                  search: window.location.search,
                })
                """
            )
            self.assertEqual(case['reload_request']['field_name'], '전산학술')
            self.assertEqual(case['reload_state']['fieldName'], '전산학술')
            self.assertIn('전산학술', case['reload_state']['activeFilters'])
            self.assertIn('field_name=%EC%A0%84%EC%82%B0%ED%95%99%EC%88%A0', case['reload_state']['search'])

            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.evaluate('history.back()')
            await page.waitForFunction("window.location.pathname === '/question-bank'")
            await page.waitForFunction("document.querySelector('#bankPageFieldInput').value === '전산학술'")
            case['back_forward_state'] = await page.evaluate(
                """
                () => ({
                  fieldName: document.querySelector('#bankPageFieldInput')?.value || '',
                  activeFilters: document.querySelector('#bankPageActiveFilters')?.textContent || '',
                  search: window.location.search,
                })
                """
            )
            self.assertEqual(case['back_forward_state']['fieldName'], '전산학술')
            self.assertIn('전산학술', case['back_forward_state']['activeFilters'])
            self.assertIn('field_name=%EC%A0%84%EC%82%B0%ED%95%99%EC%88%A0', case['back_forward_state']['search'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-dynamic-filter-deeplink-reload', status=status, observations=case)
            await page.close()
    async def test_question_bank_page_ignores_stale_filters_on_same_tab_fresh_entry_without_url_params(self):
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
            await page.click('#bankPageLaunchBtn')
            await page.waitForFunction(
                "!document.body.classList.contains('question-bank-practice-collapsed') && !document.querySelector('#bankPagePracticeFrame').hidden"
            )
            case['stored_state_before_navigation'] = await page.evaluate(
                """
                (filterKey, practiceKey) => ({
                  filterState: JSON.parse(window.localStorage.getItem(filterKey) || 'null'),
                  practiceCollapsed: window.localStorage.getItem(practiceKey),
                })
                """,
                QUESTION_BANK_FILTER_STATE_KEY,
                QUESTION_BANK_PRACTICE_COLLAPSED_KEY,
            )
            self.assertEqual(case['stored_state_before_navigation']['filterState']['filters']['q'], '데이터베이스')
            self.assertEqual(case['stored_state_before_navigation']['filterState']['filters']['difficulty'], '중')
            self.assertTrue(case['stored_state_before_navigation']['filterState']['practice']['loaded'])
            self.assertEqual(case['stored_state_before_navigation']['practiceCollapsed'], '0')

            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.evaluate('history.back()')
            await page.waitForFunction("window.location.pathname === '/question-bank'")
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await page.waitForFunction(
                "document.querySelector('#bankPageQueryInput').value === '데이터베이스' && document.querySelector('#bankPageDifficultySelect').value === '중' && !document.body.classList.contains('question-bank-filters-collapsed')"
            )
            case['back_forward_values'] = await page.evaluate(
                """
                () => ({
                  query: document.querySelector('#bankPageQueryInput')?.value || '',
                  difficulty: document.querySelector('#bankPageDifficultySelect')?.value || '',
                  filtersCollapsed: document.body.classList.contains('question-bank-filters-collapsed'),
                  practiceCollapsed: document.body.classList.contains('question-bank-practice-collapsed'),
                  practiceFrameHidden: document.querySelector('#bankPagePracticeFrame')?.hidden,
                  practiceToggleDisabled: document.querySelector('#bankPageTogglePracticeBtn')?.disabled,
                })
                """
            )
            self.assertEqual(case['back_forward_values']['query'], '데이터베이스')
            self.assertEqual(case['back_forward_values']['difficulty'], '중')
            self.assertFalse(case['back_forward_values']['filtersCollapsed'])

            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await page.waitForFunction(
                "document.querySelector('#bankPageQueryInput').value === '' && document.querySelector('#bankPageDifficultySelect').value === '' && document.body.classList.contains('question-bank-filters-collapsed') && document.body.classList.contains('question-bank-practice-collapsed') && document.querySelector('#bankPagePracticeFrame').hidden && document.querySelector('#bankPageTogglePracticeBtn').disabled"
            )
            case['fresh_entry_values'] = await page.evaluate(
                """
                () => ({
                  query: document.querySelector('#bankPageQueryInput')?.value || '',
                  difficulty: document.querySelector('#bankPageDifficultySelect')?.value || '',
                  activeFilters: document.querySelector('#bankPageActiveFilters')?.textContent || '',
                  filtersCollapsed: document.body.classList.contains('question-bank-filters-collapsed'),
                  filtersRegionHidden: document.querySelector('#bankPageFiltersRegion')?.hidden,
                  practiceCollapsed: document.body.classList.contains('question-bank-practice-collapsed'),
                  practiceFrameHidden: document.querySelector('#bankPagePracticeFrame')?.hidden,
                  practiceToggleDisabled: document.querySelector('#bankPageTogglePracticeBtn')?.disabled,
                })
                """
            )
            case['stored_state_after_fresh_entry'] = await page.evaluate(
                """
                (filterKey, practiceKey) => ({
                  filterState: JSON.parse(window.localStorage.getItem(filterKey) || 'null'),
                  practiceCollapsed: window.localStorage.getItem(practiceKey),
                })
                """,
                QUESTION_BANK_FILTER_STATE_KEY,
                QUESTION_BANK_PRACTICE_COLLAPSED_KEY,
            )
            self.assertEqual(case['fresh_entry_values']['query'], '')
            self.assertEqual(case['fresh_entry_values']['difficulty'], '')
            self.assertNotIn('데이터베이스', case['fresh_entry_values']['activeFilters'])
            self.assertNotIn('중', case['fresh_entry_values']['activeFilters'])
            self.assertTrue(case['fresh_entry_values']['filtersCollapsed'])
            self.assertTrue(case['fresh_entry_values']['filtersRegionHidden'])
            self.assertTrue(case['fresh_entry_values']['practiceCollapsed'])
            self.assertTrue(case['fresh_entry_values']['practiceFrameHidden'])
            self.assertTrue(case['fresh_entry_values']['practiceToggleDisabled'])
            self.assertEqual(case['stored_state_after_fresh_entry']['filterState']['filters']['q'], '')
            self.assertEqual(case['stored_state_after_fresh_entry']['filterState']['filters']['difficulty'], '')
            self.assertFalse(case['stored_state_after_fresh_entry']['filterState']['practice']['loaded'])
            self.assertEqual(case['stored_state_after_fresh_entry']['practiceCollapsed'], '1')

            await page.evaluate(
                """
                (filterKey, practiceKey) => {
                  window.localStorage.setItem(filterKey, JSON.stringify({
                    filters: {q: 'stale-query', difficulty: '상'},
                    filtersCollapsed: false,
                    selection: {selectedId: '', startIndex: 0},
                    practice: {loaded: true, selectedId: 'stale-question', startIndex: 1},
                  }));
                  window.localStorage.setItem(practiceKey, '0');
                }
                """,
                QUESTION_BANK_FILTER_STATE_KEY,
                QUESTION_BANK_PRACTICE_COLLAPSED_KEY,
            )
            await page.goto(f'{self.base_url}/question-bank?q=%EB%84%A4%ED%8A%B8%EC%9B%8C%ED%81%AC&difficulty=%ED%95%98', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 0")
            await page.waitForFunction(
                "document.querySelector('#bankPageQueryInput').value === '네트워크' && document.querySelector('#bankPageDifficultySelect').value === '하'"
            )
            case['url_param_values'] = await page.evaluate(
                """
                () => ({
                  query: document.querySelector('#bankPageQueryInput')?.value || '',
                  difficulty: document.querySelector('#bankPageDifficultySelect')?.value || '',
                  activeFilters: document.querySelector('#bankPageActiveFilters')?.textContent || '',
                  filtersCollapsed: document.body.classList.contains('question-bank-filters-collapsed'),
                  practiceCollapsed: document.body.classList.contains('question-bank-practice-collapsed'),
                  practiceFrameHidden: document.querySelector('#bankPagePracticeFrame')?.hidden,
                })
                """
            )
            self.assertEqual(case['url_param_values']['query'], '네트워크')
            self.assertEqual(case['url_param_values']['difficulty'], '하')
            self.assertIn('네트워크', case['url_param_values']['activeFilters'])
            self.assertIn('하', case['url_param_values']['activeFilters'])
            self.assertTrue(case['url_param_values']['filtersCollapsed'])
            self.assertTrue(case['url_param_values']['practiceCollapsed'])
            self.assertTrue(case['url_param_values']['practiceFrameHidden'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-fresh-entry-filters', status=status, observations=case)
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
            case['alternate_row_before_reload'] = await page.evaluate(
                """
                () => {
                  const row = document.querySelector('#bankPageList tbody tr:nth-child(1)');
                  return row ? row.getAttribute('data-table-row-id') || '' : '';
                }
                """
            )
            await page.evaluate(
                """
                (rowId) => {
                  if (!rowId) return;
                  selectQuestionBankItem(rowId);
                }
                """,
                case['alternate_row_before_reload'],
            )
            await page.waitForFunction(
                """
                (rowId) => {
                  const activeRow = document.querySelector('#bankPageList [aria-current="true"]');
                  const summary = document.querySelector('#bankPageSelectionSummary');
                  return activeRow
                    && activeRow.getAttribute('data-table-row-id') === rowId
                    && summary
                    && summary.textContent.includes('선택 1 /')
                    && !document.body.classList.contains('question-bank-practice-collapsed')
                    && !document.querySelector('#bankPagePracticeFrame').hidden;
                }
                """,
                {},
                case['alternate_row_before_reload'],
            )
            case['practice_prompt_after_row_only_reselection'] = await embed_frame.Jeval('.question-prompt', '(node) => (node.textContent || "").trim()')
            self.assertEqual(case['practice_prompt_after_row_only_reselection'], case['practice_prompt_before_reload'])
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
            await page.evaluate(
                """
                (filterKey, rowId) => {
                  const state = JSON.parse(window.localStorage.getItem(filterKey) || 'null');
                  if (!state || !rowId) return;
                  state.selection = {
                    selectedId: rowId,
                    startIndex: 0,
                  };
                  window.localStorage.setItem(filterKey, JSON.stringify(state));
                }
                """,
                QUESTION_BANK_FILTER_STATE_KEY,
                case['alternate_row_before_reload'],
            )
            case['stored_closed_state_with_diverged_selection'] = await page.evaluate(
                '(key) => JSON.parse(window.localStorage.getItem(key) || "null")',
                QUESTION_BANK_FILTER_STATE_KEY,
            )
            self.assertEqual(case['stored_closed_state_with_diverged_selection']['selection']['selectedId'], case['alternate_row_before_reload'])
            self.assertEqual(case['stored_closed_state_with_diverged_selection']['practice']['selectedId'], case['active_row_before_reload'])
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

    async def test_question_bank_page_restores_open_practice_pane_across_history_back(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 1")
            await page.evaluate('document.querySelector("#bankPageList tbody tr:nth-child(2) .question-bank-row-trigger").click()')
            await page.waitForFunction(
                "!document.body.classList.contains('question-bank-practice-collapsed') && !document.querySelector('#bankPagePracticeFrame').hidden"
            )
            case['active_row_before_back'] = await page.evaluate(
                "document.querySelector('#bankPageList [aria-current=\"true\"]')?.getAttribute('data-table-row-id') || ''"
            )
            case['practice_status_before_back'] = await self.text(page, '#bankPagePracticeStatus')
            case['practice_frame_src_before_back'] = await page.Jeval('#bankPagePracticeFrame', '(node) => node.getAttribute("src") || ""')
            case['selected_prompt_before_back'] = await page.Jeval('.question-bank-selection-title', '(node) => (node.textContent || "").trim()')
            self.assertIn('현재 2 /', case['practice_status_before_back'])
            self.assertIn('question-bank-embed=1', case['practice_frame_src_before_back'])
            self.assertTrue(case['selected_prompt_before_back'])

            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.evaluate('history.back()')
            await page.waitForFunction("window.location.pathname === '/question-bank'")
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 1")
            await page.waitForFunction(
                "(expectedId) => { const frame = document.querySelector('#bankPagePracticeFrame'); const activeRow = document.querySelector('#bankPageList [aria-current=\"true\"]'); return activeRow && activeRow.getAttribute('data-table-row-id') === expectedId && !document.body.classList.contains('question-bank-practice-collapsed') && frame && !frame.hidden; }",
                {},
                case['active_row_before_back'],
            )
            case['restored_state_after_back'] = await page.evaluate(
                """
                () => ({
                  activeRowId: document.querySelector('#bankPageList [aria-current="true"]')?.getAttribute('data-table-row-id') || '',
                  practiceCollapsed: document.body.classList.contains('question-bank-practice-collapsed'),
                  practiceFrameHidden: document.querySelector('#bankPagePracticeFrame')?.hidden,
                  practiceFrameSrc: document.querySelector('#bankPagePracticeFrame')?.getAttribute('src') || '',
                })
                """
            )
            case['practice_status_after_back'] = await self.text(page, '#bankPagePracticeStatus')
            case['selected_prompt_after_back'] = await page.Jeval('.question-bank-selection-title', '(node) => (node.textContent || "").trim()')
            self.assertEqual(case['restored_state_after_back']['activeRowId'], case['active_row_before_back'])
            self.assertFalse(case['restored_state_after_back']['practiceCollapsed'])
            self.assertFalse(case['restored_state_after_back']['practiceFrameHidden'])
            self.assertIn('question-bank-embed=1', case['restored_state_after_back']['practiceFrameSrc'])
            self.assertEqual(case['practice_status_after_back'], case['practice_status_before_back'])
            self.assertEqual(case['selected_prompt_after_back'], case['selected_prompt_before_back'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-pane-state-history-back', status=status, observations=case)
            await page.close()

    async def test_question_bank_page_restores_row_selection_without_reopening_practice_on_reload(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 1")
            case['second_row_id'] = await page.evaluate(
                "document.querySelector('#bankPageList tbody tr:nth-child(2)')?.getAttribute('data-table-row-id') || ''"
            )
            await page.evaluate(
                """
                (rowId) => {
                  if (!rowId) return;
                  selectQuestionBankItem(rowId);
                }
                """,
                case['second_row_id'],
            )
            await page.waitForFunction(
                """
                (expectedId) => {
                  const activeRow = document.querySelector('#bankPageList [aria-current="true"]');
                  const summary = document.querySelector('#bankPageSelectionSummary');
                  return activeRow
                    && activeRow.getAttribute('data-table-row-id') === expectedId
                    && summary
                    && summary.textContent.includes('선택 2 /')
                    && document.body.classList.contains('question-bank-practice-collapsed')
                    && document.querySelector('#bankPagePracticeFrame').hidden;
                }
                """,
                {},
                case['second_row_id'],
            )
            case['stored_selection_before_reload'] = await page.evaluate(
                '(key) => JSON.parse(window.localStorage.getItem(key) || "null")',
                QUESTION_BANK_FILTER_STATE_KEY,
            )
            self.assertEqual(case['stored_selection_before_reload']['selection']['selectedId'], case['second_row_id'])
            self.assertEqual(case['stored_selection_before_reload']['selection']['startIndex'], 1)
            self.assertFalse(case['stored_selection_before_reload']['practice']['loaded'])

            await page.reload({'waitUntil': 'networkidle2'})
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 1")
            await page.waitForFunction(
                """
                (expectedId) => {
                  const activeRow = document.querySelector('#bankPageList [aria-current="true"]');
                  const summary = document.querySelector('#bankPageSelectionSummary');
                  const practiceToggle = document.querySelector('#bankPageTogglePracticeBtn');
                  return activeRow
                    && activeRow.getAttribute('data-table-row-id') === expectedId
                    && summary
                    && summary.textContent.includes('선택 2 /')
                    && document.body.classList.contains('question-bank-practice-collapsed')
                    && document.querySelector('#bankPagePracticeFrame').hidden
                    && practiceToggle
                    && practiceToggle.disabled;
                }
                """,
                {},
                case['second_row_id'],
            )
            case['selection_state_after_reload'] = await page.evaluate(
                """
                () => ({
                  activeRowId: document.querySelector('#bankPageList [aria-current="true"]')?.getAttribute('data-table-row-id') || '',
                  selectionSummary: document.querySelector('#bankPageSelectionSummary')?.textContent || '',
                  practiceCollapsed: document.body.classList.contains('question-bank-practice-collapsed'),
                  practiceFrameHidden: document.querySelector('#bankPagePracticeFrame').hidden,
                  practiceToggleDisabled: document.querySelector('#bankPageTogglePracticeBtn').disabled,
                })
                """
            )
            self.assertEqual(case['selection_state_after_reload']['activeRowId'], case['second_row_id'])
            self.assertIn('선택 2 /', case['selection_state_after_reload']['selectionSummary'])
            self.assertTrue(case['selection_state_after_reload']['practiceCollapsed'])
            self.assertTrue(case['selection_state_after_reload']['practiceFrameHidden'])
            self.assertTrue(case['selection_state_after_reload']['practiceToggleDisabled'])
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-selection-reload', status=status, observations=case)
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
                    selection: {selectedId: '', startIndex: 0},
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

    async def test_embedded_question_bank_filters_survive_reload_until_explicit_reset(self):
        case = {'path': '/'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.evaluate('toggleQuestionMode(true)')
            await page.waitForFunction("document.querySelector('#questionPanel').hidden === false")
            await page.click('#questionBankToggleBtn')
            await page.waitForFunction("document.querySelector('#questionBankBrowser').hidden === false")
            await page.waitForFunction("document.querySelectorAll('#questionBankList tr').length > 0")
            await self.set_input_value(page, '#questionBankQueryInput', self.difficulty_regression_prompt)
            await page.select('#questionBankAttemptStatusSelect', 'unseen')
            await page.waitForFunction(
                "(value) => document.querySelector('#questionBankQueryInput').value === value && document.querySelector('#questionBankAttemptStatusSelect').value === 'unseen' && window.location.search.includes('q=') && window.location.search.includes('attempt_status=unseen')",
                {},
                self.difficulty_regression_prompt,
            )
            case['url_after_filter'] = await page.evaluate('window.location.search')
            self.assertIn('attempt_status=unseen', case['url_after_filter'])
            self.assertIn('q=', case['url_after_filter'])

            await page.reload({'waitUntil': 'networkidle2'})
            await page.waitForFunction("document.querySelector('#questionPanel').hidden === false")
            await page.waitForFunction("document.querySelector('#questionBankBrowser').hidden === false")
            await page.waitForFunction(
                "(value) => document.querySelector('#questionBankQueryInput').value === value && document.querySelector('#questionBankAttemptStatusSelect').value === 'unseen'",
                {},
                self.difficulty_regression_prompt,
            )
            case['query_after_reload'] = await page.Jeval('#questionBankQueryInput', '(node) => node.value')
            case['attempt_status_after_reload'] = await page.Jeval('#questionBankAttemptStatusSelect', '(node) => node.value')
            self.assertEqual(case['query_after_reload'], self.difficulty_regression_prompt)
            self.assertEqual(case['attempt_status_after_reload'], 'unseen')

            await page.click('#questionBankResetFiltersBtn')
            await page.waitForFunction(
                "document.querySelector('#questionBankQueryInput').value === '' && document.querySelector('#questionBankAttemptStatusSelect').value === '' && window.location.search === ''"
            )
            case['url_after_reset'] = await page.evaluate('window.location.search')
            self.assertEqual(case['url_after_reset'], '')

            await page.reload({'waitUntil': 'networkidle2'})
            await page.waitForFunction("document.querySelector('#questionPanel').hidden === true")
            case['question_panel_hidden_after_reset_reload'] = await page.evaluate("document.querySelector('#questionPanel').hidden")
            self.assertTrue(case['question_panel_hidden_after_reset_reload'])
            status = 'passed'
        finally:
            self.record_case(case_id='embedded-question-bank-filter-reload', status=status, observations=case)
            await page.close()
    async def test_embedded_question_bank_mobile_layout_stacks_controls_without_overflow(self):
        case = {'path': '/'}
        page = await self.new_page(viewport={'width': 390, 'height': 844})
        status = 'failed'
        try:
            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.evaluate('toggleQuestionMode(true)')
            await page.waitForFunction("document.querySelector('#questionPanel').hidden === false")
            await page.click('#questionBankToggleBtn')
            await page.waitForFunction("document.querySelector('#questionBankBrowser').hidden === false")
            await page.waitForFunction("document.querySelectorAll('#questionBankList tr').length > 0")
            case['layout'] = await page.evaluate(
                """
                () => {
                  const viewportWidth = window.innerWidth;
                  const rect = (selector) => {
                    const node = document.querySelector(selector);
                    if (!node) return null;
                    const box = node.getBoundingClientRect();
                    return {left: box.left, right: box.right, width: box.width};
                  };
                  const fits = (selector) => [...document.querySelectorAll(selector)].every((node) => {
                    const box = node.getBoundingClientRect();
                    return box.left >= -1 && box.right <= viewportWidth + 1;
                  });
                  return {
                    browserRect: rect('#questionBankBrowser'),
                    tableWrapRect: rect('.question-bank-table-wrap'),
                    headDirection: getComputedStyle(document.querySelector('.question-bank-head')).flexDirection,
                    actionsDisplay: getComputedStyle(document.querySelector('.question-bank-actions')).display,
                    filterColumns: getComputedStyle(document.querySelector('.question-bank-filter-grid')).gridTemplateColumns.split(' ').length,
                    actionButtonsFit: fits('.question-bank-actions .question-toolbar-button'),
                    filterControlsFit: fits('.question-bank-filter-grid > *'),
                  };
                }
                """
            )
            self.assertEqual(case['layout']['headDirection'], 'column')
            self.assertEqual(case['layout']['actionsDisplay'], 'grid')
            self.assertEqual(case['layout']['filterColumns'], 1)
            self.assertTrue(case['layout']['actionButtonsFit'])
            self.assertTrue(case['layout']['filterControlsFit'])
            self.assertLessEqual(case['layout']['browserRect']['right'], 391)
            self.assertLessEqual(case['layout']['tableWrapRect']['right'], case['layout']['browserRect']['right'] + 1)
            status = 'passed'
        finally:
            self.record_case(case_id='embedded-question-bank-mobile-layout', status=status, observations=case)
            await page.close()

    async def test_question_bank_mobile_practice_solve_layout(self):
        case = {'path': '/question-bank'}
        page = await self.new_page(viewport={'width': 390, 'height': 844})
        status = 'failed'
        payload = self.question_bank_payload('mobile-practice', items=[
            self.question_bank_item('모바일 첫 문항', question_bank_id='mobile-practice-1'),
            self.question_bank_item('모바일 둘째 문항', question_bank_id='mobile-practice-2'),
        ])
        try:
            await page.evaluateOnNewDocument(
                """
                (questionBankPayload) => {
                  const originalFetch = window.fetch.bind(window);
                  window.fetch = (input, init = undefined) => {
                    const url = typeof input === 'string' ? input : input.url;
                    const method = ((init && init.method) || (typeof input !== 'string' && input.method) || 'GET').toUpperCase();
                    const parsed = new URL(url, window.location.origin);
                    if (parsed.pathname === '/api/question-bank' && method === 'GET') {
                      return Promise.resolve(new Response(JSON.stringify(questionBankPayload), {
                        status: 200,
                        headers: {'Content-Type': 'application/json'},
                      }));
                    }
                    return originalFetch(input, init);
                  };
                }
                """,
                payload,
            )
            await page.goto(f'{self.base_url}/question-bank', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#bankPageList [data-table-row-id]').length > 1")
            case['table_layout'] = await page.evaluate(
                """
                () => {
                  const viewportWidth = window.innerWidth;
                  const row = document.querySelector('#bankPageList tbody tr');
                  const cell = row?.querySelector('td');
                  const wrap = document.querySelector('#bankPageList .cs-table-wrap');
                  const rowBox = row?.getBoundingClientRect();
                  const wrapBox = wrap?.getBoundingClientRect();
                  return {
                    viewportWidth,
                    rowDisplay: row ? getComputedStyle(row).display : '',
                    cellDisplay: cell ? getComputedStyle(cell).display : '',
                    tableScrollGap: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                    rowRight: rowBox ? rowBox.right : 0,
                    wrapRight: wrapBox ? wrapBox.right : 0,
                  };
                }
                """
            )
            self.assertEqual(case['table_layout']['rowDisplay'], 'block')
            self.assertEqual(case['table_layout']['cellDisplay'], 'grid')
            self.assertLessEqual(case['table_layout']['tableScrollGap'], 2)
            self.assertLessEqual(case['table_layout']['rowRight'], case['table_layout']['viewportWidth'] + 1)
            self.assertLessEqual(case['table_layout']['wrapRight'], case['table_layout']['viewportWidth'] + 1)

            await page.click('#bankPageLaunchBtn')
            await page.waitForFunction("!document.querySelector('#bankPagePracticeFrame').hidden")
            embed_frame = await self.wait_for_embed_frame(page)
            await embed_frame.waitForSelector('#questionAnswerSaveBtn')
            case['practice_layout'] = await embed_frame.evaluate(
                """
                () => {
                  const viewportWidth = window.innerWidth;
                  const shell = document.querySelector('.question-card-shell');
                  const saveButton = document.getElementById('questionAnswerSaveBtn');
                  const topbarActions = document.querySelector('.question-embed-topbar-actions');
                  const rect = (node) => {
                    if (!node) return null;
                    const box = node.getBoundingClientRect();
                    return {left: box.left, right: box.right, width: box.width};
                  };
                  return {
                    viewportWidth,
                    overflowGap: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                    shell: rect(shell),
                    saveButton: rect(saveButton),
                    topbarActions: rect(topbarActions),
                    topbarActionsDisplay: topbarActions ? getComputedStyle(topbarActions).display : '',
                    actionColumns: getComputedStyle(document.querySelector('.question-actions')).gridTemplateColumns.split(' ').length,
                  };
                }
                """
            )
            self.assertLessEqual(case['practice_layout']['overflowGap'], 2)
            self.assertLessEqual(case['practice_layout']['shell']['right'], case['practice_layout']['viewportWidth'] + 1)
            self.assertLessEqual(case['practice_layout']['saveButton']['right'], case['practice_layout']['viewportWidth'] + 1)
            self.assertLessEqual(case['practice_layout']['topbarActions']['right'], case['practice_layout']['viewportWidth'] + 1)
            self.assertIn(case['practice_layout']['topbarActionsDisplay'], ('grid', 'flex'))
            self.assertEqual(case['practice_layout']['actionColumns'], 1)
            status = 'passed'
        finally:
            self.record_case(case_id='question-bank-mobile-practice-solve-layout', status=status, observations=case)
            await page.close()
    async def test_embedded_question_bank_dynamic_select_deep_link_survives_first_request_and_reload(self):
        case = {'path': '/?field_name=전산학술&q=embedded&attempt_status=wrong'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        payload = self.question_bank_payload(
            'embedded-dynamic-field',
            items=[self.question_bank_item('전산학술 문항', field_name='전산학술', category='데이터베이스', issuer='한국은행', question_attempt_status='wrong')],
        )
        payload['summary']['available_field_names'] = ['전산학술', '테스트분야']
        payload['summary']['available_categories'] = ['데이터베이스']
        payload['summary']['available_issuers'] = ['한국은행']
        try:
            await page.evaluateOnNewDocument(
                """
                (responsePayload) => {
                  window.__questionBankRequestQueries = [];
                  const originalFetch = window.fetch.bind(window);
                  window.fetch = (input, init = undefined) => {
                    const url = typeof input === 'string' ? input : input.url;
                    const parsed = new URL(url, window.location.origin);
                    if (parsed.pathname !== '/api/question-bank') return originalFetch(input, init);
                    window.__questionBankRequestQueries.push({
                      q: parsed.searchParams.get('q') || '',
                      attempt_status: parsed.searchParams.get('attempt_status') || '',
                      field_name: parsed.searchParams.get('field_name') || '',
                    });
                    return Promise.resolve(new Response(JSON.stringify(responsePayload), {
                      status: 200,
                      headers: {'Content-Type': 'application/json'},
                    }));
                  };
                }
                """,
                payload,
            )
            await page.goto(f'{self.base_url}/?field_name=%EC%A0%84%EC%82%B0%ED%95%99%EC%88%A0&q=embedded&attempt_status=wrong', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelector('#questionPanel').hidden === false")
            await page.waitForFunction("document.querySelector('#questionBankBrowser').hidden === false")
            await page.waitForFunction("window.__questionBankRequestQueries.length > 0")
            await page.waitForFunction("document.querySelectorAll('#questionBankList tr').length > 0")
            await page.waitForFunction("document.querySelector('#questionBankQueryInput').value === 'embedded' && document.querySelector('#questionBankAttemptStatusSelect').value === 'wrong' && document.querySelector('#questionBankFieldInput').value === '전산학술'")
            case['initial_request'] = await page.evaluate('window.__questionBankRequestQueries[0]')
            case['initial_state'] = await page.evaluate(
                """
                () => ({
                  q: document.querySelector('#questionBankQueryInput')?.value || '',
                  attemptStatus: document.querySelector('#questionBankAttemptStatusSelect')?.value || '',
                  fieldName: document.querySelector('#questionBankFieldInput')?.value || '',
                  activeFilters: document.querySelector('#questionBankSummary')?.textContent || '',
                  search: window.location.search,
                })
                """
            )
            self.assertEqual(case['initial_request']['q'], 'embedded')
            self.assertEqual(case['initial_request']['attempt_status'], 'wrong')
            self.assertEqual(case['initial_request']['field_name'], '전산학술')
            self.assertEqual(case['initial_state']['q'], 'embedded')
            self.assertEqual(case['initial_state']['attemptStatus'], 'wrong')
            self.assertEqual(case['initial_state']['fieldName'], '전산학술')
            self.assertIn('field_name=%EC%A0%84%EC%82%B0%ED%95%99%EC%88%A0', case['initial_state']['search'])
            self.assertIn('attempt_status=wrong', case['initial_state']['search'])
            self.assertIn('q=embedded', case['initial_state']['search'])

            await page.reload({'waitUntil': 'networkidle2'})
            await page.waitForFunction("document.querySelector('#questionPanel').hidden === false")
            await page.waitForFunction("document.querySelector('#questionBankBrowser').hidden === false")
            await page.waitForFunction("window.__questionBankRequestQueries.length > 0")
            await page.waitForFunction("document.querySelectorAll('#questionBankList tr').length > 0")
            await page.waitForFunction("document.querySelector('#questionBankQueryInput').value === 'embedded' && document.querySelector('#questionBankAttemptStatusSelect').value === 'wrong' && document.querySelector('#questionBankFieldInput').value === '전산학술'")
            case['reload_request'] = await page.evaluate('window.__questionBankRequestQueries[0]')
            case['reload_state'] = await page.evaluate(
                """
                () => ({
                  q: document.querySelector('#questionBankQueryInput')?.value || '',
                  attemptStatus: document.querySelector('#questionBankAttemptStatusSelect')?.value || '',
                  fieldName: document.querySelector('#questionBankFieldInput')?.value || '',
                  rows: document.querySelector('#questionBankList')?.textContent || '',
                  search: window.location.search,
                })
                """
            )
            self.assertEqual(case['reload_request']['q'], 'embedded')
            self.assertEqual(case['reload_request']['attempt_status'], 'wrong')
            self.assertEqual(case['reload_request']['field_name'], '전산학술')
            self.assertEqual(case['reload_state']['q'], 'embedded')
            self.assertEqual(case['reload_state']['attemptStatus'], 'wrong')
            self.assertEqual(case['reload_state']['fieldName'], '전산학술')
            self.assertIn('전산학술 문항', case['reload_state']['rows'])
            self.assertIn('field_name=%EC%A0%84%EC%82%B0%ED%95%99%EC%88%A0', case['reload_state']['search'])
            self.assertIn('attempt_status=wrong', case['reload_state']['search'])
            self.assertIn('q=embedded', case['reload_state']['search'])
            status = 'passed'
        finally:
            self.record_case(case_id='embedded-question-bank-dynamic-select-reload', status=status, observations=case)
            await page.close()
    async def test_embedded_question_bank_text_filters_debounce_requests(self):
        case = {'path': '/'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.evaluate('toggleQuestionMode(true)')
            await page.waitForFunction("document.querySelector('#questionPanel').hidden === false")
            await page.click('#questionBankToggleBtn')
            await page.waitForFunction("document.querySelector('#questionBankBrowser').hidden === false")
            await page.waitForFunction("document.querySelectorAll('#questionBankList tr').length > 0")
            await self.install_delayed_json_route(
                page,
                route_path='/api/question-bank',
                key_param='q',
                responses={
                    'a': {'delayMs': 0, 'payload': self.question_bank_payload('a')},
                    'al': {'delayMs': 0, 'payload': self.question_bank_payload('al')},
                    'alpha': {'delayMs': 0, 'payload': self.question_bank_payload('alpha')},
                },
            )
            await self.set_input_value(page, '#questionBankQueryInput', 'a')
            await self.set_input_value(page, '#questionBankQueryInput', 'al')
            await self.set_input_value(page, '#questionBankQueryInput', 'alpha')
            await asyncio.sleep(0.08)
            case['fetch_count_before_debounce'] = await page.evaluate("() => (window.__testRouteFetchLog?.['/api/question-bank'] || []).length")
            self.assertEqual(case['fetch_count_before_debounce'], 0)
            await page.waitForFunction("(window.__testRouteFetchLog?.['/api/question-bank'] || []).length === 1")
            await page.waitForFunction("document.querySelector('#questionBankList').textContent.includes('alpha prompt')")
            await asyncio.sleep(0.25)
            case['fetch_log'] = await page.evaluate("() => (window.__testRouteFetchLog?.['/api/question-bank'] || []).map((entry) => entry.key)")
            case['question_bank_text'] = await self.text(page, '#questionBankList')
            self.assertEqual(case['fetch_log'], ['alpha'])
            self.assertIn('alpha prompt', case['question_bank_text'])
            status = 'passed'
        finally:
            self.record_case(case_id='embedded-question-bank-filter-debounce', status=status, observations=case)
            await page.close()

    async def test_embedded_question_bank_enter_triggers_immediate_refresh(self):
        case = {'path': '/'}
        page = await self.new_page(viewport={'width': 1440, 'height': 1100})
        status = 'failed'
        try:
            await page.goto(self.base_url, waitUntil='networkidle2')
            await page.evaluate('toggleQuestionMode(true)')
            await page.waitForFunction("document.querySelector('#questionPanel').hidden === false")
            await page.click('#questionBankToggleBtn')
            await page.waitForFunction("document.querySelector('#questionBankBrowser').hidden === false")
            await page.waitForFunction("document.querySelectorAll('#questionBankList tr').length > 0")
            await self.install_delayed_json_route(
                page,
                route_path='/api/question-bank',
                key_param='q',
                responses={
                    'enter-now': {'delayMs': 0, 'payload': self.question_bank_payload('enter-now')},
                },
            )
            await self.set_input_value(page, '#questionBankQueryInput', 'enter-now', submit=True)
            await asyncio.sleep(0.08)
            case['fetch_count_before_debounce'] = await page.evaluate("() => (window.__testRouteFetchLog?.['/api/question-bank'] || []).length")
            self.assertEqual(case['fetch_count_before_debounce'], 1)
            await asyncio.sleep(0.25)
            case['fetch_log'] = await page.evaluate("() => (window.__testRouteFetchLog?.['/api/question-bank'] || []).map((entry) => entry.key)")
            self.assertEqual(case['fetch_log'], ['enter-now'])
            status = 'passed'
        finally:
            self.record_case(case_id='embedded-question-bank-enter-refresh', status=status, observations=case)
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


    async def test_wiki_mobile_layout_uses_focus_safe_drawer_without_overflow(self):
        case = {'path': '/wiki'}
        page = await self.new_page(viewport={'width': 390, 'height': 844})
        status = 'failed'
        try:
            await page.goto(f'{self.base_url}/wiki', waitUntil='networkidle2')
            await page.waitForFunction("document.querySelectorAll('#wikiToc .wiki-toc-link').length > 0")
            case['initial_layout'] = await page.evaluate(
                """
                () => {
                  const viewportWidth = window.innerWidth;
                  const mainBox = document.querySelector('.wiki-main').getBoundingClientRect();
                  return {
                    pageOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                    viewportWidth,
                    mainRight: mainBox.right,
                    topbarToggleDisplay: getComputedStyle(document.querySelector('#wikiSidebarTopbarBtn')).display,
                    dockDisplay: getComputedStyle(document.querySelector('.wiki-sidebar-dock')).display,
                  };
                }
                """
            )
            self.assertLessEqual(case['initial_layout']['pageOverflow'], 2)
            self.assertLessEqual(case['initial_layout']['mainRight'], case['initial_layout']['viewportWidth'] + 1)
            self.assertNotEqual(case['initial_layout']['topbarToggleDisplay'], 'none')
            self.assertEqual(case['initial_layout']['dockDisplay'], 'none')

            await page.click('#wikiSidebarTopbarBtn')
            await page.waitForFunction("document.body.classList.contains('wiki-mobile-sidebar-open')")
            case['drawer_open'] = await page.evaluate(
                """
                () => {
                  const sidebar = document.querySelector('#wikiSidebar');
                  const backdrop = document.querySelector('#wikiSidebarBackdrop');
                  const box = sidebar.getBoundingClientRect();
                  return {
                    bodyClassOpen: document.body.classList.contains('wiki-mobile-sidebar-open'),
                    backdropHidden: backdrop.hidden,
                    viewportWidth: window.innerWidth,
                    sidebarLeft: box.left,
                    sidebarRight: box.right,
                    sidebarWidth: box.width,
                    bodyOverflow: getComputedStyle(document.body).overflow,
                    topbarExpanded: document.querySelector('#wikiSidebarTopbarBtn').getAttribute('aria-expanded') || '',
                  };
                }
                """
            )
            case['focus_after_drawer_open'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            self.assertTrue(case['drawer_open']['bodyClassOpen'])
            self.assertFalse(case['drawer_open']['backdropHidden'])
            self.assertLessEqual(case['drawer_open']['sidebarLeft'], 1)
            self.assertLessEqual(case['drawer_open']['sidebarRight'], case['drawer_open']['viewportWidth'] + 1)
            self.assertGreater(case['drawer_open']['sidebarWidth'], 200)
            self.assertEqual(case['drawer_open']['bodyOverflow'], 'hidden')
            self.assertEqual(case['drawer_open']['topbarExpanded'], 'true')

            await page.keyboard.press('Escape')
            await page.waitForFunction("!document.body.classList.contains('wiki-mobile-sidebar-open')")
            case['focus_after_drawer_close'] = await page.evaluate('document.activeElement && document.activeElement.id ? document.activeElement.id : ""')
            case['drawer_closed'] = await page.evaluate(
                """
                () => ({
                  bodyClassOpen: document.body.classList.contains('wiki-mobile-sidebar-open'),
                  backdropHidden: document.querySelector('#wikiSidebarBackdrop').hidden,
                  topbarExpanded: document.querySelector('#wikiSidebarTopbarBtn').getAttribute('aria-expanded') || '',
                })
                """
            )
            self.assertFalse(case['drawer_closed']['bodyClassOpen'])
            self.assertTrue(case['drawer_closed']['backdropHidden'])
            self.assertEqual(case['drawer_closed']['topbarExpanded'], 'false')

            await page.click('#wikiSearchToggleBtn')
            await page.waitForFunction("document.querySelector('#wikiSearch').hidden === false")
            await page.type('#wikiSearchInput', '심화')
            await page.keyboard.press('Enter')
            await page.waitForFunction("document.body.classList.contains('wiki-mobile-sidebar-open')")
            await page.waitForFunction("document.querySelector('#wikiStatus').textContent.includes('검색 결과 1건')")
            case['search_results_layout'] = await page.evaluate(
                """
                () => {
                  const inputBox = document.querySelector('#wikiSearchInput').getBoundingClientRect();
                  const tocLink = document.querySelector('#wikiToc .wiki-toc-link');
                  return {
                    pageOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                    searchHidden: document.querySelector('#wikiSearch').hidden,
                    viewportWidth: window.innerWidth,
                    searchRight: inputBox.right,
                    tocLinkText: tocLink ? (tocLink.textContent || '').trim() : '',
                  };
                }
                """
            )
            self.assertLessEqual(case['search_results_layout']['pageOverflow'], 2)
            self.assertTrue(case['search_results_layout']['searchHidden'])
            self.assertLessEqual(case['search_results_layout']['searchRight'], case['search_results_layout']['viewportWidth'] + 1)
            self.assertIn('심화 문서', case['search_results_layout']['tocLinkText'])

            await page.evaluate(
                """
                () => {
                  const target = Array.from(document.querySelectorAll('#wikiToc .wiki-toc-link'))
                    .find((link) => (link.textContent || '').includes('심화 문서'));
                  if (target) target.click();
                }
                """
            )
            await page.waitForFunction("window.location.pathname.endsWith('/wiki/page/deep-dive')")
            await page.waitForFunction("!document.body.classList.contains('wiki-mobile-sidebar-open')")
            case['post_navigation'] = await page.evaluate(
                """
                () => ({
                  pageOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                  bodyClassOpen: document.body.classList.contains('wiki-mobile-sidebar-open'),
                  currentPath: window.location.pathname,
                })
                """
            )
            self.assertLessEqual(case['post_navigation']['pageOverflow'], 2)
            self.assertFalse(case['post_navigation']['bodyClassOpen'])
            self.assertTrue(case['post_navigation']['currentPath'].endswith('/wiki/page/deep-dive'))
            status = 'passed'
        finally:
            self.record_case(case_id='wiki-mobile-layout', status=status, observations=case)
            await page.close()
if __name__ == '__main__':
    unittest.main()
