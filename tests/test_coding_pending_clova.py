"""Pending import preserves existing AI bodies and rejects stale/misordered batches."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave
import zipfile
from scripts import import_coding_pending_clova as pending


class PendingClovaTests(unittest.TestCase):
    def fixture(self, root):
        parts = [{'text': '제목.', 'speech': '제목.'}, {'text': '설명.', 'speech': '설명.'}]
        scene = {'narration': '제목. 설명.', 'segments': parts, 'introCueCount': 1, 'titleCueCount': 1}
        lessons = [{'id': 1, 'scenes': [deepcopy(scene)]}, {'id': 6, 'scenes': [deepcopy(scene)]}]
        clip = {'src': '/static/coding-audio/old.mp3', 'duration': 2, 'cues': [
            {'start': 0, 'end': 1, 'text': '제목.'}, {'start': 1, 'end': 2, 'text': '설명.'}]}
        ai = dict(deepcopy(clip), provenance={'provider': 'elevenlabs', 'voice': 'Yun', 'introProvider': 'local'})
        local = dict(deepcopy(clip), provenance={'provider': 'local'})
        manifest = {'voice': 'Mixed', 'lessons': [{'id': 1, 'scenes': [ai]}, {'id': 6, 'scenes': [local]}]}
        (root / 'manifest.json').write_text(json.dumps(manifest))
        (root / 'old.mp3').write_bytes(b'preserved')
        archive = root / 'audio.zip'
        with zipfile.ZipFile(archive, 'w') as bundle:
            for i in range(1, 4): bundle.writestr(f'{i}_Ara.mp3', b'audio')
        return lessons, manifest, pending.build_plan(lessons, manifest), archive

    def render(self, archive, tracks, scene, destination, work):
        destination.write_bytes(str(len(tracks)).encode())
        with wave.open(str(work / 'joined.wav'), 'wb') as output:
            output.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            output.writeframes(b'\0\0' * 24000 * len(tracks))
        cues = [{'start': i, 'end': i + 1, 'text': s['text']} for i, s in enumerate(scene['segments'])]
        return float(len(tracks)), cues

    def test_plan_selects_only_local_and_keeps_scene_batches_with_exact_script_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); lessons, manifest, plan, archive = self.fixture(root)
            units = plan['batches'][0]['units']
            self.assertEqual([(u['lesson'], u['kind'], u['count']) for u in units], [(1, 'prefix', 1), (6, 'full', 2)])
            pending.write_plan(plan, root / 'plan')
            self.assertEqual((root / 'plan/batch-01.txt').read_text().splitlines(), ['제목.', '제목.', '설명.'])
            self.assertEqual(len(pending.build_plan(lessons, manifest, budget=2)['batches']), 2)
            stale = deepcopy(lessons[0]); stale['scenes'][0]['segments'][0]['speech'] = '바뀜'
            with self.assertRaisesRegex(ValueError, 'changed'):
                pending.validate_unit(units[0], stale, manifest['lessons'][0]['scenes'][0])

    def test_dry_run_then_apply_preserves_ai_provider_and_requires_receipt_and_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); lessons, original, plan, archive = self.fixture(root)
            receipt = root / 'report.json'
            def tail(prefix, source, old, count, scene, cues, encoded, work):
                self.assertEqual(source.read_bytes(), b'preserved')
                encoded.write_bytes(b'new prefix and old AI body')
                return 2., deepcopy(old['cues'])
            with patch.object(pending.clova, 'render_scene', side_effect=self.render), patch.object(pending, 'append_preserved_body', side_effect=tail):
                with self.assertRaisesRegex(ValueError, 'receipt'):
                    pending.import_batch(plan, 1, archive, lessons, root, receipt, True, True)
                pending.import_batch(plan, 1, archive, lessons, root, receipt)
                self.assertEqual(json.loads((root / 'manifest.json').read_text()), original)
                self.assertEqual(len(list(root.glob('*.mp3'))), 1)
                with self.assertRaisesRegex(ValueError, 'Confirm'):
                    pending.import_batch(plan, 1, archive, lessons, root, receipt, True)
                pending.import_batch(plan, 1, archive, lessons, root, receipt, True, True)
            saved = json.loads((root / 'manifest.json').read_text())
            ai = saved['lessons'][0]['scenes'][0]['provenance']
            self.assertEqual((ai['provider'], ai['voice'], ai['introProvider'], ai['titleVoice']), ('elevenlabs', 'Yun', 'clova', '아라'))
            self.assertEqual(saved['lessons'][1]['scenes'][0]['provenance']['provider'], 'clova')
            self.assertEqual((root / 'old.mp3').read_bytes(), b'preserved')

    def test_bad_track_count_skip_and_failed_conversion_never_install(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); lessons, original, plan, archive = self.fixture(root)
            receipt = root / 'report.json'
            with self.assertRaisesRegex(ValueError, 'zero'):
                pending.import_batch(plan, 1, archive, lessons, root, receipt, skip=1)
            with patch.object(pending.clova, 'render_scene', side_effect=ValueError('bad media')), self.assertRaisesRegex(ValueError, 'bad media'):
                pending.import_batch(plan, 1, archive, lessons, root, receipt)
            with zipfile.ZipFile(archive, 'a') as bundle: bundle.writestr('4_extra.mp3', b'extra')
            with self.assertRaisesRegex(ValueError, 'Expected'):
                pending.import_batch(plan, 1, archive, lessons, root, receipt)
            self.assertEqual(json.loads((root / 'manifest.json').read_text()), original)
            self.assertFalse(receipt.exists())

    def test_existing_body_cues_are_offset_by_measured_new_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); lessons, manifest, plan, archive = self.fixture(root)
            prefix = root / 'prefix.wav'
            with wave.open(str(prefix), 'wb') as output:
                output.setparams((1, 2, 24000, 0, 'NONE', 'not compressed')); output.writeframes(b'\0\0' * 48000)
            old = manifest['lessons'][0]['scenes'][0]
            def run(args, **kwargs):
                if str(root / 'preserved-body.wav') == args[-1]:
                    with wave.open(args[-1], 'wb') as output:
                        output.setparams((1, 2, 24000, 0, 'NONE', 'not compressed')); output.writeframes(b'\0\0' * 24000)
            with patch.object(pending.renderer, 'run', side_effect=run), patch.object(pending.renderer, 'verify', return_value=3.), patch.object(pending.renderer, 'audible'):
                duration, cues = pending.append_preserved_body(prefix, root / 'old.mp3', old, 1, lessons[0]['scenes'][0], [{'start': 0, 'end': 2}], root / 'new.mp3', root)
            self.assertEqual([(c['start'], c['end']) for c in cues], [(0, 2), (2, 3)])

if __name__ == '__main__': unittest.main()
