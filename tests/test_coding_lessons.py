"""Real audio assets and native browser playback for the slide-based Java lessons."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import re
import subprocess
import threading
import unittest

from pyppeteer import launch
from tests.test_coding_practice import ROOT, KEY, QuietHandler


class LessonMediaTests(unittest.TestCase):
    def test_storyboards_and_every_audio_clip_are_complete_and_audible(self):
        lessons = json.loads((ROOT / 'static/coding-lessons.json').read_text())
        manifest = json.loads((ROOT / 'static/coding-audio/manifest.json').read_text())
        self.assertEqual([lesson['id'] for lesson in lessons], list(range(1, 31)))
        audio_lessons = {lesson['id']: lesson for lesson in manifest['lessons']}
        self.assertEqual(set(audio_lessons), set(range(1, 31)))
        paths = []
        for lesson in lessons:
            with self.subTest(problem=lesson['id']):
                scenes = lesson['scenes']
                audio = audio_lessons[lesson['id']]['scenes']
                self.assertEqual(len(scenes), 5)
                self.assertEqual(len(audio), len(scenes))
                for scene, clip in zip(scenes, audio):
                    self.assertTrue(scene['title'])
                    self.assertTrue(scene['caption'])
                    self.assertTrue(scene['narration'])
                    self.assertGreaterEqual(len(scene['items']), 1)
                    self.assertLessEqual(len(scene['items']), 5)
                    self.assertIn(scene['active'], range(len(scene['items'])))
                    self.assertGreater(clip['duration'], 1)
                    path = (ROOT / clip['src'].lstrip('/')).resolve()
                    self.assertTrue(path.is_relative_to(ROOT / 'static/coding-audio'))
                    self.assertTrue(path.is_file(), str(path))
                    paths.append((path, clip['duration']))

        def inspect(item):
            path, expected = item
            probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
                check=True, capture_output=True, text=True, timeout=15,
            )
            metadata = json.loads(probe.stdout)
            audio = [stream for stream in metadata['streams'] if stream['codec_type'] == 'audio']
            if len(audio) != 1 or len(metadata['streams']) != 1:
                raise AssertionError(f'{path}: expected audio-only asset')
            duration = float(metadata['format']['duration'])
            if duration <= 1 or abs(duration - expected) > 0.5:
                raise AssertionError(f'{path}: duration {duration} != {expected}')
            volume = subprocess.run(
                ['ffmpeg', '-hide_banner', '-i', str(path), '-af', 'volumedetect', '-f', 'null', '-'],
                capture_output=True, text=True, timeout=20,
            )
            if volume.returncode:
                raise AssertionError(volume.stderr)
            match = re.search(r'mean_volume: (-?\d+(?:\.\d+)?) dB', volume.stderr)
            if not match or float(match.group(1)) < -65:
                raise AssertionError(f'{path}: silent or nearly silent audio')
            return duration

        with ThreadPoolExecutor(max_workers=4) as pool:
            durations = list(pool.map(inspect, paths))
        self.assertEqual(len(durations), 150)
        self.assertGreater(sum(durations), 150)


class LessonHandler(QuietHandler):
    def do_GET(self):
        override = getattr(self.server, 'manifest_override', None)
        if self.path.split('?')[0] == '/static/coding-audio/manifest.json' and override is not None:
            status, payload = override
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


class LessonBrowserTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(LessonHandler, directory=str(ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/static/coding.html'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    async def asyncSetUp(self):
        self.server.manifest_override = None
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
        await self.page.waitForFunction("document.querySelector('#lessonSceneTitle').textContent.trim().length > 0")
        await self.page.waitForFunction("!document.querySelector('#lessonPlay').disabled && document.querySelector('#lessonAudio').getAttribute('src') && document.querySelector('#lessonAudio').readyState >= 1")

    async def state(self):
        return await self.page.evaluate('(key) => JSON.parse(localStorage.getItem(key))', KEY)

    async def audio_state(self):
        return await self.page.Jeval('#lessonAudio', '''el => ({paused: el.paused, time: el.currentTime,
            muted: el.muted, volume: el.volume, src: el.currentSrc, rate: el.playbackRate})''')

    async def start_audio(self):
        await self.page.click('#lessonPlay')
        await self.page.waitForFunction("!document.querySelector('#lessonAudio').paused && document.querySelector('#lessonAudio').currentTime > 0.2")

    async def test_default_slides_real_sound_pause_rate_and_mobile(self):
        self.assertFalse(await self.page.Jeval('#lessonPanel', 'el => el.hidden'))
        self.assertTrue(await self.page.Jeval('#practicePanel', 'el => el.hidden'))
        self.assertTrue((await self.audio_state())['paused'])
        await self.start_audio()
        playing = await self.audio_state()
        self.assertFalse(playing['muted'])
        self.assertGreater(playing['volume'], 0)
        self.assertTrue(playing['src'].endswith('.mp3'), playing['src'])
        self.assertTrue((await self.state())['records']['1']['lessonAssisted'])
        await self.page.click('#lessonPlay')
        paused = await self.audio_state()
        self.assertTrue(paused['paused'])
        await asyncio.sleep(0.25)
        self.assertAlmostEqual((await self.audio_state())['time'], paused['time'], delta=0.08)
        options = await self.page.JJeval('#lessonRate option', 'els => els.map(el => el.value)')
        rate = '1.5' if '1.5' in options else options[-1]
        await self.page.select('#lessonRate', rate)
        self.assertAlmostEqual((await self.audio_state())['rate'], float(rate))
        await self.page.setViewport({'width': 1440, 'height': 1000})
        await self.page.screenshot({'path': '/tmp/coding48-lessons-desktop.png', 'fullPage': True})
        await self.page.setViewport({'width': 390, 'height': 844})
        self.assertTrue(await self.page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        await self.page.screenshot({'path': '/tmp/coding48-lessons-mobile.png', 'fullPage': True})

    async def test_rapid_play_pause_does_not_restart_from_stale_play_promise(self):
        await self.start_audio()
        await self.page.click('#lessonPlay')
        # Queue both button handlers before the genuine audio.play promise settles.
        await self.page.Jeval('#lessonPlay', 'button => { button.click(); button.click(); }')
        await asyncio.sleep(0.2)
        self.assertTrue((await self.audio_state())['paused'])
        self.assertIn('재생', await self.page.Jeval('#lessonPlay', 'el => el.textContent'))

    async def test_navigation_remembers_scene_and_mode_switch_stops_audio(self):
        first_source = await self.page.Jeval('#lessonAudio', 'el => el.src')
        await self.page.click('#lessonNext')
        self.assertEqual((await self.state())['records']['1']['lessonScene'], 1)
        self.assertNotEqual(await self.page.Jeval('#lessonAudio', 'el => el.src'), first_source)
        await self.page.reload()
        await self.ready()
        self.assertEqual((await self.state())['records']['1']['lessonScene'], 1)
        self.assertTrue((await self.audio_state())['paused'])
        await self.start_audio()
        await self.page.click('#modePractice')
        self.assertTrue((await self.audio_state())['paused'])
        self.assertFalse(await self.page.Jeval('#practicePanel', 'el => el.hidden'))
        await self.page.click('#modeLesson')
        self.assertTrue((await self.audio_state())['paused'])
        await self.page.click('#lessonPrev')
        self.assertEqual((await self.state())['records']['1']['lessonScene'], 0)
        await self.start_audio()
        await self.page.click('#curriculum > summary')
        await self.page.click('#problems button:nth-child(2)')
        await self.page.waitForFunction("document.querySelector('#title').textContent.startsWith('02.')")
        self.assertTrue((await self.audio_state())['paused'])
        self.assertNotEqual(await self.page.Jeval('#lessonAudio', 'el => el.src'), first_source)

    async def test_auto_advance_uses_audio_end_and_can_be_disabled(self):
        if not await self.page.Jeval('#lessonAuto', 'el => el.checked'):
            await self.page.click('#lessonAuto')
        await self.start_audio()
        await self.page.waitForFunction("Number.isFinite(document.querySelector('#lessonAudio').duration)")
        await self.page.Jeval('#lessonAudio', 'el => { el.playbackRate = 8; el.currentTime = el.duration - 0.15; }')
        await self.page.waitForFunction("JSON.parse(localStorage.getItem('csCoding48:java:v1')).records['1'].lessonScene === 1")
        await self.page.waitForFunction("!document.querySelector('#lessonAudio').paused && document.querySelector('#lessonAudio').currentTime > 0.1")
        await self.page.click('#lessonAuto')
        await self.page.Jeval('#lessonAudio', 'el => { el.playbackRate = 8; el.currentTime = el.duration - 0.15; }')
        await self.page.waitForFunction("document.querySelector('#lessonAudio').ended")
        self.assertEqual((await self.state())['records']['1']['lessonScene'], 1)
        await self.page.click('#lessonRepeat')
        await self.page.waitForFunction("!document.querySelector('#lessonAudio').paused && document.querySelector('#lessonAudio').currentTime < 2")

    async def test_watched_requires_every_scene_not_just_skipping_to_last(self):
        if await self.page.Jeval('#lessonAuto', 'el => el.checked'):
            await self.page.click('#lessonAuto')
        for _ in range(4):
            await self.page.click('#lessonNext')
        await self.start_audio()
        await self.page.Jeval('#lessonAudio', 'el => { el.playbackRate = 8; el.currentTime = el.duration - 0.15; }')
        await self.page.waitForFunction("document.querySelector('#lessonAudio').ended")
        self.assertFalse((await self.state())['records']['1'].get('lessonWatched', False))
        self.assertIn(4, (await self.state())['records']['1']['lessonHeard'])
        for _ in range(4):
            await self.page.click('#lessonPrev')
        for index in range(4):
            await self.start_audio()
            await self.page.Jeval('#lessonAudio', 'el => { el.playbackRate = 8; el.currentTime = el.duration - 0.15; }')
            await self.page.waitForFunction("document.querySelector('#lessonAudio').ended")
            if index < 3:
                await self.page.click('#lessonNext')
        self.assertTrue((await self.state())['records']['1']['lessonWatched'])
        self.assertNotEqual((await self.state())['records']['1']['status'], 'solved')
        await self.page.click('#lessonNext')
        await self.start_audio()
        await self.page.Jeval('#lessonAudio', 'el => { el.playbackRate = 8; el.currentTime = el.duration - 0.15; }')
        await self.page.waitForFunction("!document.querySelector('#lessonNextProblem').hidden")
        await self.page.click('#lessonNextProblem')
        await self.page.waitForFunction("document.querySelector('#title').textContent.startsWith('02.')")
        await self.page.waitForFunction("!document.querySelector('#lessonAudio').paused && document.querySelector('#lessonAudio').currentTime > 0.2")

    async def test_missing_manifest_and_partial_lesson_show_preparing_without_stale_audio(self):
        manifest = json.loads((ROOT / 'static/coding-audio/manifest.json').read_text())
        self.server.manifest_override = (404, {})
        await self.page.setCacheEnabled(False)
        await self.page.reload()
        await self.page.waitForFunction("document.querySelector('#lessonStatus').textContent.includes('생성 중')")
        self.assertFalse(await self.page.Jeval('#lessonAudio', 'el => Boolean(el.getAttribute("src"))'))
        self.assertTrue(await self.page.Jeval('#lessonNext', 'el => el.disabled'))
        self.assertNotIn('실패', await self.page.Jeval('#lessonStatus', 'el => el.textContent'))
        self.server.manifest_override = (200, {**manifest, 'lessons': [item for item in manifest['lessons'] if item['id'] == 1]})
        await self.page.reload()
        await self.ready()
        await self.start_audio()
        await self.page.click('#curriculum > summary')
        await self.page.click('#problems button:nth-child(2)')
        await self.page.waitForFunction("document.querySelector('#lessonStatus').textContent.includes('생성 중')")
        self.assertTrue((await self.audio_state())['paused'])
        self.assertFalse(await self.page.Jeval('#lessonAudio', 'el => Boolean(el.getAttribute("src"))'))
        self.assertTrue(await self.page.Jeval('#lessonRepeat', 'el => el.disabled'))

    async def test_audio_error_does_not_silently_advance(self):
        await self.start_audio()
        scene = (await self.state())['records']['1'].get('lessonScene', 0)
        await self.page.Jeval('#lessonAudio', "el => { el.src = '/static/no-such-lesson-audio.mp3'; el.load(); }")
        await self.page.waitForFunction("document.querySelector('#lessonAudio').error !== null")
        await self.page.waitForFunction("/실패|오류|못|불러/.test(document.querySelector('#lessonStatus').textContent)")
        self.assertEqual((await self.state())['records']['1'].get('lessonScene', 0), scene)
        self.assertTrue((await self.audio_state())['paused'])

    async def test_lesson_help_is_not_independent_completion(self):
        await self.page.click('#lessonNext')
        self.assertTrue((await self.state())['records']['1']['lessonAssisted'])
        await self.page.click('#modePractice')
        await self.page.click('[data-step="2"]')
        for checkbox in await self.page.JJ('#checks input'):
            await checkbox.click()
        await self.page.click('[data-verdict="solved"]')
        self.assertNotEqual((await self.state())['records']['1']['status'], 'solved')
        await self.page.click('#restart')
        self.assertFalse((await self.state())['records']['1'].get('lessonAssisted', False))


if __name__ == '__main__':
    unittest.main()
