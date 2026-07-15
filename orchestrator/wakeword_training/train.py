"""
One-off local training script for a custom "pixie" openWakeWord model.

Hobby-grade, not commercial-grade: uses a modest synthetic positive set
(Pocket TTS across its built-in voices) instead of thousands of examples,
and reuses davidscripka's pre-computed curated negative-feature set
(~11 hours, 185MB) instead of the full 17GB/2000-hour one. Expect a higher
false-accept rate than a polished production model -- upgrade path later is
a "custom verifier" trained on a few real recordings of Akshat saying
"pixie", per openWakeWord's own docs, if this turns out too false-accept-y
in practice.
"""

import collections
import urllib.request
from pathlib import Path

import numpy as np
import openwakeword.utils
import torch
from torch import nn
from pocket_tts import TTSModel

OUT_DIR = Path(__file__).parent
NEGATIVE_FEATURES_URL = "https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/validation_set_features.npy"
NEGATIVE_FEATURES_PATH = OUT_DIR / "negative_features.npy"
CATALOG_VOICES = [
    "cosette", "marius", "javert", "alba", "jean", "anna", "vera", "fantine",
    "charles", "paul", "eponine", "azelma", "george", "mary", "jane",
    "michael", "eve", "giovanni", "lola", "juergen", "rafael", "estelle",
]
PHRASE_VARIANTS = ["Pixie", "Pixie!", "Pixie."]
# The final training window is 16 embedding frames (1.28s), but the
# embedding model needs more raw audio context than that to produce 16
# frames at all (a 1.28s clip only yielded 7) -- generate a longer window
# and slice the last 16 frames of the resulting embedding sequence.
WINDOW_SECONDS = 4.0


def download_negative_features():
    if NEGATIVE_FEATURES_PATH.exists():
        print("Negative features already downloaded, skipping.")
        return
    print("Downloading curated negative feature set (~185MB)...")
    urllib.request.urlretrieve(NEGATIVE_FEATURES_URL, NEGATIVE_FEATURES_PATH)


def generate_positive_clips():
    print("Generating synthetic 'pixie' clips across catalog voices...")
    tts = TTSModel.load_model()
    clips = []
    for voice in CATALOG_VOICES:
        vs = tts.get_state_for_audio_prompt(voice)
        for phrase in PHRASE_VARIANTS:
            audio = tts.generate_audio(vs, phrase).numpy()
            clips.append((audio, tts.sample_rate))
    print(f"Generated {len(clips)} positive clips from {len(CATALOG_VOICES)} voices.")
    return clips


def resample_to_16k(audio, orig_sr):
    if orig_sr == 16000:
        return audio
    import scipy.signal
    n_samples = int(len(audio) * 16000 / orig_sr)
    return scipy.signal.resample(audio, n_samples).astype(np.float32)


def clips_to_windows(clips, window_seconds=WINDOW_SECONDS, target_sr=16000):
    """Pad/place each clip at a random offset within a fixed window, biased
    so the word ends within the last 200ms -- keeps the model confident
    right after the phrase finishes, per openWakeWord's own tutorial."""
    window_samples = int(window_seconds * target_sr)
    windows = []
    for audio, sr in clips:
        audio = resample_to_16k(audio, sr)
        if len(audio) >= window_samples:
            audio = audio[-window_samples:]
        else:
            max_start = window_samples - len(audio) - int(0.05 * target_sr)
            start = np.random.randint(0, max(1, max_start))
            padded = np.zeros(window_samples, dtype=np.float32)
            padded[start:start + len(audio)] = audio
            audio = padded
        windows.append(audio)
    stacked = np.stack(windows)
    # openWakeWord's embedding model expects 16-bit PCM ints, not float32
    return np.clip(stacked * 32768, -32768, 32767).astype(np.int16)


