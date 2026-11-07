"""Problem intros preserve existing media timing, five-scene progress and cue mappings."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import prepend_coding_intros as intros


class IntroAudioTests(unittest.TestCase):
    def setUp(self):
        self.parts = [{'text': 'ID 2개를 받아요.', 'speech': '아이디 두 개를 받아요.'},
                      {'text': '먼저 온 ID를 골라요.', 'speech': '먼저 온 아이디를 골라요.'}]
        self.scene = {'segments': [{'text': 'b를 확인해요.', 'speech': '비를 확인해요.'},
                                   {'text': 'a는 다음이에요.', 'speech': '에이는 다음이에요.'}],
                      'narration': 'b를 확인해요. a는 다음이에요.', 'title': '기존 장면'}
        self.lesson = {'id': 1, 'scenes': [deepcopy(self.scene) for _ in range(5)]}
        self.clip = {'src': '/static/coding-audio/old.mp3', 'duration': 5.0,
                     'cues': [{'start': 0, 'end': 2, 'text': 'b를 확인해요.'},
                              {'start': 2, 'end': 5, 'text': 'a는 다음이에요.'}],
                     'provenance': {'provider': 'clova', 'voice': '아라'}}
        self.track = {'id': 1, 'scenes': [deepcopy(self.clip) for _ in range(5)]}
        self.story = {'scenes': [{'frames': [{'cue': 0, 'nodes': [{'id': 'b'}]},
                                            {'cue': 1, 'nodes': [{'id': 'a'}]}]} for _ in range(5)]}
        self.links = {'scenes': [{'cues': [{'lines': [2], 'note': '입력'}, {'lines': [4], 'note': '다음'}]}
                                  for _ in range(5)]}

    def test_prepend_shifts_audio_and_visuals_without_changing_body_or_other_scenes(self):
        snapshots = [deepcopy(item) for item in (self.lesson, self.track, self.story, self.links)]
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / 'intro.mp3'
            audio.write_bytes(b'validated audio')
            with patch.object(intros.renderer, 'verify', return_value=8.0):
                intros.prepend_data(self.lesson, self.track, self.story, self.links, self.parts, [1.25, 1.75], audio)
        for item, before in zip((self.lesson, self.track, self.story, self.links), snapshots):
            self.assertEqual(item['scenes'][1:], before['scenes'][1:])
            self.assertEqual(len(item['scenes']), 5)
        first, clip = self.lesson['scenes'][0], self.track['scenes'][0]
        self.assertEqual(first['segments'][2:], self.scene['segments'])
        self.assertEqual(first['introCueCount'], 2)
        self.assertEqual([(c['start'], c['end']) for c in clip['cues']], [(0, 1.25), (1.25, 3), (3, 5), (5, 8)])
        self.assertEqual([c['text'] for c in clip['cues']], [s['text'] for s in first['segments']])
        self.assertEqual([f['cue'] for f in self.story['scenes'][0]['frames']], [0, 1, 2, 3])
        self.assertEqual(self.links['scenes'][0]['cues'][2:], snapshots[3]['scenes'][0]['cues'])
        self.assertEqual(clip['provenance']['provider'], 'clova')
        self.assertEqual(clip['provenance']['introVoice'], 'Yuna')
        self.assertEqual(clip['provenance']['explanationSrc'], self.clip['src'])
        self.assertEqual(clip['provenance']['audioHash'], hashlib.sha256(b'validated audio').hexdigest())
        self.assertEqual(self.track['sourceHash'], intros.importer.fingerprint(self.lesson, self.track['scenes']))
        self.assertFalse(intros.pending_intro(self.lesson, {'segments': self.parts}))
        with self.assertRaisesRegex(ValueError, 'different introduction'):
            intros.pending_intro(self.lesson, {'segments': [dict(self.parts[0], text='다른 문제예요.')]})

    def test_title_keeps_introduction_count_body_provenance_and_idempotence(self):
        self.lesson['title'] = '중복 요청 ID 제거'
        self.lesson['scenes'][0]['introCueCount'] = 2
        self.track['scenes'][0]['provenance']['explanationSrc'] = '/static/coding-audio/body.mp3'
        part = intros.title_segment(self.lesson)
        self.assertEqual(part['text'], '1번 문제. 중복 요청 ID 제거.')
        self.assertIn('아이디', part['speech'])
        self.assertTrue(intros.pending_title(self.lesson, {'segments': [part]}))
        before = deepcopy(self.lesson['scenes'][0]['segments'])
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / 'title.mp3'
            audio.write_bytes(b'title audio')
            with patch.object(intros.renderer, 'verify', return_value=7.0):
                intros.prepend_data(self.lesson, self.track, self.story, self.links, [part], [2], audio)
        scene = self.lesson['scenes'][0]
        scene['titleCueCount'] = 1
        self.assertEqual(scene['introCueCount'], 3)
        self.assertEqual(scene['segments'][1:], before)
        self.assertEqual(self.track['scenes'][0]['provenance']['explanationSrc'], '/static/coding-audio/body.mp3')
        self.assertFalse(intros.pending_title(self.lesson, {'segments': [part]}))
        self.assertFalse(intros.pending_intro(self.lesson, {'segments': before}))
        with self.assertRaisesRegex(ValueError, 'different title'):
            intros.pending_title(self.lesson, {'segments': [dict(part, text='changed')]})

    def test_unmeasured_or_truncated_audio_is_rejected_before_data_changes(self):
        before = deepcopy(self.lesson)
        with patch.object(intros.renderer, 'verify', return_value=5.5):
            with self.assertRaisesRegex(ValueError, 'duration differs'):
                intros.prepend_data(self.lesson, self.track, self.story, self.links, self.parts, [1.25, 1.75], Path('unused'))
        self.assertEqual(before, self.lesson)
        with self.assertRaisesRegex(ValueError, 'positive measured'):
            intros.prepend_data(self.lesson, self.track, self.story, self.links, self.parts, [0, 1], Path('unused'))

    def test_intro_cards_are_centered_and_do_not_reuse_algorithm_objects(self):
        frames = intros.intro_frames(self.parts)
        for frame in frames:
            self.assertEqual(frame['edges'], [])
            node, = frame['nodes']
            self.assertEqual((node['x'], node['y']), (320, 120))
            self.assertEqual(node['id'], 'problem-introduction')
            self.assertLessEqual(max(map(len, node['label'].splitlines())), 22)


if __name__ == '__main__':
    unittest.main()
