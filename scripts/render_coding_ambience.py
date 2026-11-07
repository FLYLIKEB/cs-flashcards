"""Create a quiet, seamless brown-noise bed locally; no external recordings."""
from array import array
from pathlib import Path
import math
import random
import wave

RATE = 24000
rng = random.Random(48)
value = 0.0
samples = []
for _ in range(RATE * 30):
    value = (value + rng.uniform(-1, 1) * .02) / 1.02
    samples.append(value)
# Blend the end into the beginning; both joins retain adjacent source samples.
blend = [samples[-RATE + i] * (1 - i / RATE) + samples[i] * (i / RATE) for i in range(RATE)]
samples = blend + samples[RATE:-RATE]
mean = sum(samples) / len(samples)
samples = [x - mean for x in samples]
rms = math.sqrt(sum(x*x for x in samples) / len(samples))
scale = min(.14 / rms, .65 / max(abs(x) for x in samples))
pcm = array('h', (round(x * scale * 32767) for x in samples))
path = Path(__file__).resolve().parents[1] / 'static/coding-audio/focus-brown.wav'
with wave.open(str(path), 'wb') as output:
    output.setnchannels(1)
    output.setsampwidth(2)
    output.setframerate(RATE)
    output.writeframes(pcm.tobytes())
print(f'{path.name}: {len(samples) / RATE:.0f}s seamless loop')
