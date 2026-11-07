#!/usr/bin/env python3
"""Validate an external scene MP3 and measured subtitle timing; write only with --apply.

Example: python scripts/import_coding_ai_audio.py --lesson 1 --scene 1 \
  --audio /tmp/scene.mp3 --history /tmp/elevenlabs-history.json --voice Yun
For concatenated Clova clips, --segments accepts [{"speech": "...", "duration": 1.2}, ...]
with durations measured from decoded clips before concatenation, not estimated text lengths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile

try:
    from scripts import render_coding_lesson_audio as renderer
except ModuleNotFoundError:
    import render_coding_lesson_audio as renderer

ROOT = Path(__file__).resolve().parents[1]


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def fingerprint(lesson: dict, scenes: list[dict]) -> str:
    """Include authored content, provider provenance and every final scene timing."""
    return digest({'importerVersion': 1, 'lesson': lesson, 'scenes': scenes})


def checked_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Timing must contain finite numbers')
    return float(value)


def make_cues(scene: dict, starts: list[float], duration: float) -> list[dict]:
    parts = renderer.narration_segments(scene)
    duration = checked_number(duration)
    if len(starts) != len(parts):
        raise ValueError('Timing count must match subtitle segments')
    bounds = [round(checked_number(value), 3) for value in starts] + [round(duration, 3)]
    bounds[0] = 0.0
    cues = [{'start': bounds[i], 'end': bounds[i + 1], 'text': part['text']}
            for i, part in enumerate(parts)]
    renderer.verify_cues({'duration': round(duration, 3), 'cues': cues}, scene['narration'])
    return cues


def history_cues(scene: dict, history: dict, duration: float) -> list[dict]:
    parts = renderer.narration_segments(scene)
    speech = ' '.join(part['speech'] for part in parts)
    alignment = (history.get('alignments') or {}).get('alignment')
    if not isinstance(alignment, dict):
        raise ValueError('History does not contain original character alignment')
    chars = alignment.get('characters', [])
    starts = alignment.get('character_start_times_seconds', [])
    if not chars or not all(isinstance(c, str) and len(c) == 1 for c in chars) or ''.join(chars) != speech:
        raise ValueError('Aligned speech differs from the authored scene')
    if len(chars) != len(starts):
        raise ValueError('Character timing arrays have different lengths')
    # History v4 currently returns duration-like values in the field named
    # character_end_times_seconds. Only verified absolute starts define cuts.
    prior_start = 0.0
    for start in starts:
        start = checked_number(start)
        if start < prior_start or start >= duration:
            raise ValueError('Character starts are unordered or outside the MP3')
        prior_start = start
    offsets, offset = [], 0
    for part in parts:
        offsets.append(starts[offset])
        offset += len(part['speech']) + 1
    return make_cues(scene, offsets, duration)


def segment_cues(scene: dict, measured: list[dict], duration: float) -> list[dict]:
    parts = renderer.narration_segments(scene)
    if not isinstance(measured, list) or len(measured) != len(parts):
        raise ValueError('Measured clips must match every authored segment')
    starts, elapsed = [], 0.0
    for part, item in zip(parts, measured):
        if item.get('speech') != part['speech']:
            raise ValueError('Measured clip speech differs from authored segment')
        seconds = checked_number(item.get('duration'))
        if seconds <= 0:
            raise ValueError('Measured clip duration must be positive')
        starts.append(elapsed)
        elapsed += seconds
    # A final MP3 encoder delay/padding is allowed, but missing or extra content is not.
    if abs(elapsed - duration) > 0.1:
        raise ValueError('Measured clip durations do not cover the final MP3')
    return make_cues(scene, starts, duration)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lesson', type=int, required=True)
    parser.add_argument('--scene', type=int, required=True, help='1-based scene number')
    parser.add_argument('--audio', type=Path, required=True)
    timing = parser.add_mutually_exclusive_group(required=True)
    timing.add_argument('--history', type=Path)
    timing.add_argument('--segments', type=Path)
    parser.add_argument('--voice', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    lessons = json.loads((ROOT / 'static/coding-lessons.json').read_text())
    lesson = next((item for item in lessons if item['id'] == args.lesson), None)
    if lesson is None or not 1 <= args.scene <= len(lesson['scenes']):
        parser.error('Unknown lesson or scene')
    scene = lesson['scenes'][args.scene - 1]
    duration = renderer.verify(args.audio)
    renderer.audible(args.audio)
    source = json.loads((args.history or args.segments).read_text())
    cues = history_cues(scene, source, duration) if args.history else segment_cues(scene, source, duration)
    audio_hash = hashlib.sha256(args.audio.read_bytes()).hexdigest()
    provider = 'elevenlabs' if args.history else 'clova'
    name = f'{args.lesson:02d}-{args.scene:02d}-{audio_hash[:12]}.mp3'
    clip = {'src': f'/static/coding-audio/{name}', 'duration': round(duration, 3), 'cues': cues,
            'provenance': {'provider': provider, 'voice': args.voice, 'audioHash': audio_hash,
                           'speechHash': digest([part['speech'] for part in renderer.narration_segments(scene)]),
                           'timing': 'character-alignment' if args.history else 'measured-segments'}}
    output = ROOT / 'static/coding-audio'
    manifest_path = output / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    entry = next(item for item in manifest['lessons'] if item['id'] == args.lesson)
    entry['scenes'][args.scene - 1] = clip
    entry['sourceHash'] = fingerprint(lesson, entry['scenes'])
    entry['sourceHashKind'] = 'ai-import-v1'
    manifest['voice'] = 'Mixed'
    if args.apply:
        # Content-addressed audio is installed first; manifest replacement is atomic.
        # Existing media remains available until the manifest switches to the new file.
        with tempfile.TemporaryDirectory(prefix='coding-import-', dir=output) as directory:
            temporary = Path(directory)
            shutil.copyfile(args.audio, temporary / name)
            (temporary / name).replace(output / name)
            staged = temporary / 'manifest.json'
            staged.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
            staged.replace(manifest_path)
    print(f'{"Imported" if args.apply else "Validated (dry run)"}: {args.lesson:02d}/{args.scene:02d}, '
          f'{provider}/{args.voice}, {duration:.3f}s, {len(cues)} cues')


if __name__ == '__main__':
    main()
