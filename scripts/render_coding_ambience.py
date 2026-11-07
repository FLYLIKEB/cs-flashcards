"""Render an original, seamless instrumental bed for spoken coding lessons.

Only the Python standard library is needed. The 60-second arrangement uses soft
additive electric-piano tones, slow pads and a sparse melody; no sampled music.
All notes and delay tails wrap around the loop instead of fading to silence.
"""
from array import array
import hashlib
import math
from pathlib import Path
import sys
import wave

RATE = 24000
SECONDS = 60
FRAMES = RATE * SECONDS
TAU = 2 * math.pi


def frequency(midi):
    return 440 * 2 ** ((midi - 69) / 12)


def add_note(mix, midi, start, duration, gain, instrument):
    """Place a gently enveloped note on the circular arrangement timeline."""
    pitch = frequency(midi)
    first = round(start * RATE)
    count = round(duration * RATE)
    attack = .055 if instrument == 'piano' else .09 if instrument == 'pluck' else 1.35
    release = .65 if instrument in ('piano', 'pluck') else 2.5
    for i in range(count):
        t = i / RATE
        # Raised-cosine envelopes avoid abrupt starts/ends and audible clicks.
        fade_in = .5 - .5 * math.cos(math.pi * min(1, t / attack))
        fade_out = .5 - .5 * math.cos(math.pi * min(1, (duration - t) / release))
        phase = TAU * pitch * t
        if instrument == 'piano':
            decay = math.exp(-t / 1.9)
            tone = (math.sin(phase) + .23 * math.exp(-t / .8) * math.sin(2 * phase)
                    + .075 * math.exp(-t / .45) * math.sin(4 * phase)) * decay
        elif instrument == 'pluck':
            tone = (math.sin(phase) + .12 * math.sin(2 * phase)) * math.exp(-t / .95)
        elif instrument == 'bass':
            tone = math.sin(phase) + .08 * math.sin(2 * phase)
        else:
            # Small detuning gives the sustained bed a gentle, unhurried texture.
            tone = .5 * math.sin(phase) + .5 * math.sin(phase * 1.0014)
            tone *= .94 + .06 * math.sin(TAU * .13 * t)
        mix[(first + i) % FRAMES] += gain * fade_in * fade_out * tone


def render():
    mix = array('d', [0]) * FRAMES
    # Eight two-bar changes at 64 BPM: Cmaj9, Am9, Fmaj9, G6, Cmaj9,
    # Em7, Fmaj9, G6. Voicings stay in a narrow register beneath narration.
    chords = [
        (36, (55, 59, 62, 64)), (33, (52, 55, 59, 60)),
        (29, (53, 57, 60, 64)), (31, (55, 59, 62, 64)),
        (36, (55, 59, 62, 64)), (28, (52, 55, 59, 62)),
        (29, (53, 57, 60, 64)), (31, (55, 59, 62, 64)),
    ]
    for bar, (bass, notes) in enumerate(chords):
        start = bar * 7.5
        add_note(mix, bass + 12, start - .6, 9.5, .055, 'bass')
        for index, note in enumerate(notes):
            add_note(mix, note, start - .7, 9.6, .017, 'pad')
            add_note(mix, note, start + .2 + index * .045, 5.2, .09, 'piano')
            add_note(mix, note, start + 4 + index * .055, 3.8, .038, 'piano')
    # A short original, widely spaced motif; no beat, ticking or busy arpeggio.
    for start, note in ((2.1, 67), (5.9, 64), (12.8, 62), (19.8, 64),
                        (26.4, 62), (33.1, 67), (37.2, 64), (43.7, 62),
                        (49.9, 60), (56.2, 62)):
        add_note(mix, note, start, 3.6, .048, 'pluck')
    # Quiet, circular delay tails provide space without interrupting the loop.
    dry = array('d', mix)
    for delay, gain in ((.187, .10), (.313, .065), (.487, .035)):
        shift = round(delay * RATE)
        for i in range(FRAMES):
            mix[i] += dry[(i - shift) % FRAMES] * gain
    # A warm low-pass with a full-period warm-up keeps the seam continuous.
    alpha = 1 - math.exp(-TAU * 2400 / RATE)
    previous = 0.0
    for value in mix:
        previous += alpha * (value - previous)
    for i, value in enumerate(mix):
        previous += alpha * (value - previous)
        mix[i] = previous
    mean = sum(mix) / FRAMES
    rms = math.sqrt(sum((value - mean) ** 2 for value in mix) / FRAMES)
    peak = max(abs(value - mean) for value in mix)
    scale = min(.115 / rms, .55 / peak)
    pcm = array('h', (round((value - mean) * scale * 32767) for value in mix))
    peak = max(abs(value) for value in pcm) / 32768
    rms = math.sqrt(sum(value * value for value in pcm) / FRAMES) / 32768
    seam = abs(pcm[0] - pcm[-1]) / 32768
    assert .05 < rms < .16 and peak < .56, 'Unexpected loudness or clipping'
    assert seam < .01, 'Loop boundary has an audible discontinuity'
    if sys.byteorder != 'little':
        pcm.byteswap()
    path = Path(__file__).resolve().parents[1] / 'static/coding-audio/focus-explainer.wav'
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes(pcm.tobytes())
    print(f'{path.name}: {SECONDS}s, {RATE}Hz mono, RMS {20 * math.log10(rms):.2f} dBFS, '
          f'peak {20 * math.log10(peak):.2f} dBFS, seam delta {seam:.6f}')
    print(f'SHA256 {hashlib.sha256(path.read_bytes()).hexdigest()}')


if __name__ == '__main__':
    render()
