"""
Wake word + STT + TTS piece of the Pixie orchestrator (see
../ARCHITECTURE.md).

Listens continuously for a wake word, hits /wake for an instant "listening"
indicator on the face, records the utterance that follows (stopping on real
silence, not a fixed timer), transcribes it, and forwards it to the brain
(server.js's /chat, which also handles the Arduino serial write). Speaks
the reply back with Pocket TTS.

Wake word is a custom-trained "pixie" openWakeWord model (see
wakeword_training/train.py: synthetic TTS positives + a curated negative
feature set, later mixed with real recordings of Akshat's voice), plus a
custom verifier model (wakeword_training/train_verifier.py) that filters
the base model's activations against real voice samples and real
background-noise recordings -- the base model alone was scoring high-
confidence false accepts on background talking/TV near the mic.
"""

import collections
import sys
import time
from datetime import datetime

# Windows console/redirected-file output defaults to cp1252, which can't
# encode emoji the brain sometimes puts in replies -- that crashed the whole
# pipeline on a log line. Force UTF-8 so any reply text is safe to print.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import requests
import sounddevice as sd
import webrtcvad
from faster_whisper import WhisperModel
from openwakeword.model import Model
from pocket_tts import TTSModel

WAKE_WORD = "pixie"
WAKE_WORD_MODEL_PATH = "pixie.onnx"
VERIFIER_MODEL_PATH = "pixie_verifier.pkl"  # secondary speaker-conditioned filter, see wakeword_training/train_verifier.py
VERIFIER_THRESHOLD = 0.3  # openWakeWord's own recommended default for custom verifiers
DETECTION_THRESHOLD = 0.5  # base-model gate before the verifier runs -- verifier does the real filtering now, so this can relax back down
MIN_WORDS = 2  # a 1-word transcript is almost always noise scraping past the wake threshold, not a real command
NO_SPEECH_PROB_THRESHOLD = 0.6  # discard segments Whisper itself isn't confident contain speech
SAMPLE_RATE = 16000
WAKE_CHUNK = 1280  # openWakeWord expects 80ms chunks at 16kHz
VAD_FRAME_MS = 30  # webrtcvad only accepts 10/20/30ms frames
VAD_FRAME_SAMPLES = int(SAMPLE_RATE * VAD_FRAME_MS / 1000)
SILENCE_TIMEOUT_MS = 800  # stop recording after this much trailing silence
MAX_UTTERANCE_MS = 10000  # safety cap so a stuck mic can't hang forever
CHAT_URL = "http://localhost:4141/chat"
WIDGET_URL = "http://localhost:4141/widget"
WAKE_URL = "http://localhost:4141/wake"
TTS_VOICE = "voice_refs/rachel.flac"  # cloned from a LibriVox narrator clip
MIC_NAME_HINT = "USB PnP"  # pin to the USB mic explicitly, not whatever Windows currently defaults to


def find_mic_device():
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and MIC_NAME_HINT in dev["name"]:
            return idx
    return None  # falls back to system default input device


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {msg}", flush=True)


def record_until_silence(stream, vad, preroll=None):
    # openWakeWord needs to accumulate confidence over several chunks before
    # crossing threshold (observed ~900ms from first rising score to
    # detection) -- if you say the wake word and your question as one
    # continuous phrase, the start of the question gets spoken (and its
    # audio discarded by the wake-detection loop) before recording even
    # starts. preroll is the last ~1s buffered during wake-listening,
    # prepended here so that speech isn't lost.
    frames = [preroll] if preroll is not None else []
    silence_ms = 0
    speech_started = False
    elapsed_ms = 0
    while elapsed_ms < MAX_UTTERANCE_MS:
        frame, _ = stream.read(VAD_FRAME_SAMPLES)
        frame = frame.flatten()
        frames.append(frame.copy())
        is_speech = vad.is_speech(frame.tobytes(), SAMPLE_RATE)
        elapsed_ms += VAD_FRAME_MS
        if is_speech:
            speech_started = True
            silence_ms = 0
        elif speech_started:
            silence_ms += VAD_FRAME_MS
            if silence_ms >= SILENCE_TIMEOUT_MS:
                break
    return np.concatenate(frames)


def transcribe(stt_model, audio_int16):
    t0 = time.monotonic()
    audio_float = audio_int16.astype(np.float32) / 32768.0
    # beam_size=5 (the default) does 5x the forward passes for a marginal
    # accuracy gain -- greedy decoding (beam_size=1) is the standard
    # real-time tradeoff and was costing several extra seconds per turn here.
    segments, _ = stt_model.transcribe(audio_float, language="en", beam_size=1, condition_on_previous_text=False)
    # Whisper hallucinates plausible-sounding text on silence/near-silence
    # (well-documented quirk -- a lot of its training data is YouTube
    # content, so it defaults to things like "thank you"). no_speech_prob
    # is Whisper's own confidence that a segment isn't real speech at all;
    # drop those instead of acting on fabricated text.
    real_segments = [seg for seg in segments if seg.no_speech_prob < NO_SPEECH_PROB_THRESHOLD]
    text = " ".join(seg.text for seg in real_segments).strip()
    log(f"transcribe() took {time.monotonic() - t0:.2f}s")
    return text


def clear_thinking():
    # No real reply is coming (nothing heard, or /chat failed before it could
    # sendEmotionToArduino) -- without this, the thinking dots stay stuck on
    # screen until the next real interaction.
    try:
        requests.post(WIDGET_URL, json={"command": "neutral"}, timeout=2)
    except requests.RequestException as e:
        log(f"clear-thinking POST failed: {e}")


