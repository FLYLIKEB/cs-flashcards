"""Curriculum correctness and isolated browser flows; never opens the live SQLite DB."""
import asyncio
from copy import deepcopy
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import unittest

from pyppeteer import launch

ROOT = Path(__file__).resolve().parents[1]
KEY = 'csCoding48:v1'


class CodingCurriculumTests(unittest.TestCase):
    def test_curriculum_contract_and_reference_solutions(self):
        problems = json.loads((ROOT / 'static/coding-problems.json').read_text())
        self.assertEqual([p['id'] for p in problems], list(range(1, 31)))
        self.assertEqual(sum(p['day'] == 1 for p in problems), 15)
        self.assertEqual(sum(p['day'] == 2 for p in problems), 15)
        for p in problems:
            with self.subTest(problem=p['id']):
                self.assertEqual(len(p['hints']), 3)
                self.assertGreaterEqual(len(p['tests']), 3)
                self.assertTrue(p['examples'])
                for key in ('title', 'statement', 'approach', 'complexity', 'explainPrompt', 'pitfalls'):
                    self.assertTrue(p[key], key)
                namespace = {}
                exec(compile(p['solution'], f"problem-{p['id']}", 'exec'), namespace)
                for test in p['tests']:
                    self.assertEqual(namespace['solve'](*deepcopy(test['args'])), test['expected'])


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class CodingBrowserTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/static/coding.html'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    async def asyncSetUp(self):
        options = dict(headless=True, args=['--no-sandbox'], handleSIGINT=False,
                       handleSIGTERM=False, handleSIGHUP=False, autoClose=False)
        chrome = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        if chrome.exists():
            options['executablePath'] = str(chrome)
        self.browser = await launch(**options)
        self.addAsyncCleanup(self.browser.close)
        self.page = await self.browser.newPage()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('dialog', lambda dialog: asyncio.ensure_future(dialog.accept()))
        await self.page.goto(self.url)
        await self.ready()

    async def asyncTearDown(self):
        self.assertEqual(self.errors, [])

    async def ready(self):
        await self.page.waitForFunction("document.querySelectorAll('#problems button').length === 30")

    async def state(self):
        return await self.page.evaluate('(key) => JSON.parse(localStorage.getItem(key))', KEY)

    async def fill(self, selector, value):
        await self.page.evaluate('''(selector, value) => {
            const input = document.querySelector(selector);
            input.value = value;
            input.dispatchEvent(new Event('input', {bubbles: true}));
        }''', selector, value)

    async def test_drafts_timer_and_mobile_layout_survive_reload(self):
        await self.fill('#code', 'def solve(values):\n    return values\n')
        await self.fill('#notes', '중복과 빈 입력 확인')
        await self.page.click('#timerToggle')
        initial = (await self.state())['records']['1']['started']
        await self.page.reload()
        await self.ready()
        self.assertEqual(await self.page.Jeval('#notes', '(el) => el.value'), '중복과 빈 입력 확인')
        self.assertIn('return values', await self.page.Jeval('#code', '(el) => el.value'))
        self.assertEqual((await self.state())['records']['1']['started'], initial)
        self.assertEqual(await self.page.Jeval('#timerToggle', '(el) => el.textContent'), '일시정지')
        await self.page.setViewport({'width': 1440, 'height': 1100})
        await self.page.screenshot({'path': '/tmp/coding48-desktop.png', 'fullPage': True})
        await self.page.setViewport({'width': 390, 'height': 844})
        self.assertTrue(await self.page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), await self.page.evaluate("() => Array.from(document.querySelectorAll('body *')).filter(el => el.getBoundingClientRect().right > innerWidth).map(el => [el.tagName, el.id, el.className, el.getBoundingClientRect().right]).slice(0,20)"))

    async def test_hint_restart_completion_and_day_filters(self):
        await self.page.click('#hint')
        self.assertEqual((await self.state())['records']['1']['status'], 'review')
        await self.page.click('[data-verdict="solved"]')
        self.assertIn('체크리스트', await self.page.Jeval('#result', '(el) => el.textContent'))
        await self.page.click('#restart')
        await self.page.waitForFunction("document.querySelector('#hint').textContent.includes('(0/3)')")
        for checkbox in await self.page.JJ('#checks input'):
            await checkbox.click()
        await self.page.click('[data-verdict="solved"]')
        self.assertEqual((await self.state())['records']['1']['status'], 'solved')
        self.assertEqual(await self.page.Jeval('#completed', '(el) => el.textContent'), '1 / 30')
        for day in ('1', '2'):
            await self.page.click(f'[data-filter="{day}"]')
            self.assertEqual(len(await self.page.JJ('#problems button')), 15)
        await self.page.click('[data-filter="review"]')
        self.assertEqual(len(await self.page.JJ('#problems button')), 0)

    async def test_answer_marks_review_and_due_review_is_recommended(self):
        await self.page.click('#answer summary')
        await self.page.waitForFunction("JSON.parse(localStorage.getItem('csCoding48:v1'))?.records?.['1']?.answer")
        self.assertEqual((await self.state())['records']['1']['status'], 'review')
        await self.page.evaluate('''key => {
            const state = JSON.parse(localStorage.getItem(key));
            state.records['1'].due = 1;
            localStorage.setItem(key, JSON.stringify(state));
        }''', KEY)
        await self.page.reload()
        await self.ready()
        await self.page.click('#problems button:nth-child(2)')
        await self.page.click('#recommend')
        self.assertTrue((await self.page.Jeval('#title', '(el) => el.textContent')).startswith('01.'))

    async def test_downloaded_python_runner_executes_reference_and_reports_failure(self):
        problems = json.loads((ROOT / 'static/coding-problems.json').read_text())
        await self.page.evaluate("""() => {
            const create = URL.createObjectURL.bind(URL);
            URL.createObjectURL = blob => { window.downloadedBlob = blob; return create(blob); };
        }""")
        for code, returncode in ((problems[0]['solution'], 0), ('def solve(*args):\n    return object()\n', 1)):
            await self.fill('#code', code)
            await self.page.click('#download')
            script = await self.page.evaluate('window.downloadedBlob.text()')
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'solution.py'
                path.write_text(script)
                result = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, returncode, result.stdout + result.stderr)
            self.assertIn('PASS' if returncode == 0 else 'FAIL', result.stdout)

    async def test_invalid_import_preserves_draft_and_valid_restore(self):
        await self.fill('#notes', '보존할 메모')
        before = await self.state()
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / 'invalid.json'
            invalid.write_text('{"records":{"1":{"code":"invalid"}}}')
            input_element = await self.page.J('#import')
            await input_element.uploadFile(str(invalid))
            await self.page.waitForFunction("document.querySelector('#notice').textContent.includes('복원 실패')")
            self.assertEqual(await self.state(), before)
            valid = Path(directory) / 'valid.json'
            restored = deepcopy(before)
            restored['records']['1']['notes'] = '복원된 메모'
            valid.write_text(json.dumps(restored))
            await input_element.uploadFile(str(valid))
            await self.page.waitForFunction("document.querySelector('#notes').value === '복원된 메모'")
            self.assertEqual((await self.state())['records']['1']['notes'], '복원된 메모')


if __name__ == '__main__':
    unittest.main()
