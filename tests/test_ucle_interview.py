"""Ucle source/build and authenticated delivery contracts; no live DB writes."""
import contextlib
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from scripts import build_ucle_interview as builder
from tests import test_interview_remote as remote_helpers

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'applications' / 'ucle-interview'
ANSWER_FILES = ('answers-001-070.json', 'answers-071-140.json', 'answers-141-200.json')


class UcleContentTests(unittest.TestCase):
    def test_original_questions_keep_ids_and_nine_category_boundaries(self):
        questions = builder.load_questions()
        self.assertEqual([q['id'] for q in questions], list(range(1, 201)))
        self.assertEqual(Counter(q['category'] for q in questions),
                         {1: 20, 2: 30, 3: 35, 4: 25, 5: 25, 6: 20, 7: 20, 8: 15, 9: 10})
        self.assertIn('우리 회사를 알게 된 경로', questions[0]['question'])
        self.assertIn('1년 뒤', questions[-1]['question'])

    def test_inline_emphasis_escapes_html_including_bold_content(self):
        rendered = builder.bold('안녕 **<img src=x onerror="alert(1)">** & <script>bad</script>')
        self.assertIn('<strong>&lt;img', rendered)
        self.assertIn('&lt;script&gt;bad&lt;/script&gt;', rendered)
        self.assertNotIn('<img', rendered)
        self.assertNotIn('<script>', rendered)
        self.assertEqual(rendered.count('<strong>'), 1)

    def test_authored_answers_cover_every_question_with_short_emphasized_sections(self):
        answers = [answer for filename in ANSWER_FILES for answer in json.loads((SITE / filename).read_text())]
        self.assertEqual([a['id'] for a in answers], list(range(1, 201)))
        for answer in answers:
            with self.subTest(id=answer['id']):
                self.assertEqual(len(answer['keywords']), 3)
                self.assertEqual(len(set(answer['keywords'])), 3)
                self.assertTrue(all(isinstance(k, str) and k.strip() for k in answer['keywords']))
                self.assertIn(len(answer['answer']), (3, 4, 5))
                for text in [answer['summary'], answer['explanation'], *answer['answer']]:
                    self.assertRegex(text, r'\*\*[^*]+\*\*')
                    self.assertEqual(text.count('**') % 2, 0, 'unbalanced bold markers')

    def test_generation_is_reproducible_and_readable_without_javascript(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            for filename in ('source.md', 'template.html', *ANSWER_FILES):
                shutil.copyfile(SITE / filename, target / filename)
            with mock.patch.object(builder, 'SITE', target), contextlib.redirect_stdout(io.StringIO()):
                builder.build()
            for filename in ('index.html', 'answers.md'):
                self.assertEqual((target / filename).read_bytes(), (SITE / filename).read_bytes(),
                                 f'Rebuild required for {filename}')
            html = (target / 'index.html').read_text()
            self.assertEqual(re.findall(r'<article class="card" id="question-(\d+)"', html),
                             [str(i) for i in range(1, 201)])
            self.assertEqual(html.count('data-step="1"'), 200)
            self.assertEqual(html.count('data-step="2"'), 200)
            self.assertEqual(html.count('data-step="3"'), 200)
            self.assertNotRegex(html, r'<article[^>]*\bhidden\b')
            self.assertNotRegex(html, r'data-step="[123]"[^>]*\bhidden\b')
            self.assertNotIn('@@CARDS@@', html)
            self.assertEqual(html.count('<h3>이렇게 물어보세요</h3>'), 10)

    def test_rejects_missing_original_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            source = (SITE / 'source.md').read_text()
            source = re.sub(r'^\*\*200\.\*\*.*$', '', source, flags=re.M)
            (target / 'source.md').write_text(source)
            with mock.patch.object(builder, 'SITE', target), self.assertRaisesRegex(ValueError, 'exactly'):
                builder.load_questions()

    def test_deployment_stages_only_required_assets(self):
        script = (ROOT / 'scripts/deploy_lightsail_flashcards.sh').read_text()
        block = re.search(r'^mkdir -p "\$TMP_STAGE/applications/ucle-interview"\nfor asset .*?\ndone$',
                          script, flags=re.M | re.S)
        self.assertIsNotNone(block)
        expected = {'index.html', 'study.css', 'study.js', 'source.md', 'answers.md'}
        with tempfile.TemporaryDirectory() as tmp:
            root, stage = Path(tmp) / 'root', Path(tmp) / 'stage'
            source = root / 'applications' / 'ucle-interview'
            source.mkdir(parents=True)
            for filename in expected | {'template.html', 'answers-001-070.json', 'progress.sqlite'}:
                (source / filename).write_text('fixture')
            result = subprocess.run(['bash', '-c', 'set -euo pipefail\nROOT_DIR="$1"\nTMP_STAGE="$2"\n' + block[0],
                                     'ucle-packaging-test', str(root), str(stage)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            staged = stage / 'applications' / 'ucle-interview'
            self.assertEqual({p.name for p in staged.iterdir()}, expected)

    def test_home_has_new_menu(self):
        self.assertIn('href="/ucle-interview/"', (ROOT / 'static/index.html').read_text())


class UcleAuthTests(unittest.IsolatedAsyncioTestCase):
    # Reuse only the ASGI fixture, not the other site's test methods.
    setUp = remote_helpers.InterviewRemoteTests.setUp
    request = remote_helpers.InterviewRemoteTests.request

    async def test_page_and_content_require_existing_authentication(self):
        for filename in ('', 'study.js', 'study.css', 'source.md', 'answers.md'):
            with self.subTest(filename=filename):
                status, headers, _ = await self.request('/ucle-interview/' + filename)
                self.assertEqual(status, 401)
                self.assertIn(b'Basic', headers[b'www-authenticate'])
                status, _, body = await self.request('/ucle-interview/' + filename,
                                                     headers=[(b'authorization', remote_helpers.BASIC_AUTH)])
                self.assertEqual(status, 200)
                self.assertEqual(body, (SITE / (filename or 'index.html')).read_bytes())

    async def test_cookie_authentication_and_mount_boundaries(self):
        _, headers, _ = await self.request('/ucle-interview/',
                                           headers=[(b'authorization', remote_helpers.BASIC_AUTH)])
        cookie = headers[b'set-cookie'].split(b';', 1)[0]
        status, _, _ = await self.request('/ucle-interview/study.js', headers=[(b'cookie', cookie)])
        self.assertEqual(status, 200)
        for path in ('/ucle-interview/../park_jiwoo_resume.md', '/ucle-interview/../../state/progress.sqlite'):
            with self.subTest(path=path):
                status, _, _ = await self.request(path, headers=[(b'cookie', cookie)])
                self.assertEqual(status, 404)


if __name__ == '__main__':
    unittest.main()
