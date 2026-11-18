"""Recorded Ucle narration must match authored content and measured sections."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import render_ucle_audio as renderer


class UcleAudioTests(unittest.TestCase):
    def test_source_covers_all_questions_and_keeps_cautions_in_answer(self):
        tracks = renderer.source_tracks()
        self.assertEqual([t['id'] for t in tracks], list(range(1, 201)))
        answers = [a for name in renderer.ANSWER_FILES
                   for a in json.loads((renderer.SITE / name).read_text())]
        for track, answer in zip(tracks, answers):
            with self.subTest(id=track['id']):
                self.assertEqual([s['step'] for s in track['sections']], [0, 1, 2, 3])
                self.assertEqual(track['path'], f'audio/question-{track["id"]:03}.mp3')
                self.assertTrue(all(s['text'] and '**' not in s['text'] for s in track['sections']))
                for paragraph in answer['answer']:
                    self.assertIn(renderer.plain_text(paragraph), track['sections'][2]['text'])
                if answer.get('caution'):
                    self.assertIn(renderer.plain_text(answer['caution']), track['sections'][2]['text'])
        self.assertIn('이렇게 물어보세요.', tracks[190]['sections'][2]['text'])
        self.assertNotEqual(tracks[0]['sourceHash'], tracks[1]['sourceHash'])

    def test_shipped_manifest_matches_sources_and_files(self):
        manifest = json.loads((renderer.OUTPUT / 'manifest.json').read_text())
        self.assertEqual((manifest['version'], manifest['voice'], manifest['rate']), (1, 'Yuna', 185))
        expected = renderer.source_tracks()
        self.assertEqual(len(manifest['tracks']), 200)
        self.assertEqual(len(list(renderer.OUTPUT.glob('question-*.mp3'))), 200)
        for source, recorded in zip(expected, manifest['tracks']):
            with self.subTest(id=source['id']):
                for field in ('id', 'path', 'sourceHash'):
                    self.assertEqual(source[field], recorded[field])
                renderer.validate_sections(source, recorded['sections'], recorded['duration'])
                self.assertGreater((renderer.SITE / recorded['path']).stat().st_size, 1000)

    def test_rejects_stale_text_nonfinite_and_overlapping_sections(self):
        track = renderer.source_tracks()[0]
        valid = [{**s, 'start': float(i), 'end': float(i + 1)}
                 for i, s in enumerate(track['sections'])]
        self.assertEqual(renderer.validate_sections(track, valid, 4.05), valid)
        invalids = [None, [], valid[:3]]
        for key, value in [('start', .5), ('end', float('nan')), ('end', 6), ('text', 'stale'), ('step', 99)]:
            invalid = copy.deepcopy(valid)
            invalid[1][key] = value
            invalids.append(invalid)
        for invalid in invalids:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                renderer.validate_sections(track, invalid, 4.05)
        with self.assertRaises(ValueError):
            renderer.validate_sections(track, valid, 5)

    def test_pcm_boundaries_come_from_actual_samples_and_encode_once(self):
        track = renderer.source_tracks()[0]
        lengths = [24000, 36000, 48002, 12000]
        remaining = iter(lengths)
        spoken, encodings = [], []
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            output = site / 'audio'
            output.mkdir()

            def fake_run(args):
                if args[0] == 'say':
                    spoken.append(Path(args[args.index('-f') + 1]).read_text())
                elif args[-1].endswith('section.pcm'):
                    Path(args[-1]).write_bytes(b'\x01\x00' * next(remaining))
                else:
                    encodings.append(Path(args[args.index('-i') + 1]).read_bytes())
                    Path(args[-1]).write_bytes(b'encoded-mp3')

            duration = round(sum(lengths) / 24000, 6)
            with patch.object(renderer, 'SITE', site), patch.object(renderer, 'OUTPUT', output), \
                    patch.object(renderer, 'run', side_effect=fake_run), \
                    patch.object(renderer, 'verify', return_value=duration):
                result = renderer.render(track)
            self.assertEqual(spoken, [renderer.pronounce(s['text']) for s in track['sections']])
            self.assertEqual(len(encodings), 1)
            self.assertEqual(len(encodings[0]), sum(lengths) * 2)
            self.assertEqual([s['start'] for s in result['sections']], [0, 1., 2.5, 4.500083])
            self.assertEqual(result['sections'][-1]['end'], 5.000083)
            self.assertEqual((site / track['path']).read_bytes(), b'encoded-mp3')
            self.assertFalse(list(output.glob('.render-*')))

    def test_verify_only_fails_closed_on_stale_cache_without_synthesizing(self):
        track = renderer.source_tracks()[0]
        valid = [{**s, 'start': float(i), 'end': float(i + 1)}
                 for i, s in enumerate(track['sections'])]
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            (site / 'audio').mkdir()
            (site / track['path']).write_bytes(b'existing-mp3')
            with patch.object(renderer, 'SITE', site), patch.object(renderer, 'run') as synthesis, \
                    patch.object(renderer, 'verify', return_value=4.05):
                prior = {**track, 'sections': valid}
                self.assertEqual(renderer.render(track, prior, verify_only=True)['sections'], valid)
                for stale in (None, {**prior, 'sourceHash': 'old'}, {**prior, 'sections': []}):
                    with self.assertRaises(ValueError):
                        renderer.render(track, stale, verify_only=True)
                synthesis.assert_not_called()


if __name__ == '__main__':
    unittest.main()
