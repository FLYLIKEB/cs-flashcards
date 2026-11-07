"""Batch imports validate order and all scenes before a single manifest switch."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import import_coding_clova_zip as clova


class ClovaZipTests(unittest.TestCase):
    def archive(self, names):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            for name in names:
                archive.writestr(name, b'audio')
        buffer.seek(0)
        return zipfile.ZipFile(buffer)

    def test_numerical_order_and_sample_skip(self):
        with self.archive([f'{i}_Ara.mp3' for i in reversed(range(1, 13))]) as archive:
            tracks = clova.ordered_tracks(archive, 11, 1)
        self.assertEqual([t.filename for t in tracks], [f'{i}_Ara.mp3' for i in range(2, 13)])

    def test_rejects_missing_duplicate_ambiguous_and_extra_tracks(self):
        for names in (['1_a.mp3', '3_a.mp3'], ['1_a.mp3', '1_b.mp3'],
                      ['sample.mp3', '2_a.mp3'], ['1_a.mp3']):
            with self.subTest(names=names), self.archive(names) as archive, self.assertRaises(ValueError):
                clova.ordered_tracks(archive, 1, 1)

    def fixture(self, root):
        scene = {'narration': 'a예요.', 'segments': [{'text': 'a예요.', 'speech': '에이예요.'}]}
        lessons = [{'id': 9, 'scenes': [scene, scene]}]
        manifest = {'version': 2, 'voice': 'Yuna', 'lessons': [
            {'id': 9, 'sourceHash': 'old', 'scenes': [{'src': 'old1'}, {'src': 'old2'}]},
            {'id': 8, 'sourceHash': 'untouched', 'scenes': []}]}
        (root / 'manifest.json').write_text(json.dumps(manifest))
        archive_path = root / 'input.zip'
        with zipfile.ZipFile(archive_path, 'w') as archive:
            for i in range(1, 4):
                archive.writestr(f'{i}_Ara.mp3', b'placeholder')
        return lessons, manifest, archive_path

    def fake_render(self, archive, tracks, scene, destination, work):
        destination.write_bytes(tracks[0].filename.encode())
        return 1.2, [{'start': 0, 'end': 1.2, 'text': scene['narration']}]

    def test_dry_run_and_failed_later_scene_leave_manifest_and_audio_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lessons, original, archive = self.fixture(root)
            with patch.object(clova, 'render_scene', side_effect=self.fake_render):
                clova.import_zip(archive, lessons, root, '아라')
            self.assertEqual(json.loads((root / 'manifest.json').read_text()), original)
            self.assertEqual(list(root.glob('*.mp3')), [])
            calls = 0
            def failing(*args):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise ValueError('Invalid later scene')
                return self.fake_render(*args)
            with patch.object(clova, 'render_scene', side_effect=failing), self.assertRaises(ValueError):
                clova.import_zip(archive, lessons, root, '아라', apply=True)
            self.assertEqual(json.loads((root / 'manifest.json').read_text()), original)
            self.assertEqual(list(root.glob('*.mp3')), [])

    def test_apply_preserves_other_lessons_and_hashes_complete_scenes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lessons, original, archive = self.fixture(root)
            with patch.object(clova, 'render_scene', side_effect=self.fake_render):
                result = clova.import_zip(archive, lessons, root, '아라', apply=True)
            saved = json.loads((root / 'manifest.json').read_text())
            self.assertEqual(saved, result)
            self.assertEqual(saved['lessons'][1], original['lessons'][1])
            self.assertEqual(len(list(root.glob('*.mp3'))), 2)
            entry = saved['lessons'][0]
            self.assertEqual(entry['sourceHash'], clova.importer.fingerprint(lessons[0], entry['scenes']))


if __name__ == '__main__':
    unittest.main()
