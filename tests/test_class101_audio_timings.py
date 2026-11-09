"""Sentence timing validation and PCM concatenation without voice synthesis."""
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from scripts import render_class101_audio as renderer


class AudioSentenceTimingTests(TestCase):
    def setUp(self):
        self.track = {"id": 1, "type": "answer", "text": "첫 문장입니다. 두 번째 문장입니다.",
                      "speech": "1번 답변. 첫 문장입니다. 두 번째 문장입니다.",
                      "sourceHash": "test", "path": "audio/answer-001.mp3"}

    def test_valid_sample_offsets_and_malformed_timings(self):
        valid = [{"start": 1.0, "end": 2.5}, {"start": 2.5, "end": 4.0}]
        self.assertEqual(renderer.validate_timings(self.track, valid, 4.1), valid)
        for invalid in (None, {}, [], [None, {}], [{}, {}],
                        [{"start": 1, "end": 2}],
                        [{"start": 1, "end": 2}, {"start": 1.9, "end": 3}],
                        [{"start": 1, "end": 2}, {"start": 2, "end": 5}],
                        [{"start": 1, "end": 2}, {"start": 2, "end": float("nan")}],
                        [{"start": 1, "end": 2}, {"start": "2", "end": 3}]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                renderer.validate_timings(self.track, invalid, 4.1)

    def test_render_joins_pcm_and_encodes_once_with_sample_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "audio"
            output.mkdir()
            speech_segments, encoded_pcm = [], []
            sample_lengths = iter([24000, 36000, 48002])

            def fake_run(args):
                if args[0] == "say":
                    speech_segments.append(Path(args[args.index("-f") + 1]).read_text())
                elif args[-1].endswith("segment.pcm"):
                    Path(args[-1]).write_bytes(b"\x01\x00" * next(sample_lengths))
                else:
                    encoded_pcm.append(Path(args[args.index("-i") + 1]).read_bytes())
                    Path(args[-1]).write_bytes(b"encoded-mp3")

            with patch.object(renderer, "ROOT", root), patch.object(renderer, "OUTPUT", output), \
                    patch.object(renderer, "run", side_effect=fake_run), \
                    patch.object(renderer, "verify", return_value=4.500083):
                result = renderer.render(self.track, None, False, False)
            self.assertEqual(speech_segments, ["1번 답변.", "첫 문장입니다.", "두 번째 문장입니다."])
            self.assertEqual(len(encoded_pcm), 1)
            self.assertEqual(len(encoded_pcm[0]), (24000 + 36000 + 48002) * 2)
            self.assertEqual(result["sentences"], [{"start": 1.0, "end": 2.5}, {"start": 2.5, "end": 4.500083}])
            self.assertEqual((root / self.track["path"]).read_bytes(), b"encoded-mp3")
            self.assertFalse(list(output.glob(".render-*")))

    def test_cached_audio_requires_timings_and_preserves_them(self):
        timings = [{"start": 1., "end": 2.}, {"start": 2., "end": 3.}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "audio").mkdir()
            (root / self.track["path"]).write_bytes(b"existing-audio")
            prior = {**self.track, "sentences": timings}
            with patch.object(renderer, "ROOT", root), patch.object(renderer, "verify", return_value=3.1), \
                    patch.object(renderer, "run") as synthesis:
                result = renderer.render(self.track, prior, False, True)
                self.assertEqual(result["sentences"], timings)
                synthesis.assert_not_called()
                with self.assertRaises(ValueError):
                    renderer.render(self.track, self.track, False, True)
