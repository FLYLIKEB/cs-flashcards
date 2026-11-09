"""Exercise the authenticated interview mount without starting DB/background workers."""
import asyncio
import base64
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app as flashcard_app

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'applications' / 'class101-interview'
BASIC_AUTH = b'Basic ' + base64.b64encode(b'interview-test:secret-test')


class InterviewRemoteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = mock.patch.multiple(
            flashcard_app, PUBLIC_USERNAME='interview-test', PUBLIC_PASSWORD='secret-test'
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    async def request(self, path, *, headers=(), method='GET'):
        events = []
        request_sent = False

        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {'type': 'http.request', 'body': b'', 'more_body': False}
            await asyncio.Event().wait()

        async def send(event):
            events.append(event)

        await flashcard_app.app({
            'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'},
            'http_version': '1.1', 'method': method, 'scheme': 'https',
            'path': path, 'raw_path': path.encode(), 'root_path': '',
            'query_string': b'', 'headers': list(headers),
            'server': ('test.local', 443), 'client': ('127.0.0.1', 12345),
        }, receive, send)
        start = next(event for event in events if event['type'] == 'http.response.start')
        body = b''.join(event.get('body', b'') for event in events if event['type'] == 'http.response.body')
        return start['status'], dict(start['headers']), body

    async def test_index_and_assets_remain_authenticated(self):
        for path in ('/interview/', '/interview/audio/question-001.mp3', '/interview/answers.md'):
            with self.subTest(path=path):
                status, headers, _ = await self.request(path)
                self.assertEqual(status, 401)
                self.assertIn(b'Basic', headers[b'www-authenticate'])
        status, headers, body = await self.request('/interview/', headers=[(b'authorization', BASIC_AUTH)])
        self.assertEqual(status, 200)
        self.assertEqual(body, (SITE / 'index.html').read_bytes())
        self.assertIn(b'text/html', headers[b'content-type'])
        self.assertIn(b'HttpOnly', headers[b'set-cookie'])
        self.assertIn(b'Secure', headers[b'set-cookie'])

    async def test_cookie_auth_and_mobile_audio_range(self):
        _, headers, _ = await self.request('/interview/', headers=[(b'authorization', BASIC_AUTH)])
        cookie = headers[b'set-cookie'].split(b';', 1)[0]
        status, headers, body = await self.request('/interview/audio/answer-001.mp3', headers=[
            (b'cookie', cookie), (b'range', b'bytes=0-31'),
        ])
        audio = SITE / 'audio' / 'answer-001.mp3'
        self.assertEqual(status, 206)
        self.assertEqual(body, audio.read_bytes()[:32])
        self.assertEqual(headers[b'content-range'], f'bytes 0-31/{audio.stat().st_size}'.encode())
        self.assertEqual(headers[b'accept-ranges'], b'bytes')
        self.assertEqual(headers[b'content-type'], b'audio/mpeg')

    async def test_site_dependencies_are_served(self):
        for filename in ('interview.css', 'audio-player.js', 'reading-highlight.js', 'underline.js',
                         'focus-study.js', 'questions.md', 'answers.md', 'whiteboard.html',
                         'whiteboard.css', 'fonts/PretendardVariable.woff2', 'audio/manifest.json'):
            with self.subTest(filename=filename):
                status, _, body = await self.request('/interview/' + filename, headers=[(b'authorization', BASIC_AUTH)])
                self.assertEqual(status, 200)
                self.assertEqual(body, (SITE / filename).read_bytes())

    async def test_mount_does_not_expose_sibling_files_or_directory_listing(self):
        for path in ('/interview/../park_jiwoo_resume.md', '/interview/../../app.py',
                     '/interview/fonts/', '/interview/audio/'):
            with self.subTest(path=path):
                status, _, _ = await self.request(path, headers=[(b'authorization', BASIC_AUTH)])
                self.assertEqual(status, 404)


class InterviewPackagingTests(unittest.TestCase):
    def test_deploy_copies_only_required_site_assets(self):
        script = (ROOT / 'scripts/deploy_lightsail_flashcards.sh').read_text()
        match = re.search(r'^stage_interview_assets\(\) \{\n.*?^\}\n', script, re.M | re.S)
        self.assertIsNotNone(match)
        self.assertIn('stage_interview_assets "$ROOT_DIR/applications/class101-interview" "$TMP_STAGE/applications/class101-interview"', script)
        expected = {
            'index.html', 'interview.css', 'audio-player.js', 'underline.js', 'reading-highlight.js',
            'focus-study.js', 'questions.md', 'answers.md', 'whiteboard.html', 'whiteboard.css',
            'fonts/PretendardVariable.woff2', 'fonts/LICENSE.txt', 'audio/manifest.json',
        } | {f'audio/{kind}-{number:03d}.mp3' for kind in ('question', 'answer') for number in range(1, 101)}
        with tempfile.TemporaryDirectory() as tmp:
            source, stage = Path(tmp) / 'applications/class101-interview', Path(tmp) / 'stage'
            for name in expected | {'answers-01-30.md', 'render-tmp/frame.png', 'state/progress.sqlite'}:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture')
            (source.parent / 'park_jiwoo_resume.md').write_text('private resume')
            result = subprocess.run(
                ['bash', '-c', 'set -euo pipefail\n' + match.group(0) + '\nstage_interview_assets "$1" "$2"',
                 'interview-packaging-test', str(source), str(stage)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({str(path.relative_to(stage)) for path in stage.rglob('*') if path.is_file()}, expected)


if __name__ == '__main__':
    unittest.main()
