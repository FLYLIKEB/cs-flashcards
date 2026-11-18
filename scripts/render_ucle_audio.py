#!/usr/bin/env python3
"""Render one Korean MP3 per Ucle question with measured section boundaries.

Run with --verify-only to decode every shipped file and check source freshness.
The source texts remain unchanged; spoken abbreviations use the existing interview dictionary.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

try:
    from .build_ucle_interview import SITE, load_questions
    from .render_class101_audio import plain_text, pronounce, run, verify
except ImportError:
    from build_ucle_interview import SITE, load_questions
    from render_class101_audio import plain_text, pronounce, run, verify

OUTPUT = SITE / 'audio'
VOICE, RATE = 'Yuna', 185
SAMPLE_RATE = 24000
ANSWER_FILES = ('answers-001-070.json', 'answers-071-140.json', 'answers-141-200.json')


def source_tracks():
    answers = [answer for name in ANSWER_FILES for answer in json.loads((SITE / name).read_text())]
    questions = load_questions()
    if [a['id'] for a in answers] != list(range(1, 201)):
        raise ValueError('Expected answers 1–200 exactly once in order')
    tracks = []
    for question, answer in zip(questions, answers):
        number = question['id']
        answer_label = '이렇게 물어보세요.' if number >= 191 else '이렇게 말해보세요.'
        answer_text = answer_label + ' ' + ' '.join(answer['answer'])
        if answer.get('caution'):
            answer_text += ' 확인할 점입니다. ' + answer['caution']
        sections = [
            {'step': 0, 'text': plain_text(f'{number}번 질문. {question["question"]}')},
            {'step': 1, 'text': plain_text('한 줄 핵심. ' + answer['summary'])},
            {'step': 2, 'text': plain_text(answer_text)},
            {'step': 3, 'text': plain_text('쉽게 이해하기. ' + answer['explanation'])},
        ]
        fingerprint = json.dumps(
            [sections, [pronounce(s['text']) for s in sections], VOICE, RATE,
             'ucle-pcm-sections-mp3-48k-v1'], ensure_ascii=False, sort_keys=True).encode()
        tracks.append({'id': number, 'path': f'audio/question-{number:03}.mp3',
                       'sourceHash': hashlib.sha256(fingerprint).hexdigest(), 'sections': sections})
    return tracks


def validate_sections(track, sections, duration):
    if not math.isfinite(duration) or duration <= .5:
        raise ValueError(f'Invalid duration: {track["path"]}')
    if not isinstance(sections, list) or len(sections) != 4:
        raise ValueError(f'Missing section timings: {track["path"]}')
    previous = 0
    for expected, actual in zip(track['sections'], sections):
        if not isinstance(actual, dict) or any(actual.get(key) != expected[key] for key in ('step', 'text')):
            raise ValueError(f'Stale section content: {track["path"]}')
        start, end = actual.get('start'), actual.get('end')
        if (not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                or not math.isfinite(start) or not math.isfinite(end)
                or start != previous or end <= start or end > duration):
            raise ValueError(f'Invalid section bounds: {track["path"]}')
        previous = end
    if duration - previous > .2:
        raise ValueError(f'Section timings do not cover audio: {track["path"]}')
    return sections


def render(track, prior=None, force=False, verify_only=False):
    destination = SITE / track['path']
    cached = (prior and prior.get('sourceHash') == track['sourceHash']
              and prior.get('path') == track['path'] and destination.is_file())
    if verify_only and not cached:
        raise ValueError(f'Missing or stale audio: {destination}')
    if cached and not force:
        try:
            duration = verify(destination)
            sections = validate_sections(track, prior.get('sections'), duration)
            return {**track, 'duration': duration, 'sections': sections}
        except (ValueError, subprocess.SubprocessError):
            if verify_only:
                raise
    with tempfile.TemporaryDirectory(prefix='.render-', dir=OUTPUT) as temporary:
        folder = Path(temporary)
        samples = 0
        sections = []
        with (folder / 'speech.pcm').open('wb') as joined:
            for section in track['sections']:
                (folder / 'section.txt').write_text(pronounce(section['text']), encoding='utf-8')
                run(['say', '-v', VOICE, '-r', str(RATE), '-f', str(folder / 'section.txt'),
                     '-o', str(folder / 'section.aiff')])
                run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                     '-i', str(folder / 'section.aiff'), '-ac', '1', '-ar', str(SAMPLE_RATE),
                     '-f', 's16le', str(folder / 'section.pcm')])
                pcm = (folder / 'section.pcm').read_bytes()
                if not pcm or len(pcm) % 2:
                    raise ValueError(f'Invalid PCM section: {track["path"]}')
                start = round(samples / SAMPLE_RATE, 6)
                samples += len(pcm) // 2
                sections.append({**section, 'start': start, 'end': round(samples / SAMPLE_RATE, 6)})
                joined.write(pcm)
        encoded = folder / 'speech.mp3'
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
             '-f', 's16le', '-ar', str(SAMPLE_RATE), '-ac', '1', '-i', str(folder / 'speech.pcm'),
             '-map_metadata', '-1', '-ac', '1', '-ar', str(SAMPLE_RATE),
             '-codec:a', 'libmp3lame', '-b:a', '48k', str(encoded)])
        duration = verify(encoded)
        validate_sections(track, sections, duration)
        encoded.replace(destination)
    return {**track, 'duration': duration, 'sections': sections}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--verify-only', action='store_true')
    group.add_argument('--force', action='store_true')
    args = parser.parse_args()
    for command in ('ffmpeg', 'ffprobe') + (() if args.verify_only else ('say',)):
        if not shutil.which(command):
            raise SystemExit(f'Required tool unavailable: {command}')
    tracks = source_tracks()
    OUTPUT.mkdir(exist_ok=True)
    manifest_path = OUTPUT / 'manifest.json'
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    prior = {t['id']: t for t in previous.get('tracks', [])}
    results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = [pool.submit(render, track, prior.get(track['id']), args.force, args.verify_only)
                for track in tracks]
        for count, job in enumerate(as_completed(jobs), 1):
            result = job.result()
            results[result['id']] = result
            if count % 20 == 0:
                print(f'Validated {count}/200 tracks', flush=True)
    ordered = [results[t['id']] for t in tracks]
    manifest = {'version': 1, 'voice': VOICE, 'rate': RATE, 'tracks': ordered}
    if not args.verify_only:
        temporary = OUTPUT / '.manifest.tmp'
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary.replace(manifest_path)
    duration = sum(t['duration'] for t in ordered)
    size = sum((SITE / t['path']).stat().st_size for t in ordered)
    print(f'PASS: 200 decoded, non-silent MP3s; {duration:.3f}s; {size:,} bytes')


if __name__ == '__main__':
    main()
