"""
Records ambient background audio through the real USB mic, as negative
examples for the openWakeWord custom verifier -- see train_verifier.py.

Run this while whatever's causing false accepts (TV, talking, etc.) is
actually playing near the mic, so the verifier learns to reject exactly
that audio. Appends rather than overwrites, so run it multiple times
across different moments for variety.
"""

from pathlib import Path

import sounddevice as sd
import soundfile as sf

OUT_DIR = Path(__file__).parent / "negative_clips"
SAMPLE_RATE = 16000
DURATION_S = 15
MIC_NAME_HINT = "USB PnP"  # must match listen.py's runtime mic exactly


def find_mic_device():
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and MIC_NAME_HINT in dev["name"]:
            return idx
    return None


def main():
    OUT_DIR.mkdir(exist_ok=True)
    mic_device = find_mic_device()
    if mic_device is not None:
        print(f"Using mic: {sd.query_devices(mic_device)['name']}")
    else:
        print(f'No device matching "{MIC_NAME_HINT}" found, falling back to system default input')

    existing = len(list(OUT_DIR.glob("*.wav")))
    path = OUT_DIR / f"background_{existing:03d}.wav"
    print(f"Recording {DURATION_S}s of ambient background audio to {path}...")
    audio = sd.rec(int(DURATION_S * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=mic_device)
    sd.wait()
    sf.write(path, audio, SAMPLE_RATE)
    print("Done.")


if __name__ == "__main__":
    main()
