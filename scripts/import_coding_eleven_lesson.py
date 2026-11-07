#!/usr/bin/env python3
"""Split a generated ElevenLabs lesson using its exact history character starts.

Join authored speech with one space across every segment and scene before generation.
For lesson 1's existing opening sample, pass --first-scene 2 to retain that scene.
Default is dry run; --apply installs all selected scenes with one manifest switch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import wave

try:
    from scripts import import_coding_ai_audio as importer
except ModuleNotFoundError:
    import import_coding_ai_audio as importer

renderer = importer.renderer
ROOT = importer.ROOT


def scene_timings(lesson: dict, history: dict, first_scene: int, duration: float) -> list[dict]:
    if not 1 <= first_scene <= len(lesson['scenes']):
        raise ValueError('First scene is outside this lesson')
    scenes = lesson['scenes'][first_scene - 1:]
    segments = [part for scene in scenes for part in renderer.narration_segments(scene)]
    combined = {'segments': segments, 'narration': ' '.join(part['text'] for part in segments)}
    importer.history_cues(combined, history, duration)  # Exact speech and timing validation.
    alignment = history['alignments']['alignment']
    starts = alignment['character_start_times_seconds']
    offset, boundaries = 0, []
    for scene in scenes:
        speech = ' '.join(part['speech'] for part in renderer.narration_segments(scene))
        boundaries.append((offset, len(speech)))
        offset += len(speech) + 1
    result = []
    for index, (offset, length) in enumerate(boundaries):
        begin = starts[offset] if index else 0.0
        end = starts[boundaries[index + 1][0]] if index + 1 < len(boundaries) else duration
        if end <= begin:
            raise ValueError('Scene boundaries must strictly advance')
        result.append({'start': begin, 'end': end, 'offset': offset, 'length': length})
    return result


def import_lesson(audio: Path, history: dict, lesson: dict, output: Path, voice: str,
                  first_scene: int = 1, apply: bool = False) -> dict:
    manifest_path = output / 'manifest.json'
    original = manifest_path.read_bytes()
    manifest = json.loads(original)
    entry = next(item for item in manifest['lessons'] if item['id'] == lesson['id'])
    if len(entry['scenes']) != len(lesson['scenes']):
        raise ValueError('Existing manifest does not contain every lesson scene')
    renderer.verify(audio)
    renderer.audible(audio)
    with tempfile.TemporaryDirectory(prefix='eleven-lesson-', dir=output) as directory:
        work = Path(directory)
        pcm = work / 'source.wav'
        renderer.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(audio),
                      '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le', str(pcm)], timeout=120)
        with wave.open(str(pcm), 'rb') as decoded:
            frame_count = decoded.getnframes()
            duration = frame_count / 24000
            boundaries = scene_timings(lesson, history, first_scene, duration)
            original_alignment = history['alignments']['alignment']
            files = []
            for number, boundary in enumerate(boundaries, first_scene):
                scene = lesson['scenes'][number - 1]
                begin = round(boundary['start'] * 24000)
                end = round(boundary['end'] * 24000)
                decoded.setpos(begin)
                sliced = work / 'scene.wav'
                with wave.open(str(sliced), 'wb') as target:
                    target.setnchannels(1)
                    target.setsampwidth(2)
                    target.setframerate(24000)
                    target.writeframes(decoded.readframes(end - begin))
                encoded = work / 'scene.mp3'
                renderer.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(sliced),
                              '-c:a', 'libmp3lame', '-b:a', '96k', str(encoded)], timeout=60)
                seconds = renderer.verify(encoded)
                renderer.audible(encoded)
                offset, length = boundary['offset'], boundary['length']
                alignment = {'characters': original_alignment['characters'][offset:offset + length],
                             'character_start_times_seconds': [max(0.0, value - begin / 24000)
                                 for value in original_alignment['character_start_times_seconds'][offset:offset + length]]}
                cues = importer.history_cues(scene, {'alignments': {'alignment': alignment}}, seconds)
                audio_hash = hashlib.sha256(encoded.read_bytes()).hexdigest()
                name = f"{lesson['id']:02d}-{number:02d}-{audio_hash[:12]}.mp3"
                encoded.rename(work / name)
                files.append(name)
                entry['scenes'][number - 1] = {
                    'src': f'/static/coding-audio/{name}', 'duration': round(seconds, 3), 'cues': cues,
                    'provenance': {'provider': 'elevenlabs', 'voice': voice, 'audioHash': audio_hash,
                                   'speechHash': importer.digest([part['speech'] for part in renderer.narration_segments(scene)]),
                                   'timing': 'character-alignment'}}
        entry['sourceHash'] = importer.fingerprint(lesson, entry['scenes'])
        entry['sourceHashKind'] = 'ai-import-v1'
        manifest['voice'] = 'Mixed'
        if apply:
            if manifest_path.read_bytes() != original:
                raise ValueError('Manifest changed during conversion; rerun to preserve concurrent imports')
            for name in files:
                (work / name).replace(output / name)
            pending = work / 'manifest.json'
            pending.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
            pending.replace(manifest_path)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lesson', type=int, required=True)
    parser.add_argument('--first-scene', type=int, default=1)
    parser.add_argument('--audio', type=Path, required=True)
    parser.add_argument('--history', type=Path, required=True)
    parser.add_argument('--voice', default='Yun')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    lessons = json.loads((ROOT / 'static/coding-lessons.json').read_text())
    lesson = next((item for item in lessons if item['id'] == args.lesson), None)
    if lesson is None:
        parser.error('Unknown lesson')
    import_lesson(args.audio, json.loads(args.history.read_text()), lesson,
                  ROOT / 'static/coding-audio', args.voice, args.first_scene, args.apply)
    print(f'{"Imported" if args.apply else "Validated (dry run)"}: '
          f'lesson {args.lesson}, scenes {args.first_scene}–{len(lesson["scenes"])}')


if __name__ == '__main__':
    main()
