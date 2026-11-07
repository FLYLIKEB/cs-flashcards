"""The spoken lesson points to actual, reviewed Java source lines."""
import asyncio
from functools import partial
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading
import unittest

from pyppeteer import launch
from tests.test_coding_lessons import LessonHandler
from tests.test_coding_practice import ROOT, KEY


def code_links():
    return {item['id']: item for part in ('01-15', '16-30') for item in
            json.loads((ROOT / f'static/coding-code-links-{part}.json').read_text())}


def content(name):
    value = json.loads((ROOT / f'static/{name}').read_text())
    return {item['id']: item for item in value}


def tracks():
    return {item['id']: item for item in json.loads(
        (ROOT / 'static/coding-audio/manifest.json').read_text())['lessons']}


class CodeLinkDataTests(unittest.TestCase):
    def test_every_explanation_maps_to_reviewed_source_lines(self):
        links, lessons, problems = code_links(), content('coding-lessons.json'), content('coding-problems.json')
        self.assertEqual(sorted(links), list(range(1, 31)))
        total = 0
        for problem_id, link in links.items():
            source = problems[problem_id]['java']['solution']
            lines = source.rstrip().splitlines()
            self.assertEqual(link['sourceHash'], hashlib.sha256(source.encode()).hexdigest())
            self.assertEqual(len(link['scenes']), 5)
            for index, scene in enumerate(link['scenes']):
                self.assertEqual(len(scene['cues']), len(lessons[problem_id]['scenes'][index]['segments']))
                for cue in scene['cues']:
                    with self.subTest(problem=problem_id, scene=index, cue=cue):
                        self.assertTrue(cue['note'].strip())
                        self.assertLessEqual(len(cue['note']), 40)
                        self.assertGreaterEqual(len(cue['lines']), 1)
                        self.assertLessEqual(len(cue['lines']), 3)
                        self.assertEqual(cue['lines'], sorted(set(cue['lines'])))
                        for number in cue['lines']:
                            self.assertIsInstance(number, int)
                            self.assertGreaterEqual(number, 1)
                            self.assertLessEqual(number, len(lines))
                            self.assertRegex(lines[number - 1], r'[^\s{};]')
                    total += 1
        intro_count = sum(scene.get('introCueCount', 0) for lesson in lessons.values() for scene in lesson['scenes'])
        self.assertEqual(total - intro_count, 620)

    def test_operation_explanations_point_to_the_operation_not_arbitrary_progress(self):
        links, problems = code_links(), content('coding-problems.json')
        for problem_id, scene, cue, operation in (
            (1, 3, 0, 'seen.add(id)'),
            (2, 3, 0, 'first.get(target - amounts[j])'),
            (2, 3, 2, 'first.putIfAbsent'),
            (20, 3, 2, 'cost != distance[node]'),
            (26, 3, 2, 'oldest.remove()'),
        ):
            source = problems[problem_id]['java']['solution'].splitlines()
            selected = links[problem_id]['scenes'][scene]['cues'][cue]['lines']
            self.assertIn(operation, '\n'.join(source[n - 1] for n in selected))


class CodeHandler(LessonHandler):
    def do_GET(self):
        if getattr(self.server, 'code_unavailable', False) and self.path.startswith('/static/coding-code-links-'):
            self.send_error(503)
            return
        super().do_GET()


class CodeFollowBrowserTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(CodeHandler, directory=str(ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/static/coding.html'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    async def asyncSetUp(self):
        self.server.code_unavailable = False
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
        await self.page.waitForFunction('document.querySelector("#lessonAudio").readyState >= 1 && !document.querySelector("#lessonPlay").disabled')

    async def select_problem(self, number):
        await self.page.evaluate('(n) => document.querySelectorAll("#problems button")[n - 1].click()', number)
        await self.ready()

    async def scene(self, index):
        for _ in range(index):
            await self.page.click('#lessonNext')
        await self.ready()

    async def seek(self, seconds):
        await self.page.Jeval('#lessonSeek', '(el, value) => { el.value = value; el.dispatchEvent(new Event("input", {bubbles: true})); }', seconds)
        await self.page.waitForFunction('(t) => Math.abs(document.querySelector("#lessonAudio").currentTime - t) < 0.1', {}, seconds)
        await asyncio.sleep(0.05)

    async def current_lines(self, selector='#lessonCode'):
        return await self.page.JJeval(selector + ' .is-current', 'els => els.map(el => Number(el.dataset.line))')

    async def seek_body(self, problem_id, scene=0):
        cue_index = content('coding-lessons.json')[problem_id]['scenes'][scene].get('introCueCount', 0)
        cue = tracks()[problem_id]['scenes'][scene]['cues'][cue_index]
        await self.seek((cue['start'] + cue['end']) / 2)
        await self.page.waitForFunction('!document.querySelector("#lessonCodePanel").hidden')
        return cue_index

    async def assert_cue(self, problem_id, scene, cue):
        expected = code_links()[problem_id]['scenes'][scene]['cues'][cue]
        self.assertEqual(await self.current_lines(), expected['lines'])
        self.assertEqual(await self.current_lines('#lessonCodeSource'), expected['lines'])
        self.assertEqual(await self.page.Jeval('#lessonCodeNote', 'el => el.textContent'), expected['note'])
        self.assertEqual(await self.page.Jeval('#lessonSubtitle', 'el => el.textContent'), tracks()[problem_id]['scenes'][scene]['cues'][cue]['text'])
        source = content('coding-problems.json')[problem_id]['java']['solution'].splitlines()
        displayed = await self.page.JJeval('#lessonCode .code-row code', 'els => els.map(el => el.textContent.trim())')
        self.assertEqual(displayed, [source[n - 1].strip() for n in expected['lines']])

    async def test_audio_seek_pause_and_speed_keep_code_and_caption_together(self):
        await self.select_problem(2)
        await self.scene(3)
        cues = tracks()[2]['scenes'][3]['cues']
        self.assertTrue(await self.page.Jeval('#lessonAudio', 'el => el.paused'))
        for index in (0, 2, 1, 3, 0):
            await self.seek((cues[index]['start'] + cues[index]['end']) / 2)
            await self.assert_cue(2, 3, index)
        held = await self.current_lines()
        await asyncio.sleep(0.2)
        self.assertEqual(await self.current_lines(), held)
        await self.page.click('#lessonSettings > summary')
        await self.page.select('#lessonRate', '1.5')
        await self.seek(cues[1]['start'] - 0.1)
        await self.page.click('#lessonPlay')
        await self.page.waitForFunction('(text) => document.querySelector("#lessonSubtitle").textContent === text', {}, cues[1]['text'])
        await self.page.click('#lessonPlay')
        await self.assert_cue(2, 3, 1)
        self.assertEqual(await self.page.Jeval('#lessonAudio', 'el => el.playbackRate'), 1.5)
        await self.page.reload()
        await self.ready()
        await self.assert_cue(2, 3, 0)
        self.assertTrue(await self.page.Jeval('#lessonAudio', 'el => el.paused'))
        await self.select_problem(1)
        body_cue = await self.seek_body(1)
        await self.assert_cue(1, 0, body_cue)

    async def test_problem_intro_hides_code_until_body_and_seek_back_restores_intro(self):
        scene = content('coding-lessons.json')[1]['scenes'][0]
        intro_count = scene['introCueCount']
        cues = tracks()[1]['scenes'][0]['cues']
        self.assertGreater(intro_count, 0)
        self.assertLess(intro_count, len(cues))
        self.assertTrue(await self.page.Jeval('#lessonCodePanel', 'el => el.hidden'))
        self.assertEqual(await self.page.Jeval('#lessonSceneTitle', 'el => el.textContent'), '어떤 문제인가요?')
        self.assertEqual(await self.page.Jeval('#lessonSubtitle', 'el => el.textContent'), cues[0]['text'])
        await self.seek(cues[intro_count]['start'] - 0.05)
        self.assertTrue(await self.page.Jeval('#lessonCodePanel', 'el => el.hidden'))
        await self.seek(cues[intro_count]['start'])
        await self.page.waitForFunction('!document.querySelector("#lessonCodePanel").hidden')
        self.assertEqual(await self.page.Jeval('#lessonSceneTitle', 'el => el.textContent'), scene['title'])
        await self.assert_cue(1, 0, intro_count)
        await self.seek(0)
        self.assertTrue(await self.page.Jeval('#lessonCodePanel', 'el => el.hidden'))
        self.assertEqual(await self.page.Jeval('#lessonSceneTitle', 'el => el.textContent'), '어떤 문제인가요?')
        self.assertEqual(await self.page.Jeval('#lessonSubtitle', 'el => el.textContent'), cues[0]['text'])
        self.assertTrue(await self.page.Jeval('#lessonAudio', 'el => el.paused'))

    async def test_full_source_follows_only_inside_its_scroll_container(self):
        await self.select_problem(20)
        await self.scene(3)
        await self.page.setViewport({'width': 1440, 'height': 900})
        self.assertTrue(await self.page.Jeval('#lessonFullCode', 'el => el.open'))
        await self.page.evaluate('window.scrollTo(0, 0)')
        before_y = await self.page.evaluate('scrollY')
        cues = tracks()[20]['scenes'][3]['cues']
        await self.seek((cues[1]['start'] + cues[1]['end']) / 2)
        await self.assert_cue(20, 3, 1)
        self.assertEqual(await self.page.evaluate('scrollY'), before_y)
        self.assertGreater(await self.page.Jeval('#lessonCodeSource', 'el => el.scrollTop'), 0)
        self.assertTrue(await self.page.Jeval('#lessonCodeSource', '''el => {
            const row = el.querySelector('.is-current');
            return row.offsetTop >= el.scrollTop && row.offsetTop < el.scrollTop + el.clientHeight;
        }'''))
        await self.seek(0)
        await self.assert_cue(20, 3, 0)
        self.assertEqual(await self.page.evaluate('scrollY'), before_y)
        await self.page.screenshot({'path': '/tmp/code-follow-desktop.png', 'fullPage': True})
        await self.page.setViewport({'width': 390, 'height': 844})
        self.assertTrue(await self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        await self.page.Jeval('#lessonCodePanel', 'el => el.scrollIntoView({block: "start"})')
        self.assertGreater(await self.page.Jeval('#lessonCode', 'el => el.getBoundingClientRect().width'), 200)
        self.assertGreaterEqual(await self.page.Jeval('#lessonCode', 'el => parseFloat(getComputedStyle(el).fontSize)'), 12)
        await self.page.screenshot({'path': '/tmp/code-follow-mobile.png', 'fullPage': True})

    async def test_code_exposure_is_assistance_not_independent_completion(self):
        await self.seek_body(1)
        self.assertTrue(await self.page.Jeval('#lessonFullCode', 'el => el.open'))
        await self.page.waitForFunction('(key) => JSON.parse(localStorage.getItem(key)).records[1].lessonAssisted', {}, KEY)
        await self.page.click('#modePractice')
        await self.page.click('[data-step="2"]')
        for checkbox in await self.page.JJ('#checks input'):
            await checkbox.click()
        await self.page.click('[data-verdict="solved"]')
        state = await self.page.evaluate('(key) => JSON.parse(localStorage.getItem(key))', KEY)
        self.assertNotEqual(state['records']['1']['status'], 'solved')
        await self.page.click('#restart')
        state = await self.page.evaluate('(key) => JSON.parse(localStorage.getItem(key))', KEY)
        self.assertFalse(state['records']['1'].get('lessonAssisted', False))

    async def test_code_link_failure_keeps_sound_and_full_java_available(self):
        self.server.code_unavailable = True
        await self.page.reload()
        await self.ready()
        await self.seek_body(1)
        self.assertEqual(await self.current_lines(), [])
        self.assertIn('불러오지 못', await self.page.Jeval('#lessonCodeNote', 'el => el.textContent'))
        self.assertTrue(await self.page.Jeval('#lessonFullCode', 'el => el.open'))
        source = content('coding-problems.json')[1]['java']['solution'].rstrip().splitlines()
        self.assertEqual(await self.page.JJeval('#lessonCodeSource code', 'els => els.map(el => el.textContent)'), source)
        await self.page.click('#lessonPlay')
        await self.page.waitForFunction('!document.querySelector("#lessonAudio").paused && document.querySelector("#lessonAudio").currentTime > 0.1')
        self.assertTrue(await self.page.Jeval('#lessonSubtitle', 'el => Boolean(el.textContent)'))
        await self.page.click('#lessonPlay')
