"""Authored algorithm motion must follow the real audio clock, including seeking."""
import asyncio
from functools import partial
from http.server import ThreadingHTTPServer
import json
import math
import re
from pathlib import Path
import threading
import unittest

from pyppeteer import launch
from tests.test_coding_lessons import LessonHandler
from tests.test_coding_practice import ROOT, KEY


def storyboards():
    return sum((json.loads((ROOT / f'static/coding-motion-{part}.json').read_text())
                for part in ('01-15', '16-30')), [])


def soundtracks():
    return {item['id']: item for item in
            json.loads((ROOT / 'static/coding-audio/manifest.json').read_text())['lessons']}


class MotionDataTests(unittest.TestCase):
    def test_all_150_scenes_have_valid_cue_timed_algorithm_changes(self):
        stories = storyboards()
        tracks = soundtracks()
        self.assertEqual([item['id'] for item in stories], list(range(1, 31)))
        for lesson in stories:
            with self.subTest(problem=lesson['id']):
                self.assertEqual(len(lesson['scenes']), 5)
                moved = False
                for scene_index, scene in enumerate(lesson['scenes']):
                    frames = scene['frames']
                    self.assertGreaterEqual(len(frames), 3)
                    cues = [frame['cue'] for frame in frames]
                    self.assertEqual(cues, sorted(set(cues)))
                    self.assertEqual(cues[0], 0)
                    self.assertLess(cues[-1], len(tracks[lesson['id']]['scenes'][scene_index]['cues']))
                    previous = {}
                    distinct = set()
                    for frame in frames:
                        nodes = frame['nodes']
                        ids = {node['id'] for node in nodes}
                        self.assertGreater(len(ids), 0)
                        self.assertTrue(any(node['label'].strip() for node in nodes))
                        self.assertEqual(len(ids), len(nodes))
                        distinct.add(json.dumps(nodes, sort_keys=True))
                        for node in nodes:
                            self.assertIsInstance(node['id'], str)
                            self.assertIsInstance(node['label'], str)
                            self.assertIn(node.get('tone', 'default'), ('default', 'blue', 'green', 'red', 'muted'))
                            for key in ('x', 'y'):
                                self.assertTrue(math.isfinite(node[key]))
                            width, height = node.get('w', 90), node.get('h', 44)
                            self.assertGreater(width, 0)
                            self.assertGreater(height, 0)
                            self.assertGreaterEqual(node['x'] - width / 2, 0)
                            self.assertLessEqual(node['x'] + width / 2, 640)
                            self.assertGreaterEqual(node['y'] - height / 2, 0)
                            self.assertLessEqual(node['y'] + height / 2, 240)
                            old = previous.get(node['id'])
                            moved |= bool(old and any(old.get(key, default) != node.get(key, default)
                                                     for key, default in (('x', 0), ('y', 0), ('w', 90), ('h', 44))))
                        for edge in frame.get('edges', []):
                            self.assertIn(edge['from'], ids)
                            self.assertIn(edge['to'], ids)
                            self.assertNotEqual(edge['from'], edge['to'])
                        previous = {node['id']: node for node in nodes}
                    self.assertGreaterEqual(len(distinct), 3, (lesson['id'], scene_index))
                self.assertTrue(moved, f'Problem {lesson["id"]} never moves an algorithm object')


    def test_worked_examples_retain_algorithm_results(self):
        stories = {lesson['id']: lesson for lesson in storyboards()}
        deduplicated = stories[1]['scenes'][2]['frames'][-1]['nodes']
        result = sorted((node for node in deduplicated if node.get('tone') == 'green'), key=lambda node: node['x'])
        self.assertEqual([node['label'] for node in result], ['b', 'a', 'c'])
        hops = stories[13]['scenes'][2]['frames'][-1]['nodes']
        self.assertIn('2 거리 2', [node['label'].replace('\n', ' ') for node in hops])
        grid = stories[24]['scenes'][2]['frames'][-1]['nodes']
        self.assertTrue(any(node['label'] == '2' for node in grid))
        cache = stories[26]['scenes'][2]['frames'][-1]['nodes']
        self.assertTrue(any('[1, -1, 3]' in node['label'] for node in cache))
        batch = stories[30]['scenes'][0]['frames'][-1]['nodes']
        self.assertTrue(any('11' in node['label'] for node in batch))


