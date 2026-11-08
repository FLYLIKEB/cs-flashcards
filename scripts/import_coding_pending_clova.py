#!/usr/bin/env python3
"""Plan remaining local narration, then validate/import ordered CLOVA sentence ZIPs.

plan --output tmp/coding-pending-clova
import --plan .../plan.json --batch 1 --zip export.zip --report .../validated.json
import [same arguments] --apply --confirm-order

Paste batch-NN.txt lines in exact order, export per-sentence MP3s with no samples.
A dry-run receipt is mandatory before apply. No provider calls are made here.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import wave
import zipfile
try:
    from scripts import import_coding_clova_zip as clova
except ModuleNotFoundError:
    import import_coding_clova_zip as clova
importer, renderer, ROOT = clova.importer, clova.renderer, clova.ROOT


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_plan(lessons, manifest, budget=900):
    entries = {x['id']: x for x in manifest['lessons']}
    units = []
    for lesson in lessons:
        for index, scene in enumerate(lesson['scenes']):
            old = entries[lesson['id']]['scenes'][index]
            provenance = old.get('provenance', {})
            full = provenance.get('provider', 'local') == 'local'
            count = len(scene['segments']) if full else scene.get('introCueCount', 0) if provenance.get('introProvider') == 'local' else 0
            if not count:
                continue
            parts = renderer.narration_segments(scene)[:count]
            units.append({'lesson': lesson['id'], 'scene': index + 1, 'kind': 'full' if full else 'prefix',
                          'count': count, 'sceneHash': importer.digest(scene), 'sourceClipHash': importer.digest(old),
                          'speechHash': importer.digest([p['speech'] for p in parts]), 'segments': parts,
                          'estimatedSeconds': round(old['cues'][count - 1]['end'], 3)})
    batches, current, seconds = [], [], 0
    for unit in units:
        if unit['estimatedSeconds'] > budget:
            raise ValueError('A scene exceeds batch budget')
        if current and seconds + unit['estimatedSeconds'] > budget:
            batches.append(current); current, seconds = [], 0
        current.append(unit); seconds += unit['estimatedSeconds']
    if current:
        batches.append(current)
    return {'version': 1, 'maxDecodedSeconds': 1800, 'planningBudgetSeconds': budget,
            'batches': [{'id': i + 1, 'units': batch} for i, batch in enumerate(batches)]}


def write_plan(plan, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n')
    for batch in plan['batches']:
        rows = []
        for unit in batch['units']:
            for cue, part in enumerate(unit['segments']):
                rows.append({'track': len(rows) + 1, 'lesson': unit['lesson'], 'scene': unit['scene'],
                             'cue': cue, 'speech': part['speech'], 'speechHash': importer.digest(part['speech'])})
        prefix = output / f"batch-{batch['id']:02d}"
        prefix.with_suffix('.txt').write_text('\n'.join(row['speech'] for row in rows) + '\n')
        prefix.with_suffix('.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
        print(f"Batch {batch['id']}: {len(rows)} tracks, {sum(len(r['speech']) for r in rows)} characters, "
              f"{sum(u['estimatedSeconds'] for u in batch['units']):.2f}s existing audio")


def validate_unit(unit, lesson, old):
    scene = lesson['scenes'][unit['scene'] - 1]
    if importer.digest(scene) != unit['sceneHash'] or importer.digest(old) != unit['sourceClipHash']:
        raise ValueError('Authored content or source audio changed; regenerate the pending plan')
    expected = renderer.narration_segments(scene)[:unit['count']]
    if expected != unit['segments'] or importer.digest([p['speech'] for p in expected]) != unit['speechHash']:
        raise ValueError('Ordered speech mapping differs from authored segments')
    return scene


def append_preserved_body(prefix_wav, source, old, count, scene, prefix_cues, encoded, work):
    """Trim only the old local prefix, retain the existing AI body and its cue spacing."""
    boundary = old['cues'][count]['start']
    body = work / 'preserved-body.wav'
    renderer.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
                  '-af', f'aresample=24000,atrim=start_sample={round(boundary * 24000)},asetpts=PTS-STARTPTS',
                  '-ac', '1', '-c:a', 'pcm_s16le', str(body)], timeout=60)
    combined = work / 'combined.wav'
    with wave.open(str(prefix_wav), 'rb') as prefix, wave.open(str(body), 'rb') as tail, wave.open(str(combined), 'wb') as output:
        prefix_seconds = prefix.getnframes() / prefix.getframerate()
        output.setparams(prefix.getparams())
        output.writeframes(prefix.readframes(prefix.getnframes()))
        output.writeframes(tail.readframes(tail.getnframes()))
    renderer.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(combined),
                  '-c:a', 'libmp3lame', '-b:a', '128k', str(encoded)], timeout=60)
    duration = renderer.verify(encoded)
    renderer.audible(encoded)
    if abs(duration - (prefix_seconds + old['duration'] - boundary)) > .15:
        raise ValueError('Preserved AI body duration changed unexpectedly')
    starts = [c['start'] for c in prefix_cues] + [prefix_seconds + c['start'] - boundary for c in old['cues'][count:]]
    return duration, importer.make_cues(scene, starts, duration)


def import_batch(plan, batch_id, archive_path, lessons, output, receipt_path, apply=False, confirm_order=False, skip=0):
    if skip != 0:
        raise ValueError('Pending batches require exactly zero sample tracks')
    batch = next(b for b in plan['batches'] if b['id'] == batch_id)
    expected = sum(u['count'] for u in batch['units'])
    identity = {'planHash': importer.digest(plan), 'batch': batch_id, 'archiveHash': file_hash(archive_path), 'tracks': expected}
    if apply:
        if not confirm_order:
            raise ValueError('Confirm downloaded sentence order against the batch track map before applying')
        if not receipt_path.exists() or json.loads(receipt_path.read_text()).get('identity') != identity:
            raise ValueError('A matching successful dry-run receipt is required before apply')
    manifest_path = output / 'manifest.json'
    original = manifest_path.read_bytes()
    manifest = json.loads(original)
    entries = {x['id']: x for x in manifest['lessons']}
    authored = {x['id']: x for x in lessons}
    for unit in batch['units']:
        validate_unit(unit, authored[unit['lesson']], entries[unit['lesson']]['scenes'][unit['scene'] - 1])
    with zipfile.ZipFile(archive_path) as archive, tempfile.TemporaryDirectory(prefix='pending-clova-', dir=output) as directory:
        work = Path(directory)
        tracks = clova.ordered_tracks(archive, expected, 0)
        cursor, decoded_total, staged = 0, 0.0, []
        for unit in batch['units']:
            lesson = authored[unit['lesson']]; entry = entries[unit['lesson']]
            scene = lesson['scenes'][unit['scene'] - 1]; old = entry['scenes'][unit['scene'] - 1]
            count = unit['count']; parts = unit['segments']
            selected = tracks[cursor:cursor + count]; cursor += count
            encoded = work / 'scene.mp3'
            subset = {'segments': parts, 'narration': ' '.join(p['text'] for p in parts)}
            duration, cues = clova.render_scene(archive, selected, subset, encoded, work)
            with wave.open(str(work / 'joined.wav'), 'rb') as pcm:
                decoded_total += pcm.getnframes() / pcm.getframerate()
            if decoded_total > min(1800, plan['maxDecodedSeconds']):
                raise ValueError('Downloaded batch exceeds the 30-minute project limit')
            if unit['kind'] == 'prefix':
                source = output / Path(old['src']).name
                expected_hash = old.get('provenance', {}).get('audioHash')
                if expected_hash and file_hash(source) != expected_hash:
                    raise ValueError('Preserved source audio hash mismatch')
                duration, cues = append_preserved_body(work / 'joined.wav', source, old, count, scene, cues, encoded, work)
                provenance = deepcopy(old.get('provenance', {}))
                provenance.update({'introProvider': 'clova', 'introVoice': '아라', 'preservedBodySrc': old['src'],
                                   'timing': 'measured-clova-prefix-and-preserved-body-cues'})
            else:
                provenance = {'provider': 'clova', 'voice': '아라', 'timing': 'measured-segments'}
                if scene.get('introCueCount'):
                    provenance.update({'introProvider': 'clova', 'introVoice': '아라'})
            audio_hash = file_hash(encoded)
            provenance.update({'audioHash': audio_hash, 'speechHash': importer.digest([p['speech'] for p in scene['segments']]),
                               'importPlanHash': identity['planHash'], 'importArchiveHash': identity['archiveHash']})
            if scene.get('introCueCount'):
                provenance.update({'introCueCount': scene['introCueCount'], 'titleCueCount': scene.get('titleCueCount', 0),
                                   'titleProvider': 'clova', 'titleVoice': '아라'})
            name = f"{unit['lesson']:02d}-{unit['scene']:02d}-{audio_hash[:12]}.mp3"
            encoded.rename(work / name); staged.append(name)
            entry['scenes'][unit['scene'] - 1] = {'src': f'/static/coding-audio/{name}', 'duration': round(duration, 3), 'cues': cues, 'provenance': provenance}
            entry['sourceHashKind'] = 'ai-import-v1'; entry['sourceHash'] = importer.fingerprint(lesson, entry['scenes'])
        report = {'identity': identity, 'decodedSeconds': round(decoded_total, 3), 'scenes': len(staged), 'status': 'validated'}
        if apply:
            if manifest_path.read_bytes() != original:
                raise ValueError('Manifest changed during conversion; nothing applied')
            manifest['voice'] = 'Mixed'
            for name in staged:
                (work / name).replace(output / name)
            pending = work / 'manifest.json'
            pending.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
            pending.replace(manifest_path)
        else:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    make = commands.add_parser('plan'); make.add_argument('--output', type=Path, default=ROOT / 'tmp/coding-pending-clova')
    take = commands.add_parser('import')
    for name in ('plan', 'zip', 'report'):
        take.add_argument('--' + name, type=Path, required=True)
    take.add_argument('--batch', type=int, required=True)
    take.add_argument('--skip', type=int, default=0)
    take.add_argument('--apply', action='store_true'); take.add_argument('--confirm-order', action='store_true')
    args = parser.parse_args()
    lessons = json.loads((ROOT / 'static/coding-lessons.json').read_text())
    output = ROOT / 'static/coding-audio'
    if args.command == 'plan':
        write_plan(build_plan(lessons, json.loads((output / 'manifest.json').read_text())), args.output)
    else:
        print(json.dumps(import_batch(json.loads(args.plan.read_text()), args.batch, args.zip, lessons, output,
                                     args.report, args.apply, args.confirm_order, args.skip), ensure_ascii=False))


if __name__ == '__main__':
    main()
