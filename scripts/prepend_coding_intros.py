#!/usr/bin/env python3
"""Prepend measured local problem introductions without replacing existing explanations.

Default: validate the authored introductions and print the pending lesson IDs.
--apply: synthesize local Yuna introductions, verify every output, then install JSON.
An already applied introduction is skipped; changed introductions fail closed.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import textwrap
import wave

try:
    from scripts import import_coding_ai_audio as importer
except ModuleNotFoundError:
    import import_coding_ai_audio as importer

renderer = importer.renderer
ROOT = importer.ROOT
DATA = ['coding-lessons.json', 'coding-audio/manifest.json',
        'coding-motion-01-15.json', 'coding-motion-16-30.json',
        'coding-code-links-01-15.json', 'coding-code-links-16-30.json']


def pending_intro(lesson: dict, intro: dict) -> bool:
    parts = intro.get('segments')
    renderer.narration_segments({'segments': parts, 'narration': ' '.join(p['text'] for p in parts or [])})
    count = lesson['scenes'][0].get('introCueCount', 0)
    if count:
        if lesson['scenes'][0]['segments'][:count] != parts:
            raise ValueError(f"Lesson {lesson['id']} already has a different introduction")
        return False
    return True


def intro_frames(parts: list[dict]) -> list[dict]:
    return [{'cue': i, 'nodes': [{'id': 'problem-introduction',
             'label': '\n'.join(textwrap.wrap(part['text'], width=22, break_long_words=True)),
             'x': 320, 'y': 120, 'w': 600, 'h': 224, 'tone': 'default'}], 'edges': []}
            for i, part in enumerate(parts)]


def prepend_data(lesson: dict, track: dict, story: dict, links: dict,
                 parts: list[dict], durations: list[float], encoded: Path) -> None:
    scene, old = lesson['scenes'][0], track['scenes'][0]
    if len(parts) != len(durations) or any(d <= 0 for d in durations):
        raise ValueError('Every introduction segment needs a positive measured duration')
    offset = sum(durations)
    duration = renderer.verify(encoded)
    if abs(duration - offset - old['duration']) > .15:
        raise ValueError('Combined audio duration differs from measured source content')
    starts, elapsed = [], 0.0
    for seconds in durations:
        starts.append(elapsed)
        elapsed += seconds
    starts.extend(offset + cue['start'] for cue in old['cues'])
    scene['segments'] = deepcopy(parts) + scene['segments']
    scene['narration'] = ' '.join(p['text'] for p in scene['segments'])
    scene['introCueCount'] = len(parts)
    cues = importer.make_cues(scene, starts, duration)
    audio_hash = hashlib.sha256(encoded.read_bytes()).hexdigest()
    provenance = deepcopy(old.get('provenance', {'provider': 'local', 'voice': 'Yuna'}))
    provenance.update({'audioHash': audio_hash,
                       'speechHash': importer.digest([p['speech'] for p in scene['segments']]),
                       'timing': 'measured-introduction-and-preserved-cues',
                       'introProvider': 'local', 'introVoice': 'Yuna', 'introCueCount': len(parts),
                       'explanationSrc': old['src']})
    name = f"{lesson['id']:02d}-01-{audio_hash[:12]}.mp3"
    track['scenes'][0] = {'src': f'/static/coding-audio/{name}', 'duration': round(duration, 3),
                          'cues': cues, 'provenance': provenance}
    first = story['scenes'][0]
    first['frames'] = intro_frames(parts) + [dict(frame, cue=frame['cue'] + len(parts)) for frame in first['frames']]
    original_lines = links['scenes'][0]['cues'][0]['lines']
    links['scenes'][0]['cues'] = [{'lines': list(original_lines), 'note': '먼저 입력과 구할 결과를 이해해요.'}
                                 for _ in parts] + links['scenes'][0]['cues']
    track['sourceHashKind'] = 'ai-import-v1'
    track['sourceHash'] = importer.fingerprint(lesson, track['scenes'])


def render_intro(parts: list[dict], source: Path, output: Path, work: Path) -> list[float]:
    info = json.loads(renderer.run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(source)]).stdout)
    stream = next(s for s in info['streams'] if s['codec_type'] == 'audio')
    rate = max(24000, int(stream['sample_rate']))
    channels = int(stream['channels'])
    bitrate = max(128000, int(stream.get('bit_rate', 128000)))
    durations = []
    joined = work / 'joined.wav'
    with wave.open(str(joined), 'wb') as target:
        target.setnchannels(channels)
        target.setsampwidth(2)
        target.setframerate(rate)
        for i in range(len(parts) + 1):
            if i < len(parts):
                text, original = work / 'speech.txt', work / 'intro.aiff'
                text.write_text(parts[i]['speech'])
                renderer.run(['say', '-v', 'Yuna', '-r', '185', '-f', str(text), '-o', str(original)], timeout=120)
            else:
                original = source
            pcm = work / 'part.wav'
            renderer.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(original),
                          '-ar', str(rate), '-ac', str(channels), '-c:a', 'pcm_s16le', str(pcm)], timeout=60)
            with wave.open(str(pcm), 'rb') as audio:
                frames = audio.getnframes()
                if frames <= 0:
                    raise ValueError('Empty decoded introduction or explanation')
                if i < len(parts):
                    durations.append(frames / rate)
                target.writeframes(audio.readframes(frames))
    renderer.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(joined),
                  '-c:a', 'libmp3lame', '-b:a', str(bitrate), str(output)], timeout=60)
    renderer.audible(output)
    return durations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    paths = [ROOT / 'static' / name for name in DATA]
    originals = {p: p.read_bytes() for p in paths}
    lessons, manifest, m1, m2, c1, c2 = [json.loads(originals[p]) for p in paths]
    intro_path = ROOT / 'static/coding-intros.json'
    intro_bytes = intro_path.read_bytes()
    intros = json.loads(intro_bytes)
    if [i['id'] for i in intros] != [lesson['id'] for lesson in lessons]:
        raise ValueError('Introductions must match the complete lesson sequence')
    pending = [(lesson, intro) for lesson, intro in zip(lessons, intros) if pending_intro(lesson, intro)]
    print(f'Pending introductions: {[lesson["id"] for lesson, _ in pending]}', flush=True)
    if not args.apply or not pending:
        return
    tracks = {x['id']: x for x in manifest['lessons']}
    stories = {x['id']: x for x in m1 + m2}
    links = {x['id']: x for x in c1 + c2}
    output = ROOT / 'static/coding-audio'
    with tempfile.TemporaryDirectory(prefix='coding-intros-', dir=output) as directory:
        work = Path(directory)
        media_files = []
        for lesson, intro in pending:
            track = tracks[lesson['id']]
            source = ROOT / track['scenes'][0]['src'].lstrip('/')
            encoded = work / 'encoded.mp3'
            durations = render_intro(intro['segments'], source, encoded, work)
            prepend_data(lesson, track, stories[lesson['id']], links[lesson['id']], intro['segments'], durations, encoded)
            name = Path(track['scenes'][0]['src']).name
            encoded.rename(work / name)
            media_files.append(name)
            print(f'Validated {lesson["id"]:02d}: {sum(durations):.3f}s introduction', flush=True)
        manifest['voice'] = 'Mixed'
        if any(p.read_bytes() != raw for p, raw in originals.items()) or intro_path.read_bytes() != intro_bytes:
            raise ValueError('Source files changed during synthesis; nothing applied')
        payloads = [lessons, manifest, m1, m2, c1, c2]
        for i, payload in enumerate(payloads):
            (work / f'{i}.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
        for name in media_files:
            (work / name).replace(output / name)
        changed = []
        try:
            # Install the manifest last, after scripts and their cue mappings are ready.
            for i in (0, 2, 3, 4, 5, 1):
                (work / f'{i}.json').replace(paths[i])
                changed.append(paths[i])
        except OSError:
            for path in changed:
                rollback = work / 'rollback.json'
                rollback.write_bytes(originals[path])
                rollback.replace(path)
            raise
    print(f'Applied {len(pending)} introductions; original explanation files preserved.')


if __name__ == '__main__':
    main()
