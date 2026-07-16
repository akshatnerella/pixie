"""
Records real "pixie" samples through the actual USB mic, to mix into the
training set alongside the synthetic TTS positives in train.py.

The deployed model was trained entirely on synthetic voices and scored
Akshat's real attempts around 0.35-0.75 -- well under a usable threshold.
Real recordings from the actual mic/room/voice should close that gap.

Run this, then say "pixie" naturally (not shouted, not robotic) once per
prompt. Aim for 20+ takes with some variation in tone and distance from
the mic -- run it again later to add more, it appends rather than overwrites.
"""

from pathlib import Path

import sounddevice as sd
import soundfile as sf

OUT_DIR = Path(__file__).parent / "real_positives"
SAMPLE_RATE = 16000
CLIP_SECONDS = 1.5
NUM_CLIPS = 20
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
    print(f"Recording {NUM_CLIPS} real 'pixie' samples at {SAMPLE_RATE}Hz.")
    print("Say 'pixie' naturally, once, right after pressing Enter.\n")
    for i in range(existing, existing + NUM_CLIPS):
        input(f"[{i + 1}] Press Enter, then say 'pixie'...")
        audio = sd.rec(int(CLIP_SECONDS * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=mic_device)
        sd.wait()
        path = OUT_DIR / f"pixie_{i:03d}.wav"
        sf.write(path, audio, SAMPLE_RATE)
        print(f"  saved {path.name}")
    print(f"\nDone. {existing + NUM_CLIPS} total real samples in {OUT_DIR}")


if __name__ == "__main__":
    main()
