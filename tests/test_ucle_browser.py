"""Real browser checks for independent Ucle study state; no SQLite startup."""
import asyncio
import base64
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

from pyppeteer import launch
from tests.test_frontend_browser import browser_executable

ROOT = Path(__file__).resolve().parents[1]


class UcleBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        env = {**os.environ, 'CS_FLASHCARDS_PASSWORD': 'ucle-browser-test'}
        self.server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', str(port), '--lifespan', 'off'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop_server)
        for _ in range(100):
            try:
                await asyncio.to_thread(urlopen, self.url + '/ucle-interview/index.html', timeout=1)
                break
            except HTTPError as error:
                if error.code == 401:
                    error.close()
                    break
                raise
            except URLError:
                await asyncio.sleep(.1)
        else:
            self.fail('Local server did not start')
        options = {'headless': True, 'args': ['--no-sandbox'], 'handleSIGINT': False, 'handleSIGTERM': False, 'handleSIGHUP': False, 'autoClose': False}
        if browser_executable():
            options['executablePath'] = browser_executable()
        self.browser = await launch(**options)
        self.addAsyncCleanup(self.browser.close)
        self.page = await self.browser.newPage()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        token = base64.b64encode(b'cs:ucle-browser-test').decode()
        await self.page.setExtraHTTPHeaders({'Authorization': 'Basic ' + token})
        await self.page.goto(self.url + '/ucle-interview/index.html')
        await self.page.waitForSelector('#controls:not([hidden])')

    def stop_server(self):
        self.server.terminate()
        try:
            self.server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.server.kill()
            self.server.wait()

    async def test_reveal_review_break_reload_filters_and_mobile(self):
        page = self.page
        self.assertEqual(await page.evaluate('document.querySelectorAll(".card:not([hidden])").length'), 1)
        self.assertEqual(await page.evaluate('document.querySelectorAll(".card:not([hidden]) [data-step]:not([hidden])").length'), 0)
        await page.click('#reveal')
        await page.click('#reveal')
        self.assertGreater(await page.evaluate('document.querySelectorAll("#question-1 .spoken strong").length'), 0)
        await page.click('#review')
        await page.click('#done')
        await page.click('#pause')
        await page.reload()
        self.assertFalse(await page.evaluate('document.querySelector("#break-panel").hidden'))
        self.assertTrue(await page.evaluate('document.querySelector("#workspace").hidden'))
        await page.click('#resume')
        self.assertEqual(await page.Jeval('#done', 'el => el.getAttribute("aria-pressed")'), 'true')
        self.assertFalse(await page.Jeval('#question-1 [data-step="2"]', 'el => el.hidden'))
        await page.click('#next')
        self.assertEqual(await page.evaluate('document.querySelectorAll(".card:not([hidden]) [data-step]:not([hidden])").length'), 0)
        for _ in range(4):
            await page.click('#done')
            await page.click('#next')
        self.assertFalse(await page.Jeval('#checkpoint', 'el => el.hidden'))
        await page.click('#more')
        self.assertTrue(await page.Jeval('#checkpoint', 'el => el.hidden'))
        await page.click('#library summary')
        await page.select('#mode', 'review')
        self.assertIn('1 / 1문항', await page.Jeval('#position', 'el => el.textContent'))
        await page.click('#review')
        self.assertFalse(await page.Jeval('#empty', 'el => el.hidden'))
        await page.select('#mode', 'essential')
        self.assertEqual(await page.evaluate('document.querySelectorAll("#picker option").length'), 15)
        await page.select('#mode', 'all')
        await page.select('#category', '9')
        self.assertEqual(await page.evaluate('document.querySelectorAll("#picker option").length'), 10)
        await page.select('#category', 'all')
        await page.type('#search', '존재하지않는검색어')
        self.assertFalse(await page.Jeval('#empty', 'el => el.hidden'))
        await page.evaluate('document.querySelector("#search").value = ""; document.querySelector("#search").dispatchEvent(new Event("input"))')
        await page.select('#picker', '200')
        self.assertTrue(await page.Jeval('#next', 'el => el.disabled'))
        for _ in range(3):
            await page.click('#reveal')
        for width in (390, 1440):
            await page.setViewport({'width': width, 'height': 844})
            self.assertTrue(await page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        await page.setViewport({'width': 390, 'height': 844})
        await page.screenshot({'path': '/tmp/ucle-mobile.png', 'fullPage': True})
        self.assertEqual(self.errors, [])

    async def test_priority_category_filters_and_playing_next_continue(self):
        page = self.page
        for category in range(1, 10):
            await page.select('#category', str(category))
            for priority in range(1, 4):
                await page.select('#priority', str(priority))
                self.assertGreater(await page.evaluate('UcleStudy.snapshot().ids.length'), 0)
                self.assertTrue(await page.evaluate("""() => UcleStudy.snapshot().ids.every(id => {
                    const card = document.getElementById(`question-${id}`);
                    return card.dataset.category === document.querySelector('#category').value
                        && card.dataset.priority === document.querySelector('#priority').value;
                })"""))
        await page.select('#category', '1')
        await page.select('#priority', '1')
        selected = await page.evaluate('UcleStudy.snapshot().ids')
        current = await page.evaluate('UcleStudy.snapshot().current')
        next_id = selected[selected.index(current) + 1]
        await page.click('#voice-auto')
        await page.click('#voice-play')
        await page.waitForFunction('document.querySelector("#voice-audio").currentTime > 0')
        await page.click('#next')
        await page.waitForFunction('(id) => UcleStudy.snapshot().current === id && !document.querySelector("#voice-audio").paused && document.querySelector("#voice-audio").currentTime > 0', {}, next_id)
        self.assertIn(f'question-{next_id:03}.mp3', await page.Jeval('#voice-audio', 'el => el.currentSrc'))
        await page.click('#voice-play')
        await page.click('#next')
        self.assertTrue(await page.Jeval('#voice-audio', 'el => el.paused'))
        await page.click('#voice-play')
        await page.waitForFunction('document.querySelector("#voice-audio").currentTime > 0')
        await page.select('#priority', '2')
        self.assertTrue(await page.Jeval('#voice-audio', 'el => el.paused'))
        await page.reload()
        self.assertEqual(await page.Jeval('#priority', 'el => el.value'), '2')
        self.assertEqual(await page.Jeval('#category', 'el => el.value'), '1')
        self.assertTrue(await page.Jeval('#voice-audio', 'el => el.paused'))
        self.assertEqual(self.errors, [])

    async def test_real_audio_progress_seek_autonext_break_and_reload(self):
        page = self.page
        self.assertTrue(await page.Jeval('#voice-audio', 'el => el.paused'))
        await page.click('#voice-play')
        await page.waitForFunction('document.querySelector("#voice-audio").currentTime > 0', timeout=15000)
        await page.waitForFunction('Number.isFinite(document.querySelector("#voice-audio").duration)')
        await page.click('#voice-play')
        self.assertTrue(await page.Jeval('#voice-audio', 'el => el.paused'))
        await page.select('#voice-rate', '1.5')
        self.assertEqual(await page.Jeval('#voice-audio', 'el => el.playbackRate'), 1.5)
        await page.click('#voice-play')
        await page.evaluate("""async () => {
            const data = await (await fetch('audio/manifest.json')).json();
            const section = data.tracks.find(track => track.id === 1).sections.find(section => section.step === 3);
            document.querySelector('#voice-audio').currentTime = section.start + 0.1;
        }""")
        await page.waitForFunction("document.getElementById('question-1').querySelectorAll('[data-step]')[2].hidden === false")
        await page.Jeval('#voice-audio', 'el => { el.currentTime = el.duration - 0.15; }')
        await page.waitForFunction('!document.querySelector("#question-2").hidden', timeout=15000)
        await page.waitForFunction('document.querySelector("#voice-audio").currentTime > 0')
        self.assertEqual(await page.evaluate('JSON.parse(localStorage.getItem("ucle-interview-study-v1")).done.length'), 0)
        await page.click('#pause')
        self.assertTrue(await page.Jeval('#voice-audio', 'el => el.paused'))
        await page.click('#resume')
        self.assertTrue(await page.Jeval('#voice-audio', 'el => el.paused'))
        await page.click('#library summary')
        await page.select('#picker', '200')
        await page.click('#voice-play')
        await page.waitForFunction('document.querySelector("#voice-audio").currentTime > 0')
        await page.Jeval('#voice-audio', 'el => { el.currentTime = el.duration - 0.15; }')
        await page.waitForFunction('document.querySelector("#voice-audio").ended', timeout=15000)
        self.assertFalse(await page.Jeval('#question-200', 'el => el.hidden'))
        await page.reload()
        self.assertTrue(await page.Jeval('#voice-audio', 'el => el.paused'))
        self.assertEqual(await page.Jeval('#voice-rate', 'el => el.value'), '1.5')
        self.assertEqual(self.errors, [])

    async def test_stack_basics_is_separate_readable_page_on_mobile(self):
        page = self.page
        await page.click('header a[href="stack-basics.html"]')
        await page.waitForSelector('details')
        self.assertGreaterEqual(await page.evaluate('document.querySelectorAll("details").length'), 24)
        self.assertGreater(await page.evaluate("() => Array.from(document.links).filter(a => a.href.startsWith('https://')).length"), 10)
        await page.setJavaScriptEnabled(False)
        await page.reload()
        await page.click('details summary')
        self.assertTrue(await page.Jeval('details', 'el => el.open'))
        for width in (390, 1440):
            await page.setViewport({'width': width, 'height': 844})
            self.assertTrue(await page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.assertEqual(self.errors, [])

    async def test_compact_overview_and_collapsing_audio_keeps_playing(self):
        page = self.page
        await page.setViewport({'width': 1440, 'height': 900})
        self.assertEqual(await page.Jeval('#question-map', 'el => el.children.length'), 200)
        self.assertEqual(await page.Jeval('#question-list', 'el => el.children.length'), 200)
        self.assertLess(await page.Jeval('#question-map', 'el => el.getBoundingClientRect().bottom'), 900)
        await page.click('#voice-play')
        await page.waitForFunction('!document.querySelector("#voice-audio").paused')
        await page.click('#voice-details summary')
        self.assertFalse(await page.Jeval('#voice-details', 'el => el.open'))
        self.assertFalse(await page.Jeval('#voice-audio', 'el => el.paused'))
        await page.click('#question-map button:nth-child(200)')
        await page.waitForFunction('document.querySelector("#voice-audio").currentSrc.includes("question-200.mp3") && !document.querySelector("#voice-audio").paused')
        self.assertEqual(await page.Jeval('#question-map button:nth-child(200)', 'el => el.getAttribute("aria-current")'), 'true')
        await page.screenshot({'path': '/tmp/ucle-compact-desktop.png'})
        await page.setViewport({'width': 390, 'height': 844})
        self.assertFalse(await page.evaluate('document.documentElement.scrollWidth > innerWidth'))
        self.assertLess(await page.Jeval('#question-map', 'el => el.getBoundingClientRect().height'), 300)
        await page.screenshot({'path': '/tmp/ucle-compact-mobile.png'})
        self.assertFalse(self.errors)

    async def test_no_javascript_fallback(self):
        await self.page.setJavaScriptEnabled(False)
        await self.page.reload()
        self.assertEqual(await self.page.evaluate('document.querySelectorAll(".card:not([hidden])").length'), 200)
        self.assertIn('한 줄 핵심', await self.page.Jeval('#question-1', 'el => el.textContent'))

    async def test_storage_failure_stays_usable(self):
        await self.page.evaluateOnNewDocument('''() => { Object.defineProperty(window, 'localStorage', {get() {throw new Error('blocked');}}); }''')
        await self.page.reload()
        self.assertIn('저장할 수 없어요', await self.page.Jeval('#saved', 'el => el.textContent'))
        await self.page.click('#next')
        self.assertFalse(await self.page.Jeval('#question-2', 'el => el.hidden'))
        self.assertEqual(self.errors, [])
