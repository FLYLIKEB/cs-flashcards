from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import socket
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
MAIN_WORKSPACE_ROOT = ROOT.parent / 'cs_flashcards'
QUESTION_BANK_LAUNCH_KEY = 'csPendingQuestionBankLaunch:v1'
WIKI_SIDEBAR_STATE_KEY = 'csFlashcardsWikiSidebar:v1'
WAVE_ID_RE = re.compile(r'^(wave-\d+)')
CANONICAL_COMMAND = '.venv/bin/python -m unittest tests.test_frontend_browser'
TRANSCRIPT_DIR = ROOT / 'artifacts' / 'frontend-browser'


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
        python_candidates = [ROOT / '.venv' / 'bin' / 'python', MAIN_WORKSPACE_ROOT / '.venv' / 'bin' / 'python']
        python_path = next((path for path in python_candidates if path.exists()), None)
        if python_path is None:
            raise RuntimeError('A project .venv Python is required to run the frontend browser harness.')
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

    def question_bank_payload(self, label: str) -> dict[str, object]:
        return {
            'items': [
                {
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
                }
            ],
            'summary': {
                'total': 1,
                'returned': 1,
                'available_topics': [label],
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
        page = await self.new_page(viewport={'width': 640, 'height': 960})
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
            case['sidebar_initially_open'] = await page.evaluate(
                "document.querySelector('#wikiSidebarToggleBtn').getAttribute('aria-expanded') === 'true'"
            )
            self.assertFalse(case['sidebar_initially_open'])
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
            self.assertIn('일치하는 문서가 없습니다.', case['wiki_status'])
            status = 'passed'
        finally:
            self.record_case(case_id='wiki-sidebar-status', status=status, observations=case)
            await page.close()


if __name__ == '__main__':
    unittest.main()
