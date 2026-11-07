"""External speech must match authored readings and measured subtitle boundaries."""
import copy
import unittest

from scripts import import_coding_ai_audio as importer


class AudioImportTests(unittest.TestCase):
    def setUp(self):
        self.scene = {'narration': 'b 확인. 4 더하기.', 'segments': [
            {'text': 'b 확인.', 'speech': '비 확인.'},
            {'text': '4 더하기.', 'speech': '사 더하기.'}]}
        speech = ' '.join(s['speech'] for s in self.scene['segments'])
        self.alignment = {'characters': list(speech),
                          'character_start_times_seconds': [i / 10 for i in range(len(speech))],
                          'character_end_times_seconds': [(i + 1) / 10 for i in range(len(speech))]}
        self.history = {'alignments': {'alignment': self.alignment}}

    def test_real_character_boundary_preserves_literal_subtitles_and_full_coverage(self):
        cues = importer.history_cues(self.scene, self.history, 1.5)
        self.assertEqual(cues, [{'start': 0.0, 'end': 0.6, 'text': 'b 확인.'},
                                {'start': 0.6, 'end': 1.5, 'text': '4 더하기.'}])

    def test_history_duration_like_end_fields_do_not_replace_absolute_starts(self):
        history = copy.deepcopy(self.history)
        history['alignments']['alignment']['character_end_times_seconds'] = [0.1] * len(self.alignment['characters'])
        cues = importer.history_cues(self.scene, history, 1.5)
        self.assertEqual(cues[1]['start'], 0.6)
        self.assertEqual(cues[-1]['end'], 1.5)

    def test_rejects_changed_speech_or_missing_alignment(self):
        wrong = copy.deepcopy(self.history)
        wrong['alignments']['alignment']['characters'][0] = '씨'
        for history in (wrong, {}, {'alignments': None}):
            with self.subTest(history=history), self.assertRaises(ValueError):
                importer.history_cues(self.scene, history, 1.5)

    def test_rejects_malformed_unordered_nonfinite_and_out_of_bounds_times(self):
        for key, value in (
            ('character_start_times_seconds', [0]),
            ('character_start_times_seconds', [0.5] + self.alignment['character_start_times_seconds'][1:]),
            ('character_start_times_seconds', [float('nan')] + self.alignment['character_start_times_seconds'][1:]),
            ('character_start_times_seconds', [2.0] * len(self.alignment['characters'])),
        ):
            bad = copy.deepcopy(self.history)
            bad['alignments']['alignment'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                importer.history_cues(self.scene, bad, 1.5)

    def test_measured_clips_have_exact_count_speech_and_total_duration(self):
        measured = [{'speech': '비 확인.', 'duration': 0.8}, {'speech': '사 더하기.', 'duration': 1.2}]
        cues = importer.segment_cues(self.scene, measured, 2.04)
        self.assertEqual(cues[0]['end'], 0.8)
        self.assertEqual(cues[-1]['end'], 2.04)
        for items in (measured[:1], [dict(measured[0], speech='다른 말'), measured[1]],
                      [dict(measured[0], duration=-1), measured[1]]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                importer.segment_cues(self.scene, items, 2.04)
        with self.assertRaises(ValueError):
            importer.segment_cues(self.scene, measured, 3)

    def test_fingerprint_changes_with_voice_timing_and_authored_content(self):
        lesson = {'id': 1, 'scenes': [self.scene]}
        scenes = [{'cues': [{'start': 0, 'end': 1}], 'provenance': {'voice': 'Yun'}}]
        original = importer.fingerprint(lesson, scenes)
        self.assertEqual(original, importer.fingerprint(copy.deepcopy(lesson), copy.deepcopy(scenes)))
        changed = copy.deepcopy(scenes)
        changed[0]['provenance']['voice'] = 'Ara'
        self.assertNotEqual(original, importer.fingerprint(lesson, changed))
        changed = copy.deepcopy(scenes)
        changed[0]['cues'][0]['end'] = 2
        self.assertNotEqual(original, importer.fingerprint(lesson, changed))
        changed_lesson = copy.deepcopy(lesson)
        changed_lesson['scenes'][0]['segments'][0]['speech'] = '다른 말'
        self.assertNotEqual(original, importer.fingerprint(changed_lesson, scenes))


if __name__ == '__main__':
    unittest.main()
