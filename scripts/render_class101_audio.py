#!/usr/bin/env python3
"""Render 200 Korean interview MP3s with local macOS Yuna and FFmpeg.

Run: python3 scripts/render_class101_audio.py [--verify-only] [--force]
Manifest schema: {version, voice, rate, tracks: [{id, type, text, speech,
sourceHash, duration, path}]}; paths are relative to the interview page.
Confirmation notes are not narrated. The text field preserves the plain-text
answer; speech additionally includes the question number and pronunciation aids.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

try:
    from .build_class101_interview import ROOT, parse_answers, parse_questions
except ImportError:
    from build_class101_interview import ROOT, parse_answers, parse_questions


OUTPUT = ROOT / "audio"
VOICE, RATE = "Yuna", 185
PRONUNCIATIONS = {
    "API": "에이피아이", "SQL": "에스큐엘", "DB": "디비",
    "JPA": "제이피에이", "TPS": "티피에스", "PG": "피지",
    "MDC": "엠디씨", "DTO": "디티오", "TTL": "티티엘",
    "JDBC": "제이디비씨", "HTTP": "에이치티티피", "ID": "아이디",
    "CPU": "씨피유", "OOM": "오오엠", "SQS": "에스큐에스",
    "JSON": "제이슨", "UX": "유엑스", "SMS": "에스엠에스",
    "N+1": "엔 플러스 원", "p95": "피 구십오", "p99": "피 구십구",
    "MySQL": "마이 에스큐엘", "BigDecimal": "빅 데시멀",
    "Next.js": "넥스트 제이에스", "Node.js": "노드 제이에스",
    "NestJS": "네스트 제이에스", "TypeScript": "타입스크립트",
    "TypeORM": "타입 오알엠", "JavaScript": "자바스크립트",
    "WebSocket": "웹소켓", "Spring": "스프링", "Java": "자바",
    "FFmpeg": "에프에프 엠펙", "B마트": "비마트",
}


def plain_text(body):
    body = " ".join(line.strip() for line in body.splitlines()
                    if not line.lstrip().startswith(">"))
    body = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", body)
    return " ".join(body.replace("`", "").replace("**", "").split())


def pronounce(text):
    for word in sorted(PRONUNCIATIONS, key=len, reverse=True):
        text = re.sub(r"(?<![A-Za-z])" + re.escape(word) + r"(?![A-Za-z])",
                      PRONUNCIATIONS[word], text)
    return re.sub(r"(?<=\d)ms(?![A-Za-z])", "밀리초", text).replace("→", "에서 ")


def source_tracks():
    groups = parse_questions((ROOT / "questions.md").read_text(encoding="utf-8"))
    answers = parse_answers([ROOT / name for name in (
        "answers-01-30.md", "answers-31-60.md", "answers-61-100.md")])
    tracks = []
    for _, questions in groups:
        for number, question in questions:
            for kind, label, body in (("question", "질문", question),
                                      ("answer", "답변", answers[number])):
                text = plain_text(body)
                speech = pronounce(f"{number}번 {label}. {text}")
                fingerprint = json.dumps([speech, VOICE, RATE, "mp3-48k-mono-v1"],
                                         ensure_ascii=False).encode()
                tracks.append({"id": number, "type": kind, "text": text,
                               "speech": speech,
                               "sourceHash": hashlib.sha256(fingerprint).hexdigest(),
                               "path": f"audio/{kind}-{number:03}.mp3"})
    assert len(tracks) == 200
    assert all(t["text"] and "확인 메모:" not in t["speech"] for t in tracks)
    assert [(t["id"], t["type"]) for t in tracks] == [
        (n, kind) for n in range(1, 101) for kind in ("question", "answer")]
    return tracks


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=180)


def verify(path):
    metadata = json.loads(run(["ffprobe", "-v", "error", "-show_streams",
                               "-show_format", "-of", "json", str(path)]).stdout)
    streams = metadata.get("streams", [])
    seconds = float(metadata["format"]["duration"])
    if (len(streams) != 1 or streams[0].get("codec_name") != "mp3"
            or not math.isfinite(seconds) or seconds <= 0.5):
        raise ValueError(f"Invalid audio: {path}")
    decoded = run(["ffmpeg", "-hide_banner", "-nostdin", "-xerror", "-i", str(path),
                   "-af", "volumedetect", "-f", "null", "-"])
    volume = re.search(r"mean_volume: (-?[\d.]+) dB", decoded.stderr)
    if not volume or not math.isfinite(float(volume.group(1))):
        raise ValueError(f"Silent audio: {path}")
    return seconds


def render(track, prior, force, verify_only):
    destination = ROOT / track["path"]
    cached = prior and prior.get("sourceHash") == track["sourceHash"] and destination.exists()
    if verify_only and not cached:
        raise ValueError(f"Missing or stale audio: {destination}")
    if cached and not force:
        try:
            return {**track, "duration": verify(destination)}
        except (ValueError, subprocess.SubprocessError):
            if verify_only:
                raise
    with tempfile.TemporaryDirectory(prefix=".render-", dir=OUTPUT) as temporary:
        folder = Path(temporary)
        (folder / "speech.txt").write_text(track["speech"], encoding="utf-8")
        run(["say", "-v", VOICE, "-r", str(RATE), "-f", str(folder / "speech.txt"),
             "-o", str(folder / "speech.aiff")])
        encoded = folder / "speech.mp3"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
             "-i", str(folder / "speech.aiff"), "-map_metadata", "-1", "-ac", "1",
             "-ar", "24000", "-codec:a", "libmp3lame", "-b:a", "48k", str(encoded)])
        duration = verify(encoded)
        encoded.replace(destination)
    return {**track, "duration": duration}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--verify-only", action="store_true")
    options.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for binary in ("ffmpeg", "ffprobe") + (() if args.verify_only else ("say",)):
        if not shutil.which(binary):
            raise SystemExit(f"Required local tool is unavailable: {binary}")
    assert plain_text("**테스트** `API`\n\n> 확인 메모: 제외") == "테스트 API"
    assert pronounce("API와 MySQL, 18ms") == "에이피아이와 마이 에스큐엘, 18밀리초"
    assert pronounce("909ms에서 18ms로") == "909밀리초에서 18밀리초로"
    tracks = source_tracks()
    OUTPUT.mkdir(exist_ok=True)
    manifest_path = OUTPUT / "manifest.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    prior = {(t["id"], t["type"]): t for t in previous.get("tracks", [])}
    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(render, t, prior.get((t["id"], t["type"])),
                            args.force, args.verify_only) for t in tracks]
        for count, job in enumerate(as_completed(jobs), 1):
            result = job.result()
            results[(result["id"], result["type"])] = result
            if count % 20 == 0:
                print(f"Validated {count}/200 tracks", flush=True)
    ordered = [results[(t["id"], t["type"])] for t in tracks]
    manifest = {"version": 1, "voice": VOICE, "rate": RATE, "tracks": ordered}
    if not args.verify_only:
        temporary = OUTPUT / ".manifest.tmp"
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        temporary.replace(manifest_path)
    duration = sum(t["duration"] for t in ordered)
    size = sum((ROOT / t["path"]).stat().st_size for t in ordered)
    print(f"PASS: 200 decoded, non-silent MP3s; {duration:.1f}s; {size:,} bytes")


if __name__ == "__main__":
    main()