class MotionHandler(LessonHandler):
    def do_GET(self):
        if getattr(self.server, 'motion_unavailable', False) and self.path.startswith('/static/coding-motion-'):
            self.send_error(503)
            return
        super().do_GET()


class MotionBrowserTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(MotionHandler, directory=str(ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/static/coding.html'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    async def asyncSetUp(self):
        self.server.motion_unavailable = False
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
        await self.page.goto(self.url)
        await self.ready()

    async def asyncTearDown(self):
        self.assertEqual(self.errors, [])

    async def ready(self):
        await self.page.waitForFunction("document.querySelector('#lessonCards svg') && document.querySelector('#lessonAudio').readyState >= 1 && !document.querySelector('#lessonPlay').disabled")

    async def seek(self, seconds):
        await self.page.Jeval('#lessonSeek', '''(el, value) => {
            el.value = value;
            el.dispatchEvent(new Event('input', {bubbles: true}));
        }''', seconds)
        await self.page.waitForFunction('(time) => Math.abs(document.querySelector("#lessonAudio").currentTime - time) < 0.1', {}, seconds)
        await asyncio.sleep(0.05)

    async def snapshot(self):
        return await self.page.JJeval('#lessonCards g[data-node]', '''els => els.map(el => ({
            id: el.dataset.node, transform: el.getAttribute('transform'),
            opacity: el.getAttribute('opacity'), text: el.textContent
        })).sort((a, b) => a.id.localeCompare(b.id))''')

    async def select_problem(self, problem_id):
        if not await self.page.Jeval('#curriculum', 'el => el.open'):
            await self.page.click('#curriculum > summary')
        await self.page.click(f'#problems button:nth-child({problem_id})')
        await self.ready()

    async def moving_scene(self):
        lesson = json.loads((ROOT / 'static/coding-motion-01-15.json').read_text())[0]
        for scene_index, scene in enumerate(lesson['scenes']):
            for index, frame in enumerate(scene['frames'][1:], 1):
                old = {n['id']: n for n in scene['frames'][index - 1]['nodes']}
                moving = next((node for node in frame['nodes'] if node['id'] in old and
                               (node['x'], node['y']) != (old[node['id']]['x'], old[node['id']]['y'])), None)
                if moving:
                    for _ in range(scene_index):
                        await self.page.click('#lessonNext')
                    await self.ready()
                    return scene_index, index, frame, moving
        self.fail('Lesson 1 needs a moving data object')

    async def test_real_playback_seek_pause_and_rate_share_one_clock(self):
        self.assertTrue(await self.page.Jeval('#lessonAudio', 'el => el.paused'))
        scene_index, frame_index, frame, moving = await self.moving_scene()
        cue = soundtracks()[1]['scenes'][scene_index]['cues'][frame['cue']]
        await self.page.setViewport({'width': 1440, 'height': 900})
        before = await self.snapshot()
        await self.page.screenshot({'path': '/tmp/motion-before.png', 'fullPage': True})
        await self.page.click('#lessonPlay')
        await self.page.waitForFunction('!document.querySelector("#lessonAudio").paused && document.querySelector("#lessonAudio").currentTime > 0.1')
        await self.page.click('#lessonPlay')
        await self.seek(cue['start'] + 0.2)
        held = await self.snapshot()
        await asyncio.sleep(0.3)
        self.assertEqual(await self.snapshot(), held, 'Motion must freeze with paused audio')
        await self.seek(min(cue['start'] + 1.0, cue['end'] - 0.05))
        self.assertEqual(await self.page.Jeval('#lessonCards svg', 'el => Number(el.dataset.frame)'), frame_index)
        self.assertEqual(await self.page.Jeval('#lessonSubtitle', 'el => el.textContent'), cue['text'])
        self.assertNotEqual(await self.snapshot(), before)
        transform = await self.page.Jeval(f'#lessonCards g[data-node="{moving["id"]}"]', 'el => el.getAttribute("transform")')
        self.assertEqual([float(value) for value in re.findall(r'-?\d+(?:\.\d+)?', transform)], [moving['x'], moving['y']])
        await self.page.screenshot({'path': '/tmp/motion-after.png', 'fullPage': True})
        await self.seek(0)
        self.assertEqual(await self.page.Jeval('#lessonCards svg', 'el => el.dataset.frame'), '0')
        self.assertEqual(await self.snapshot(), before)
        await self.page.click('#lessonSettings > summary')
        await self.page.select('#lessonRate', '1.5')
        await self.seek(max(0, cue['start'] - 0.15))
        await self.page.click('#lessonPlay')
        await self.page.waitForFunction('(index) => Number(document.querySelector("#lessonCards svg").dataset.frame) === index', {}, frame_index)
        await self.page.click('#lessonPlay')
        self.assertEqual(await self.page.Jeval('#lessonAudio', 'el => el.playbackRate'), 1.5)
        self.assertEqual(await self.page.Jeval('#lessonSubtitle', 'el => el.textContent'), cue['text'])
        await self.page.click('#modePractice')
        self.assertTrue(await self.page.Jeval('#lessonAudio', 'el => el.paused'))
        self.assertFalse(await self.page.Jeval('#practicePanel', 'el => el.hidden'))
        state = await self.page.evaluate('(key) => JSON.parse(localStorage.getItem(key))', KEY)
        self.assertNotEqual(state['records']['1']['status'], 'solved')

    async def test_reduced_motion_keeps_algorithm_state_without_tween(self):
        scene_index, _, frame, moving = await self.moving_scene()
        await self.page._client.send('Emulation.setEmulatedMedia', {'features': [{'name':'prefers-reduced-motion', 'value':'reduce'}]})
        await self.page.click('#lessonPlay')
        await self.page.waitForFunction('document.querySelector("#lessonAudio").currentTime > 0.1')
        await self.page.click('#lessonPlay')
        cue = soundtracks()[1]['scenes'][scene_index]['cues'][frame['cue']]
        await self.seek(cue['start'] + 0.1)
        transform = await self.page.Jeval(f'#lessonCards g[data-node="{moving["id"]}"]', 'el => el.getAttribute("transform")')
        self.assertEqual([float(value) for value in re.findall(r'-?\d+(?:\.\d+)?', transform)], [moving['x'], moving['y']])
        self.assertEqual(await self.page.Jeval('#lessonSubtitle', 'el => el.textContent'), cue['text'])

    async def test_stack_graph_grid_and_cache_fit_mobile_and_desktop(self):
        for problem_id in (9, 13, 24, 26, 30):
            await self.select_problem(problem_id)
            for name, width, height in [('desktop', 1440, 900), ('mobile', 390, 844)]:
                await self.page.setViewport({'width': width, 'height': height})
                await self.page.evaluate('scrollTo(0, 0)')
                self.assertTrue(await self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
                box = await self.page.Jeval('#lessonCards svg', 'el => ({width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height})')
                self.assertGreater(box['width'], 200)
                self.assertGreater(box['height'], 90)
                for selector in ('#lessonSubtitleBox', '#lessonSeek', '#lessonPlay'):
                    bottom = await self.page.Jeval(selector, 'el => el.getBoundingClientRect().bottom')
                    self.assertLessEqual(bottom, height, (problem_id, name, selector, bottom))
                self.assertTrue(await self.page.Jeval('#lessonAudio', 'el => el.paused'))
                await self.page.screenshot({'path': f'/tmp/motion-{problem_id}-{name}.png', 'fullPage': True})
        await self.page.reload()
        await self.ready()
        self.assertTrue(await self.page.Jeval('#lessonAudio', 'el => el.paused'))

    async def test_unavailable_animation_keeps_audio_and_subtitles_usable(self):
        self.server.motion_unavailable = True
        await self.page.reload()
        await self.page.waitForFunction("!document.querySelector('#lessonPlay').disabled && document.querySelector('#lessonAudio').readyState >= 1")
        self.assertEqual(len(await self.page.JJ('#lessonCards svg')), 0)
        self.assertGreater(len(await self.page.JJ('#lessonCards .lesson-card')), 0)
        self.assertTrue(await self.page.Jeval('#lessonStatus', 'el => Boolean(el.textContent.trim())'))
        await self.page.click('#lessonPlay')
        await self.page.waitForFunction('!document.querySelector("#lessonAudio").paused && document.querySelector("#lessonAudio").currentTime > 0.1')
        self.assertTrue(await self.page.Jeval('#lessonSubtitle', 'el => Boolean(el.textContent.trim())'))
        await self.page.click('#lessonPlay')