def ask_pixie(text):
    t0 = time.monotonic()
    try:
        r = requests.post(CHAT_URL, json={"message": text}, timeout=60)
        log(f"ask_pixie() /chat round trip took {time.monotonic() - t0:.2f}s")
        return r.json()
    except requests.RequestException as e:
        log(f"ask_pixie() failed after {time.monotonic() - t0:.2f}s: {e}")
        return {"error": str(e)}


def speak(tts_model, voice_state, text):
    t0 = time.monotonic()
    audio = tts_model.generate_audio(voice_state, text)
    t1 = time.monotonic()
    log(f"TTS generate_audio() took {t1 - t0:.2f}s")
    sd.play(audio.numpy(), samplerate=tts_model.sample_rate)
    sd.wait()
    log(f"TTS playback took {time.monotonic() - t1:.2f}s")


def is_time_trigger(text):
    # Exact-phrase matching was too brittle -- "what is the time" doesn't
    # contain the substring "what time". Just check "time" shows up
    # alongside a question/request word; broader, but a false positive
    # here just means Pixie answers with the time unprompted, harmless.
    lower = text.lower()
    return "time" in lower and any(w in lower for w in ("what", "tell me", "current"))


def handle_time(tts_model, voice_state):
    # Deterministic path: no brain call at all, just the system clock --
    # this is what "be very fast since it's deterministic" means in practice.
    now = datetime.now()
    display = now.strftime("%I:%M").lstrip("0")
    spoken = now.strftime("%I:%M %p").lstrip("0")
    t0 = time.monotonic()
    try:
        requests.post(WIDGET_URL, json={"command": f"time:{display}"}, timeout=5)
        log(f"widget POST took {time.monotonic() - t0:.2f}s")
    except requests.RequestException as e:
        log(f"Failed to push clock widget after {time.monotonic() - t0:.2f}s: {e}")
    speak(tts_model, voice_state, f"It's {spoken}")


def main():
    log("Loading models...")
    oww_model = Model(
        wakeword_models=[WAKE_WORD_MODEL_PATH],
        custom_verifier_models={WAKE_WORD: VERIFIER_MODEL_PATH},
        custom_verifier_threshold=VERIFIER_THRESHOLD,
    )
    stt_model = WhisperModel("base.en", device="cpu", compute_type="int8")
    tts_model = TTSModel.load_model()
    voice_state = tts_model.get_state_for_audio_prompt(TTS_VOICE)
    vad = webrtcvad.Vad(3)  # was 2 -- flagging ~2s of ambient noise as speech on every false wake trigger

    mic_device = find_mic_device()
    if mic_device is not None:
        log(f"Using mic: {sd.query_devices(mic_device)['name']}")
    else:
        log(f'No device matching "{MIC_NAME_HINT}" found, falling back to system default input')

    # ~1s of raw audio (12 * 80ms chunks), always kept current -- wake
    # detection takes ~900ms of accumulating confidence to fire, and
    # whatever's said during that window would otherwise never reach STT.
    preroll_buffer = collections.deque(maxlen=12)

    log(f'Listening for wake word "{WAKE_WORD}"...')
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=WAKE_CHUNK, device=mic_device) as stream:
        while True:
            chunk, _ = stream.read(WAKE_CHUNK)
            chunk = chunk.flatten()
            preroll_buffer.append(chunk.copy())
            prediction = oww_model.predict(chunk)
            score = prediction[WAKE_WORD]
            if score > 0.3:
                # Below-threshold scores too, so we can see how close real
                # attempts get instead of guessing blind when nothing fires.
                log(f"wake score: {score:.3f}")
            if score > DETECTION_THRESHOLD:
                turn_t0 = time.monotonic()
                oww_model.reset()
                log(f"Wake word detected (score={score:.3f})")

                # Instant "listening" indicator (small red dot overlay, wakes
                # from sleep if needed) fired before STT/brain even start, so
                # there's visible feedback right away instead of a dead pause.
                wake_t0 = time.monotonic()
                try:
                    requests.post(WAKE_URL, timeout=2)
                except requests.RequestException as e:
                    log(f"wake POST failed: {e}")
                log(f"wake POST took {time.monotonic() - wake_t0:.2f}s")

                preroll = np.concatenate(list(preroll_buffer)) if preroll_buffer else None
                rec_t0 = time.monotonic()
                utterance = record_until_silence(stream, vad, preroll=preroll)
                log(f"record_until_silence() took {time.monotonic() - rec_t0:.2f}s ({len(utterance) / SAMPLE_RATE:.2f}s of audio)")

                # Recording's done, switch to the "thinking" loader while
                # STT/brain (or the deterministic path) do their thing.
                try:
                    requests.post(WIDGET_URL, json={"command": "thinking"}, timeout=2)
                except requests.RequestException as e:
                    log(f"thinking POST failed: {e}")

                text = transcribe(stt_model, utterance)
                log(f"Heard: {text!r}")
                if text and len(text.split()) < MIN_WORDS:
                    log(f"Discarding as noise (< {MIN_WORDS} words)")
                    text = ""
                if text and is_time_trigger(text):
                    handle_time(tts_model, voice_state)
                elif text:
                    result = ask_pixie(text)
                    log(f"Pixie: {result}")
                    if "reply" in result:
                        speak(tts_model, voice_state, result["reply"])
                    else:
                        clear_thinking()
                else:
                    clear_thinking()
                log(f"TOTAL turn time: {time.monotonic() - turn_t0:.2f}s")
                oww_model.reset()
                preroll_buffer.clear()  # avoid prepending stale pre-previous-turn audio next time
                log(f'Listening for wake word "{WAKE_WORD}"...')


if __name__ == "__main__":
    main()
