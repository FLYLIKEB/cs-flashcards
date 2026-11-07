"""Scene cuts follow exact history starts, including partial first-lesson imports."""
import copy
import unittest

from scripts import import_coding_eleven_lesson as eleven


class ElevenLessonTests(unittest.TestCase):
    def setUp(self):
        self.lesson = {'id': 1, 'scenes': [
            {'narration': 'a.', 'segments': [{'text': 'a.', 'speech': '에이.'}]},
            {'narration': 'b. 4.', 'segments': [{'text': 'b.', 'speech': '비.'}, {'text': '4.', 'speech': '사.'}]},
            {'narration': 'c.', 'segments': [{'text': 'c.', 'speech': '씨.'}]}]}

    def history(self, first=1):
        speech = ' '.join(segment['speech'] for scene in self.lesson['scenes'][first - 1:]
                          for segment in scene['segments'])
        return {'alignments': {'alignment': {'characters': list(speech),
                'character_start_times_seconds': [round(0.2 + i * 0.1, 3) for i in range(len(speech))]}}}

    def test_whole_lesson_uses_actual_scene_start_including_leading_silence(self):
        cuts = eleven.scene_timings(self.lesson, self.history(), 1, 2)
        self.assertEqual(cuts, [{'start': 0, 'end': 0.6, 'offset': 0, 'length': 3},
                                {'start': 0.6, 'end': 1.2, 'offset': 4, 'length': 5},
                                {'start': 1.2, 'end': 2, 'offset': 10, 'length': 2}])

    def test_partial_lesson_excludes_existing_opening_scene(self):
        cuts = eleven.scene_timings(self.lesson, self.history(first=2), 2, 2)
        self.assertEqual(cuts, [{'start': 0, 'end': 0.8, 'offset': 0, 'length': 5},
                                {'start': 0.8, 'end': 2, 'offset': 6, 'length': 2}])

    def test_wrong_join_text_and_out_of_bounds_scene_fail(self):
        history = self.history()
        history['alignments']['alignment']['characters'][3] = '\n'
        with self.assertRaises(ValueError):
            eleven.scene_timings(self.lesson, history, 1, 2)
        for first in (0, 4):
            with self.subTest(first=first), self.assertRaises(ValueError):
                eleven.scene_timings(self.lesson, self.history(), first, 2)

    def test_nonincreasing_scene_boundary_fails(self):
        history = self.history()
        history['alignments']['alignment']['character_start_times_seconds'] = [0] * 12
        with self.assertRaises(ValueError):
            eleven.scene_timings(self.lesson, history, 1, 2)


if __name__ == '__main__':
    unittest.main()
