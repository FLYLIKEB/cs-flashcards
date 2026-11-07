"""Literal learning subtitles and natural spoken readings stay paired."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import render_coding_lesson_audio as renderer
from scripts import import_coding_ai_audio as importer

ROOT = Path(__file__).resolve().parents[1]


class NarrationAuthoringTests(unittest.TestCase):
    def test_all_scenes_have_explicit_matching_display_and_speech(self):
        lessons = json.loads((ROOT / 'static/coding-lessons.json').read_text())
        manifest = {item['id']: item for item in json.loads(
            (ROOT / 'static/coding-audio/manifest.json').read_text())['lessons']}
        total = 0
        for lesson in lessons:
            entry = manifest[lesson['id']]
            expected_hash = (importer.fingerprint(lesson, entry['scenes'])
                             if entry.get('sourceHashKind') == 'ai-import-v1' else renderer.fingerprint(lesson))
            self.assertEqual(entry['sourceHash'], expected_hash)
            for index, scene in enumerate(lesson['scenes']):
                with self.subTest(lesson=lesson['id'], scene=index):
                    self.assertIn('segments', scene)
                    segments = renderer.narration_segments(scene)
                    self.assertEqual([part['text'] for part in segments],
                                     [cue['text'] for cue in manifest[lesson['id']]['scenes'][index]['cues']])
                    self.assertTrue(all(len(part['text']) <= 100 for part in segments))
                    total += len(segments)
        intro_count = sum(scene.get('introCueCount', 0) for lesson in lessons for scene in lesson['scenes'])
        self.assertEqual(total - intro_count, 620, 'Original explanations must remain intact')

    def test_example_tokens_are_literal_in_subtitles(self):
        lessons = {item['id']: item for item in json.loads((ROOT / 'static/coding-lessons.json').read_text())}
        requests = lessons[1]['scenes'][0]['narration']
        for token in ('b', 'a', 'c'):
            self.assertIn(token, requests)
        for spoken in ('에이', '비,', '씨,'):
            self.assertNotIn(spoken, requests)
        payments = lessons[2]['scenes'][0]['narration']
        for token in ('4', '2', '6', '8'):
            self.assertIn(token, payments)
        self.assertIn('putIfAbsent', lessons[2]['scenes'][3]['narration'])
        self.assertIn('LinkedHashMap', lessons[26]['scenes'][3]['narration'])

    def test_renderer_speaks_reading_but_emits_literal_subtitle(self):
        scene = {'narration': 'b를 확인해요. 4를 더해요.', 'segments': [
            {'text': 'b를 확인해요.', 'speech': '비를 확인해요.'},
            {'text': '4를 더해요.', 'speech': '사를 더해요.'}]}
        spoken = []
        def fake_run(args, **kwargs):
            if args[0] == 'say':
                spoken.append(Path(args[args.index('-f') + 1]).read_text())
        with patch.object(renderer, 'run', side_effect=fake_run), \
             patch.object(renderer, 'pcm_duration', return_value=1.5), \
             patch.object(renderer, 'verify', return_value=3.25), \
             patch.object(renderer, 'audible'), patch.object(renderer.shutil, 'move'):
            result = renderer.render({'id': 1, 'scenes': [scene]}, None, True)
        self.assertEqual(spoken, ['비를 확인해요.', '사를 더해요.'])
        self.assertEqual(result['scenes'][0]['cues'], [
            {'start': 0, 'end': 1.5, 'text': 'b를 확인해요.'},
            {'start': 1.5, 'end': 3.25, 'text': '4를 더해요.'}])

    def test_mismatched_or_missing_readings_fail_before_synthesis(self):
        for scene in (
            {'narration': 'b', 'segments': [{'text': 'a', 'speech': '에이'}]},
            {'narration': 'b', 'segments': [{'text': 'b', 'speech': ''}]},
            {'narration': 'b', 'segments': []},
        ):
            with self.subTest(scene=scene), self.assertRaises(ValueError):
                renderer.narration_segments(scene)
        self.assertEqual(renderer.narration_segments({'narration': '기존 설명입니다.'}),
                         [{'text': '기존 설명입니다.', 'speech': '기존 설명입니다.'}])
