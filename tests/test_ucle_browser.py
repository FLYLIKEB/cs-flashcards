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