def main():
    openwakeword.utils.download_models()  # fresh venv, AudioFeatures needs its bundled models

    download_negative_features()
    negative_features = np.load(NEGATIVE_FEATURES_PATH).astype(np.float32)
    print(f"Loaded negative features: {negative_features.shape}")
    if negative_features.ndim == 2:
        # This file stores one 96-dim embedding per 80ms frame, not
        # pre-assembled (16, 96) windows like the full ACAV100M set --
        # group consecutive frames into 16-frame (1.28s) windows ourselves.
        n_windows = len(negative_features) // 16
        negative_features = negative_features[:n_windows * 16].reshape(n_windows, 16, 96)
        print(f"Reshaped into {negative_features.shape} windows")

    clips = generate_positive_clips()
    positive_audio = clips_to_windows(clips)

    print("Computing audio embeddings for positive clips (streamed, matching runtime exactly)...")
    # _get_embeddings() computes features in one batch pass over the whole
    # clip -- Model.predict() at runtime instead streams 1280-sample chunks
    # through AudioFeatures.__call__()/get_features(), which turned out to
    # produce different features for the same audio (sanity-tested model
    # scored ~0.95 on training-time batch features but only ~0.04 on the
    # exact same audio through real streaming inference). Replicating the
    # real streaming path here instead of the batch one, so training
    # features actually match what the model sees in production.
    F = openwakeword.utils.AudioFeatures()
    positive_features_list = []
    for a in positive_audio:
        F.reset()
        for i in range(0, len(a) - 1280, 1280):
            F(a[i:i + 1280])
        positive_features_list.append(F.get_features(16)[0])
    positive_features = np.stack(positive_features_list)
    print(f"Positive features: {positive_features.shape}")

    # First attempt used a 30x cap plus 10x negative loss-weighting on top
    # of it -- with only 66 positive examples, that was still enough
    # imbalance that the model collapsed to always predicting "not pixie"
    # (0.004 score on an actual "pixie" clip, indistinguishable from
    # unrelated speech). Tighter cap now, and dropping the extra weighting
    # entirely below -- let the model actually learn to discriminate first.
    max_negatives = len(positive_features) * 5
    if len(negative_features) > max_negatives:
        idx = np.random.choice(len(negative_features), max_negatives, replace=False)
        negative_features = negative_features[idx]
    print(f"Using {len(negative_features)} negative / {len(positive_features)} positive examples")

    X = np.vstack((negative_features, positive_features))
    y = np.array([0] * len(negative_features) + [1] * len(positive_features), dtype=np.float32)[..., None]

    dataset = torch.utils.data.TensorDataset(torch.from_numpy(X), torch.from_numpy(y))
    loader = torch.utils.data.DataLoader(dataset, batch_size=64, shuffle=True)

    layer_dim = 32
    model = nn.Sequential(
        nn.Flatten(),
        nn.Linear(X.shape[1] * X.shape[2], layer_dim),
        nn.LayerNorm(layer_dim),
        nn.ReLU(),
        nn.Linear(layer_dim, layer_dim),
        nn.LayerNorm(layer_dim),
        nn.ReLU(),
        nn.Linear(layer_dim, 1),
        nn.Sigmoid(),
    )

    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.BCELoss()
    n_epochs = 30
    history = collections.defaultdict(list)
    print(f"Training for {n_epochs} epochs...")
    X_t, y_t = torch.from_numpy(X), torch.from_numpy(y)
    for epoch in range(n_epochs):
        epoch_loss = 0.0
        for xb, yb in loader:
            optimizer.zero_grad()
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
        with torch.no_grad():
            all_pred = model(X_t)
            pos_score = all_pred[y_t == 1].mean().item()
            neg_score = all_pred[y_t == 0].mean().item()
        history["loss"].append(epoch_loss / len(loader))
        print(f"  epoch {epoch + 1}/{n_epochs}  loss={history['loss'][-1]:.4f}  "
              f"avg_pos_score={pos_score:.3f}  avg_neg_score={neg_score:.3f}")

    output_path = OUT_DIR / "pixie.onnx"
    model.eval()
    torch.onnx.export(model, torch.zeros((1, X.shape[1], X.shape[2])), f=str(output_path), dynamo=False)
    print(f"Exported model to {output_path}")


if __name__ == "__main__":
    main()
