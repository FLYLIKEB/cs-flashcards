#!/usr/bin/env python3
"""Render Korean narration for DOM coding slides using local macOS say and FFmpeg.

Run: .venv/bin/python scripts/render_coding_lesson_audio.py [--ids 1 2] [--force]
No video, external service, credentials, or dependency installation is involved.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
import re
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'static/coding-lessons.json'
OUTPUT = ROOT / 'static/coding-audio'
VOICE, RATE = 'Yuna', 185


def run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs)


def verify(path: Path) -> float:
    data = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]).stdout)
    audio = [s for s in data['streams'] if s['codec_type'] == 'audio']
    seconds = float(data['format']['duration'])
    if len(audio) != 1 or audio[0]['codec_name'] != 'mp3' or not math.isfinite(seconds) or seconds <= 0.5:
        raise ValueError(f'Invalid narration: {path}')
    return seconds


def audible(path: Path):
    result = run(['ffmpeg', '-hide_banner', '-i', str(path), '-af', 'volumedetect', '-f', 'null', '-'], timeout=60)
    if 'mean_volume:' not in result.stderr or 'mean_volume: -inf' in result.stderr:
        raise ValueError(f'Silent narration: {path}')


def sentences(narration: str) -> list[str]:
    """Keep the spoken text intact while giving each sentence measured boundaries."""
    return re.split(r'(?<=[.!?])\s+', ' '.join(narration.split()))


def narration_segments(scene: dict) -> list[dict]:
    """Display code literally while giving TTS an explicitly authored reading."""
    segments = scene.get('segments')
    if segments is None:
        return [{'text': text, 'speech': text} for text in sentences(scene['narration'])]
    if not isinstance(segments, list) or not segments:
        raise ValueError('Narration needs at least one paired segment')
    if any(not isinstance(item, dict) or
           any(not isinstance(item.get(key), str) or not item[key].strip()
               for key in ('text', 'speech')) for item in segments):
        raise ValueError('Every subtitle needs a nonempty spoken reading')
    if ' '.join(item['text'] for item in segments) != scene['narration']:
        raise ValueError('Display transcript must match subtitle segments')
    return segments


def pcm_duration(path: Path) -> float:
    data = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(path)]).stdout)
    stream = next(s for s in data['streams'] if s['codec_type'] == 'audio')
    numerator, denominator = map(int, stream['time_base'].split('/'))
    seconds = int(stream['duration_ts']) * numerator / denominator
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError(f'Invalid sentence duration: {path}')
    return seconds


def verify_cues(scene: dict, narration: str):
    cues = scene['cues']
    if not cues or ' '.join(cue['text'] for cue in cues) != ' '.join(narration.split()):
        raise ValueError('Subtitle text does not match narration')
    previous_end = 0
    for cue in cues:
        start, end = cue['start'], cue['end']
        if not math.isfinite(start) or not math.isfinite(end) or abs(start - previous_end) > 0.001:
            raise ValueError('Subtitle cues must be contiguous from zero')
        if end <= start or end > scene['duration'] + 0.001:
            raise ValueError('Subtitle cue outside clip bounds')
        previous_end = end
    if abs(previous_end - scene['duration']) > 0.001:
        raise ValueError('Subtitle cues must cover the clip')


def fingerprint(lesson: dict) -> str:
    digest = hashlib.sha256(Path(__file__).read_bytes())
    digest.update(json.dumps(lesson, ensure_ascii=False, sort_keys=True).encode())
    return digest.hexdigest()


def render(lesson: dict, prior: dict | None, force: bool) -> dict:
    for scene in lesson['scenes']:
        narration_segments(scene)
    source_hash = fingerprint(lesson)
    if not force and prior and prior.get('sourceHash') == source_hash and len(prior.get('scenes', [])) == len(lesson['scenes']):
        try:
            for index, scene in enumerate(prior['scenes'], 1):
                cached = OUTPUT / f"{lesson['id']:02d}-{index:02d}.mp3"
                actual = verify(cached)
                audible(cached)
                verify_cues(scene, lesson['scenes'][index - 1]['narration'])
                if abs(actual - scene['duration']) > 0.1:
                    raise ValueError('Cached duration mismatch')
            return prior
        except (ValueError, KeyError, subprocess.CalledProcessError):
            pass
    scenes = []
    with tempfile.TemporaryDirectory(prefix=f"coding-audio-{lesson['id']:02d}-") as directory:
        work = Path(directory)
        for index, scene in enumerate(lesson['scenes'], 1):
            narration = scene['narration']
            if not isinstance(narration, str) or not narration.strip():
                raise ValueError(f"Missing narration: {lesson['id']}/{index}")
            name = f"{lesson['id']:02d}-{index:02d}.mp3"
            text, encoded = work / 'speech.txt', work / name
            cues, parts, elapsed = [], [], 0.0
            for number, segment in enumerate(narration_segments(scene)):
                sound = work / f'sentence-{number:03d}.aiff'
                text.write_text(segment['speech'], encoding='utf-8')
                run(['say', '-v', VOICE, '-r', str(RATE), '-f', str(text), '-o', str(sound)], timeout=120)
                start = elapsed
                elapsed += pcm_duration(sound)
                cues.append({'start': round(start, 3), 'end': round(elapsed, 3), 'text': segment['text']})
                parts.append(f"file '{sound.name}'")
            concat = work / 'sentences.txt'
            concat.write_text('\n'.join(parts) + '\n', encoding='utf-8')
            run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                 '-f', 'concat', '-safe', '0', '-i', str(concat),
                 '-c:a', 'libmp3lame', '-b:a', '64k', '-ar', '24000', '-ac', '1',
                 '-af', 'apad=pad_dur=0.25', str(encoded)], timeout=60)
            seconds = verify(encoded)
            audible(encoded)
            cues[-1]['end'] = round(seconds, 3)
            clip = {'src': f'/static/coding-audio/{name}', 'duration': round(seconds, 3), 'cues': cues}
            verify_cues(clip, narration)
            shutil.move(str(encoded), OUTPUT / name)
            scenes.append(clip)
    return {'id': lesson['id'], 'scenes': scenes, 'sourceHash': source_hash}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ids', type=int, nargs='+', help='Lesson IDs; default all')
    parser.add_argument('--jobs', type=int, choices=(1, 2, 3), default=3)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    for command in ('say', 'ffmpeg', 'ffprobe'):
        if not shutil.which(command):
            parser.error(f'Required local tool unavailable: {command}')
    lessons = json.loads(SOURCE.read_text(encoding='utf-8'))
    ids = [p['id'] for p in lessons]
    if len(set(ids)) != len(ids) or any(i not in range(1, 31) for i in ids):
        parser.error('Expected unique lesson IDs in 1-30')
    if not args.ids and ids != list(range(1, 31)):
        parser.error('Full build requires all30 lessons')
    if args.ids and not set(args.ids).issubset(ids):
        parser.error('Requested lesson source is not ready')
    if args.ids and any(i not in range(1, 31) for i in args.ids):
        parser.error('Lesson IDs must be 1–30')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUTPUT / 'manifest.json'
    prior = json.loads(manifest_path.read_text())['lessons'] if manifest_path.exists() else []
    entries = {p['id']: p for p in prior}
    chosen = [p for p in lessons if not args.ids or p['id'] in args.ids]
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = [executor.submit(render, lesson, entries.get(lesson['id']), args.force) for lesson in chosen]
        for future in as_completed(futures):
            lesson = future.result()
            entries[lesson['id']] = lesson
            output = {'version': 2, 'voice': VOICE, 'rate': RATE,
                      'lessons': sorted(entries.values(), key=lambda p: p['id'])}
            temporary = OUTPUT / 'manifest.tmp'
            temporary.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            temporary.replace(manifest_path)
            print(f"Ready {lesson['id']:02d}: {len(lesson['scenes'])} clips, {sum(s['duration'] for s in lesson['scenes']):.1f}s", flush=True)
    print(f'Completed {len(chosen)} lessons; manifest has {len(entries)}.', flush=True)


if __name__ == '__main__':
    main()
