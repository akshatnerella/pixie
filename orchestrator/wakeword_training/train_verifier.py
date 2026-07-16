"""
Trains an openWakeWord custom verifier model -- a lightweight secondary
classifier that filters the base "pixie" model's activations, rejecting
ones that don't match the real positive recordings. Built specifically to
reject high-confidence false accepts on background TV/talk audio near the
mic (the base model was scoring those 0.8-0.97, well past any sane
threshold on the base model alone -- see openWakeWord's own docs on
custom verifier models for why a secondary speaker-conditioned filter is
the recommended fix for this exact scenario).

Positives: reuse the real "pixie" recordings from record_positives.py.
Negatives: the actual interfering background audio, captured live via
record_negative.py while it was playing.
"""

from pathlib import Path

import openwakeword

OUT_DIR = Path(__file__).parent
REAL_POSITIVES_DIR = OUT_DIR / "real_positives"
NEGATIVE_CLIPS_DIR = OUT_DIR / "negative_clips"
OUTPUT_PATH = OUT_DIR / "pixie_verifier.pkl"


def main():
    # Docs recommend keeping positive examples small (model capacity) --
    # a handful of the 20 real recordings is plenty.
    positive_clips = sorted(str(p) for p in REAL_POSITIVES_DIR.glob("*.wav"))[:10]
    negative_clips = sorted(str(p) for p in NEGATIVE_CLIPS_DIR.glob("*.wav"))
    print(f"Training verifier with {len(positive_clips)} positive / {len(negative_clips)} negative clips")

    openwakeword.train_custom_verifier(
        positive_reference_clips=positive_clips,
        negative_reference_clips=negative_clips,
        output_path=str(OUTPUT_PATH),
        model_name="pixie.onnx",
    )
    print(f"Saved verifier to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
