#!/usr/bin/env python3
"""Import ordered Clova per-sentence MP3 downloads without estimating cue timing.

Dry run: python scripts/import_coding_clova_zip.py export.zip --voice 아라
Defaults map tracks after the first sample to all segments in lessons 9 through 25.
Use --apply only after confirming the downloaded track order matches that source order.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
import wave
import zipfile

try:
    from scripts import import_coding_ai_audio as importer
except ModuleNotFoundError:
    import import_coding_ai_audio as importer

renderer = importer.renderer
ROOT = importer.ROOT


def ordered_tracks(archive: zipfile.ZipFile, expected: int, skip: int) -> list[zipfile.ZipInfo]:
    numbered = []
    for item in archive.infolist():
        path = PurePosixPath(item.filename)
        if item.is_dir() or '__MACOSX' in path.parts or path.suffix.lower() != '.mp3':
            continue
        match = re.match(r'^(\d+)(?:[_. \-]|$)', path.name)
        if not match:
            raise ValueError(f'MP3 has no leading track number: {path.name}')
        numbered.append((int(match.group(1)), item))
    numbered.sort(key=lambda row: row[0])
    numbers = [number for number, _ in numbered]
    if len(numbered) != expected + skip:
        raise ValueError(f'Expected {expected + skip} MP3 tracks including samples; got {len(numbered)}')
    if not numbers or numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        raise ValueError('Track numbers must be unique and contiguous')
    return [item for _, item in numbered[skip:]]


def render_scene(archive: zipfile.ZipFile, tracks: list[zipfile.ZipInfo], scene: dict,
                 destination: Path, work: Path) -> tuple[float, list[dict]]:
    """Decode away each source MP3 encoder delay before concatenating PCM frames."""
    measured = []
    joined = work / 'joined.wav'
    with wave.open(str(joined), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        for index, (track, segment) in enumerate(zip(tracks, renderer.narration_segments(scene))):
            source, pcm = work / f'{index}.mp3', work / f'{index}.wav'
            source.write_bytes(archive.read(track))  # Never extract archive paths onto disk.
            renderer.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
                          '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le', str(pcm)], timeout=60)
            with wave.open(str(pcm), 'rb') as decoded:
                frames = decoded.getnframes()
                if frames <= 0:
                    raise ValueError(f'Empty decoded track: {track.filename}')
                measured.append({'speech': segment['speech'], 'duration': frames / 24000})
                output.writeframes(decoded.readframes(frames))
            source.unlink()
            pcm.unlink()
    renderer.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(joined),
                  '-c:a', 'libmp3lame', '-b:a', '96k', str(destination)], timeout=60)
    duration = renderer.verify(destination)
    renderer.audible(destination)
    return duration, importer.segment_cues(scene, measured, duration)


def import_zip(path: Path, lessons: list[dict], output: Path, voice: str, skip: int = 1,
               apply: bool = False) -> dict:
    manifest_path = output / 'manifest.json'
    original = manifest_path.read_bytes()
    manifest = json.loads(original)
    entries = {entry['id']: entry for entry in manifest['lessons']}
    expected = sum(len(renderer.narration_segments(scene)) for lesson in lessons for scene in lesson['scenes'])
    if not lessons or skip < 0 or len({lesson['id'] for lesson in lessons}) != len(lessons):
        raise ValueError('Need unique lessons and a nonnegative sample count')
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix='clova-import-', dir=output) as directory:
        staging = Path(directory)
        tracks = ordered_tracks(archive, expected, skip)
        cursor, staged_files = 0, []
        for lesson in lessons:
            entry = entries[lesson['id']]
            scenes = []
            for number, scene in enumerate(lesson['scenes'], 1):
                count = len(renderer.narration_segments(scene))
                selected = tracks[cursor:cursor + count]
                cursor += count
                encoded = staging / 'scene.mp3'
                duration, cues = render_scene(archive, selected, scene, encoded, staging)
                audio_hash = hashlib.sha256(encoded.read_bytes()).hexdigest()
                name = f"{lesson['id']:02d}-{number:02d}-{audio_hash[:12]}.mp3"
                encoded.rename(staging / name)
                staged_files.append(name)
                scenes.append({'src': f'/static/coding-audio/{name}', 'duration': round(duration, 3), 'cues': cues,
                               'provenance': {'provider': 'clova', 'voice': voice, 'audioHash': audio_hash,
                                              'speechHash': importer.digest([part['speech'] for part in renderer.narration_segments(scene)]),
                                              'timing': 'measured-segments'}})
            entry['scenes'] = scenes
            entry['sourceHash'] = importer.fingerprint(lesson, scenes)
            entry['sourceHashKind'] = 'ai-import-v1'
            print(f"Validated {lesson['id']:02d}: {len(scenes)} scenes", flush=True)
        manifest['voice'] = 'Mixed'
        if apply:
            if manifest_path.read_bytes() != original:
                raise ValueError('Manifest changed during conversion; rerun to preserve concurrent imports')
            for name in staged_files:
                (staging / name).replace(output / name)
            pending = staging / 'manifest.json'
            pending.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
            pending.replace(manifest_path)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip', type=Path)
    parser.add_argument('--first', type=int, default=9)
    parser.add_argument('--last', type=int, default=25)
    parser.add_argument('--skip', type=int, default=1, help='Leading sample tracks to omit')
    parser.add_argument('--voice', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    source = json.loads((ROOT / 'static/coding-lessons.json').read_text())
    lessons = [lesson for lesson in source if args.first <= lesson['id'] <= args.last]
    if [lesson['id'] for lesson in lessons] != list(range(args.first, args.last + 1)):
        parser.error('Requested lessons must form an existing ascending range')
    import_zip(args.zip, lessons, ROOT / 'static/coding-audio', args.voice, args.skip, args.apply)
    print(f'{"Imported" if args.apply else "Validated (dry run)"} lessons {args.first}–{args.last}')


if __name__ == '__main__':
    main()
