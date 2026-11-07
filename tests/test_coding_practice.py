"""Curriculum correctness and isolated browser flows; never opens the live SQLite DB."""
import asyncio
from copy import deepcopy
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import subprocess
from pathlib import Path
import tempfile
import threading
import unittest

from pyppeteer import launch

ROOT = Path(__file__).resolve().parents[1]
KEY = 'csCoding48:java:v1'
LEGACY_KEY = 'csCoding48:v1'


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
        if await self.page.Jeval('#practicePanel', 'el => el.hidden'):
            await self.page.click('#modePractice')

    async def state(self):
        return await self.page.evaluate('(key) => JSON.parse(localStorage.getItem(key))', KEY)

    async def step(self, index):
        await self.page.click(f'[data-step="{index}"]')
        await self.page.waitForFunction(
            '(index) => !document.querySelector(["#readPanel", "#writePanel", "#reviewPanel"][index]).hidden', {}, index,
        )

    async def open_details(self, selector):
        if not await self.page.Jeval(selector, '(el) => el.open'):
            await self.page.click(selector + ' > summary')

    async def choose_problem(self, problem_id):
        await self.open_details('#curriculum')
        await self.page.click(f'#problems button:nth-child({problem_id})')

    async def fill(self, selector, value):
        if selector == '#code':
            await self.step(1)
        elif selector == '#notes':
            await self.step(2)
        await self.page.evaluate('''(selector, value) => {
            const input = document.querySelector(selector);
            input.value = value;
            input.dispatchEvent(new Event('input', {bubbles: true}));
        }''', selector, value)

    async def test_drafts_timer_and_mobile_layout_survive_reload(self):
        await self.fill('#code', 'class Solution { public static String[] solve(String[] values) { return values; } }')
        await self.fill('#notes', '중복과 빈 입력 확인')
        await self.page.click('#timerToggle')
        initial = (await self.state())['records']['1']['started']
        await self.page.reload()
        await self.ready()
        self.assertEqual(await self.page.Jeval('#notes', '(el) => el.value'), '중복과 빈 입력 확인')
        self.assertIn('return values', await self.page.Jeval('#code', '(el) => el.value'))
        self.assertEqual((await self.state())['records']['1']['started'], initial)
        self.assertEqual(await self.page.Jeval('#timerToggle', '(el) => el.textContent'), '일시정지')
        await self.step(1)
        await self.page.setViewport({'width': 1440, 'height': 1100})
        await self.page.screenshot({'path': '/tmp/coding48-focus-desktop.png', 'fullPage': True})
        await self.page.setViewport({'width': 390, 'height': 844})
        await self.page.screenshot({'path': '/tmp/coding48-focus-mobile.png', 'fullPage': True})
        self.assertTrue(await self.page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), await self.page.evaluate("() => Array.from(document.querySelectorAll('body *')).filter(el => el.getBoundingClientRect().right > innerWidth).map(el => [el.tagName, el.id, el.className, el.getBoundingClientRect().right]).slice(0,20)"))

    async def test_hint_restart_completion_and_day_filters(self):
        await self.step(1)
        await self.page.click('#hint')
        self.assertEqual((await self.state())['records']['1']['status'], 'review')
        await self.step(2)
        await self.page.click('[data-verdict="solved"]')
        self.assertIn('체크리스트', await self.page.Jeval('#result', '(el) => el.textContent'))
        await self.page.click('#restart')
        await self.page.waitForFunction("document.querySelector('#hint').textContent.includes('(0/3)')")
        await self.step(2)
        for checkbox in await self.page.JJ('#checks input'):
            await checkbox.click()
        await self.page.click('[data-verdict="solved"]')
        self.assertEqual((await self.state())['records']['1']['status'], 'solved')
        self.assertEqual(await self.page.Jeval('#completed', '(el) => el.textContent'), '1 / 30')
        await self.open_details('#curriculum')
        for day in ('1', '2'):
            await self.page.click(f'[data-filter="{day}"]')
            self.assertEqual(len(await self.page.JJ('#problems button')), 15)
        await self.page.click('[data-filter="review"]')
        self.assertEqual(len(await self.page.JJ('#problems button')), 0)

    async def test_answer_marks_review_and_due_review_is_recommended(self):
        await self.step(1)
        await self.page.click('#answer summary')
        await self.page.waitForFunction("JSON.parse(localStorage.getItem('csCoding48:java:v1'))?.records?.['1']?.answer")
        self.assertEqual((await self.state())['records']['1']['status'], 'review')
        await self.page.evaluate('''key => {
            const state = JSON.parse(localStorage.getItem(key));
            state.records['1'].due = 1;
            localStorage.setItem(key, JSON.stringify(state));
        }''', KEY)
        await self.page.reload()
        await self.ready()
        await self.choose_problem(2)
        await self.open_details('#curriculum')
        await self.page.click('#recommend')
        self.assertTrue((await self.page.Jeval('#title', '(el) => el.textContent')).startswith('01.'))
        self.assertEqual(await self.page.evaluate('document.activeElement.id'), 'stepPrompt')
        self.assertFalse(await self.page.Jeval('#curriculum', '(el) => el.open'))

    async def test_focus_starts_with_one_step_and_preserves_return_context(self):
        self.assertEqual(await self.page.Jeval('#timer', '(el) => el.getAttribute("role")'), 'timer')
        self.assertEqual(await self.page.Jeval('#timer', '(el) => el.getAttribute("aria-live")'), 'off')
        self.assertTrue(await self.page.Jeval('#writePanel', '(el) => el.getClientRects().length === 0'))
        self.assertTrue(await self.page.Jeval('#reviewPanel', '(el) => el.getClientRects().length === 0'))
        self.assertFalse(await self.page.Jeval('#curriculum', '(el) => el.open'))
        self.assertFalse(await self.page.Jeval('#readPanel', '(el) => el.hidden'))
        self.assertTrue(await self.page.Jeval('#writePanel', '(el) => el.hidden'))
        self.assertTrue(await self.page.Jeval('#reviewPanel', '(el) => el.hidden'))
        self.assertIsNone((await self.state())['records']['1']['started'])
        await self.page.click('#stageNext')
        self.assertFalse(await self.page.Jeval('#writePanel', '(el) => el.hidden'))
        await self.fill('#nextAction', '중복 요청을 건너뛰는 조건부터 작성')
        await self.page.reload()
        await self.ready()
        self.assertFalse(await self.page.Jeval('#writePanel', '(el) => el.hidden'))
        self.assertEqual(await self.page.Jeval('#nextAction', '(el) => el.value'), '중복 요청을 건너뛰는 조건부터 작성')
        await self.open_details('#reference')
        self.assertIn('String[]', await self.page.Jeval('#reference', '(el) => el.textContent'))
        await self.page.click('#stageNext')
        self.assertFalse(await self.page.Jeval('#reviewPanel', '(el) => el.hidden'))
        self.assertEqual((await self.state())['records']['1']['step'], 2)

    async def test_break_pauses_and_resumes_same_draft_without_auto_start(self):
        await self.fill('#code', 'class Solution { /* 이어서 작성 */ }')
        await self.fill('#nextAction', 'HashSet 선언 다음부터')
        await self.page.click('#timerToggle')
        self.assertIsNotNone((await self.state())['records']['1']['started'])
        await self.page.click('#breakButton')
        self.assertTrue((await self.state())['focus']['onBreak'])
        self.assertIsNone((await self.state())['records']['1']['started'])
        self.assertTrue(await self.page.Jeval('#workArea', '(el) => el.hidden'))
        self.assertFalse(await self.page.Jeval('#breakPanel', '(el) => el.hidden'))
        self.assertIn('HashSet 선언 다음부터', await self.page.Jeval('#returnNote', '(el) => el.textContent'))
        await self.page.reload()
        await self.ready()
        self.assertFalse(await self.page.Jeval('#breakPanel', '(el) => el.hidden'))
        self.assertIsNone((await self.state())['records']['1']['started'])
        await self.page.click('#resumeButton')
        self.assertFalse((await self.state())['focus']['onBreak'])
        self.assertFalse(await self.page.Jeval('#writePanel', '(el) => el.hidden'))
        self.assertIn('이어서 작성', await self.page.Jeval('#code', '(el) => el.value'))
        self.assertIsNone((await self.state())['records']['1']['started'])

    async def test_session_controls_hide_clock_and_expire_without_losing_work(self):
        await self.open_details('#sessionSettings')
        await self.page.select('#sessionMinutes', '5')
        await self.page.click('#hideTimer')
        self.assertTrue(await self.page.Jeval('#timer', '(el) => el.hidden'))
        self.assertEqual((await self.state())['focus']['minutes'], 5)
        self.assertTrue((await self.state())['focus']['hideTimer'])
        await self.fill('#code', 'class Solution { /* timeout must preserve */ }')
        await self.page.evaluate("""key => {
            const state = JSON.parse(localStorage.getItem(key));
            state.records['1'].elapsed = 299;
            state.records['1'].started = Date.now() - 2000;
            localStorage.setItem(key, JSON.stringify(state));
        }""", KEY)
        await self.page.reload()
        await self.ready()
        await self.page.waitForFunction("JSON.parse(localStorage.getItem('csCoding48:java:v1')).records['1'].started === null")
        self.assertTrue(await self.page.Jeval('#timer', '(el) => el.hidden'))
        self.assertIn('timeout must preserve', await self.page.Jeval('#code', '(el) => el.value'))
        self.assertFalse(await self.page.Jeval('#writePanel', '(el) => el.hidden'))
        self.assertTrue(await self.page.Jeval('#sessionStatus', '(el) => el.textContent.trim().length > 0'))
        await self.page.click('#timerToggle')
        renewed = (await self.state())['records']['1']
        self.assertIsNotNone(renewed['started'])
        self.assertLess(renewed['elapsed'], 2)
        await self.page.click('#timerToggle')
        self.assertIsNone((await self.state())['records']['1']['started'])

    async def test_invalid_focus_import_preserves_existing_record(self):
        await self.fill('#nextAction', '이 기록을 유지')
        before = await self.state()
        with tempfile.TemporaryDirectory() as directory:
            for focus in ({'minutes': -5, 'hideTimer': False, 'onBreak': False},
                          {'minutes': 10, 'hideTimer': 'yes', 'onBreak': False},
                          {'minutes': 10, 'hideTimer': False, 'onBreak': 'yes'}):
                with self.subTest(focus=focus):
                    invalid = deepcopy(before)
                    invalid['focus'] = focus
                    path = Path(directory) / 'invalid-focus.json'
                    path.write_text(json.dumps(invalid))
                    await self.page.evaluate("document.querySelector('#notice').textContent = ''")
                    await (await self.page.J('#import')).uploadFile(str(path))
                    await self.page.waitForFunction("document.querySelector('#notice').textContent.includes('복원 실패')")
                    self.assertEqual(await self.state(), before)

    async def capture_downloads(self):
        await self.page.evaluate("""() => {
            const create = URL.createObjectURL.bind(URL);
            URL.createObjectURL = blob => { window.downloadedBlob = blob; return create(blob); };
            HTMLAnchorElement.prototype.click = function () { window.downloadedName = this.download; };
        }""")

    def compile_and_run(self, source):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Main.java'
            path.write_text(source)
            compiled = subprocess.run(
                ['javac', '--release', '17', '-encoding', 'UTF-8', str(path)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(
                ['java', '-cp', directory, 'Main'], capture_output=True, text=True, timeout=10,
            )

    async def test_all_downloaded_java_solutions_compile_and_pass(self):
        problems = json.loads((ROOT / 'static/coding-problems.json').read_text())
        await self.capture_downloads()
        total = 0
        for p in problems:
            with self.subTest(problem=p['id']):
                await self.choose_problem(p['id'])
                self.assertEqual(await self.page.Jeval('#code', '(el) => el.value'), p['java']['starter'])
                await self.fill('#code', p['java']['solution'])
                await self.page.click('#download')
                self.assertEqual(await self.page.evaluate('window.downloadedName'), 'Main.java')
                source = await self.page.evaluate('window.downloadedBlob.text()')
                result = await asyncio.to_thread(self.compile_and_run, source)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                passed = sum(line.startswith('PASS') for line in result.stdout.splitlines())
                self.assertEqual(passed, len(p['tests']), result.stdout)
                total += passed
        self.assertEqual(total, sum(len(p['tests']) for p in problems))
        self.assertGreaterEqual(total, 101)

    async def test_java_long_results_do_not_overflow(self):
        problems = json.loads((ROOT / 'static/coding-problems.json').read_text())
        cases = {
            5: 'int[] a = new int[3000]; Arrays.fill(a, 1000000); check(() -> Solution.solve(a, new int[][]{{0, 2999}}), new long[]{3000000000L}, "overflow");',
            6: 'int[] a = new int[3000]; Arrays.fill(a, 1000000); check(() -> Solution.solve(a, 3000), 3000000000L, "overflow");',
            18: 'int[] a = new int[3000]; Arrays.fill(a, 1000000); check(() -> Solution.solve(a, 1), 3000000000L, "overflow");',
            19: 'check(() -> Solution.solve(new int[65536], 0L), 2147516416L, "overflow");',
            20: 'int[][] e = new int[3000][3]; for (int i = 0; i < 3000; i++) e[i] = new int[]{i, i+1, 1000000}; check(() -> Solution.solve(3001, e, 0, 3000), 3000000000L, "overflow");',
            23: 'int[] a = new int[5]; Arrays.fill(a, 1000000000); check(() -> Solution.solve(a), 3000000000L, "overflow");',
            30: 'int[] a = new int[3001]; Arrays.fill(a, 1000000); int[][] e = new int[3000][2]; for (int i = 0; i < 3000; i++) e[i] = new int[]{i, i+1}; check(() -> Solution.solve(a, e), 3001000000L, "overflow");',
        }
        await self.capture_downloads()
        for problem_id, extra_case in cases.items():
            with self.subTest(problem=problem_id):
                await self.choose_problem(problem_id)
                await self.fill('#code', problems[problem_id - 1]['java']['solution'])
                await self.page.click('#download')
                source = await self.page.evaluate('window.downloadedBlob.text()')
                anchor = 'public static void main(String[] args) {'
                self.assertIn(anchor, source)
                source = source.replace(anchor, anchor + '\n' + extra_case, 1)
                result = await asyncio.to_thread(self.compile_and_run, source)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('PASS overflow', result.stdout)

    async def test_java_runner_rejects_wrong_answer_and_exception(self):
        await self.capture_downloads()
        for body in ('return new String[0];', 'throw new IllegalStateException("test failure");'):
            with self.subTest(body=body):
                await self.fill('#code', 'class Solution { public static String[] solve(String[] ids) { ' + body + ' } }')
                await self.page.click('#download')
                source = await self.page.evaluate('window.downloadedBlob.text()')
                result = await asyncio.to_thread(self.compile_and_run, source)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('FAIL', result.stdout)

    async def test_python_records_remain_archived_and_java_backup_round_trips(self):
        legacy_record = {
            'code': 'def solve(ids):\n    return list(dict.fromkeys(ids))\n',
            'notes': '기존 Python 메모', 'checks': [True] * 4, 'elapsed': 125,
            'started': None, 'hints': 0, 'answer': False, 'status': 'solved', 'due': 0,
        }
        legacy = {'records': {'1': legacy_record}, 'current': 1}
        raw = json.dumps(legacy)
        await self.page.evaluate("""(key, legacyKey, raw) => {
            localStorage.removeItem(key);
            localStorage.setItem(legacyKey, raw);
        }""", KEY, LEGACY_KEY, raw)
        await self.page.reload()
        await self.ready()
        self.assertEqual(await self.page.evaluate('(key) => localStorage.getItem(key)', LEGACY_KEY), raw)
        self.assertTrue(await self.page.Jeval('#code', "el => el.value.includes('class Solution')"))
        self.assertEqual(await self.page.Jeval('#notes', '(el) => el.value'), legacy_record['notes'])
        self.assertEqual(await self.page.Jeval('#completed', '(el) => el.textContent'), '0 / 30')
        self.assertFalse(await self.page.Jeval('#legacyPanel', '(el) => el.hidden'))
        self.assertEqual(await self.page.Jeval('#legacyCode', '(el) => el.textContent'), legacy_record['code'])
        await self.fill('#notes', 'Java 메모')
        await self.capture_downloads()
        await self.open_details('.backup-menu')
        await self.page.click('#export')
        backup_text = await self.page.evaluate('window.downloadedBlob.text()')
        backup = json.loads(backup_text)
        self.assertEqual(backup['language'], 'java')
        self.assertEqual(backup['pythonRecords']['1'], legacy_record)
        self.assertEqual(backup['records']['1']['notes'], 'Java 메모')
        await self.page.reload()
        await self.ready()
        self.assertEqual(await self.page.Jeval('#notes', '(el) => el.value'), 'Java 메모')
        self.assertEqual(await self.page.Jeval('#legacyCode', '(el) => el.textContent'), legacy_record['code'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'backup.json'
            path.write_text(backup_text)
            await self.fill('#notes', '덮어쓸 메모')
            await (await self.page.J('#import')).uploadFile(str(path))
            await self.page.waitForFunction("document.querySelector('#notes').value === 'Java 메모'")
            self.assertEqual((await self.state())['pythonRecords']['1'], legacy_record)
            old_path = Path(directory) / 'python-backup.json'
            old_path.write_text(raw)
            await (await self.page.J('#import')).uploadFile(str(old_path))
            await self.page.waitForFunction("document.querySelector('#notes').value === '기존 Python 메모'")
            self.assertTrue(await self.page.Jeval('#code', "el => el.value.includes('class Solution')"))
            self.assertEqual((await self.state())['pythonRecords']['1'], legacy_record)
            self.assertEqual(await self.page.evaluate('(key) => localStorage.getItem(key)', LEGACY_KEY), raw)

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
