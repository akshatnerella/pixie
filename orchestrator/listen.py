"""
Wake word + STT + TTS piece of the Pixie orchestrator (see
../ARCHITECTURE.md).

Listens continuously for a wake word, plays an instant filler ("yeah?",
"what's up?"...) so it feels responsive, records the utterance that
follows (stopping on real silence, not a fixed timer), transcribes it, and
forwards it to the brain (server.js's /chat, which also handles the
Arduino serial write). Speaks the reply back with Pocket TTS.

Wake word is a custom-trained "pixie" openWakeWord model (see
wakeword_training/train.py) -- Picovoice's free tier was discontinued, so
this was trained locally instead: synthetic TTS positive examples +
davidscripka's pre-computed negative feature set. Hobby-grade, not
commercial-grade -- trained entirely on synthetic voices, never tested
against Akshat's actual voice through a real mic until now.
"""

import random

import numpy as np
import requests
import sounddevice as sd
import webrtcvad
from faster_whisper import WhisperModel
from openwakeword.model import Model
from pocket_tts import TTSModel

WAKE_WORD = "pixie"
WAKE_WORD_MODEL_PATH = "pixie.onnx"
DETECTION_THRESHOLD = 0.5
SAMPLE_RATE = 16000
WAKE_CHUNK = 1280  # openWakeWord expects 80ms chunks at 16kHz
VAD_FRAME_MS = 30  # webrtcvad only accepts 10/20/30ms frames
VAD_FRAME_SAMPLES = int(SAMPLE_RATE * VAD_FRAME_MS / 1000)
SILENCE_TIMEOUT_MS = 800  # stop recording after this much trailing silence
MAX_UTTERANCE_MS = 10000  # safety cap so a stuck mic can't hang forever
CHAT_URL = "http://localhost:4141/chat"
TTS_VOICE = "voice_refs/rachel.flac"  # cloned from a LibriVox narrator clip
FILLERS = ["Yeah?", "What's up?", "What up boss?", "Mmhm?", "I'm listening."]


def record_until_silence(stream, vad):
    frames = []
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
    audio_float = audio_int16.astype(np.float32) / 32768.0
    segments, _ = stt_model.transcribe(audio_float, language="en")
    return " ".join(seg.text for seg in segments).strip()


def ask_pixie(text):
    try:
        r = requests.post(CHAT_URL, json={"message": text}, timeout=60)
        return r.json()
    except requests.RequestException as e:
        return {"error": str(e)}


def speak(tts_model, voice_state, text):
    audio = tts_model.generate_audio(voice_state, text)
    sd.play(audio.numpy(), samplerate=tts_model.sample_rate)
    sd.wait()


def main():
    print("Loading models...", flush=True)
    oww_model = Model(wakeword_models=[WAKE_WORD_MODEL_PATH])
    stt_model = WhisperModel("base.en", device="cpu", compute_type="int8")
    tts_model = TTSModel.load_model()
    voice_state = tts_model.get_state_for_audio_prompt(TTS_VOICE)
    vad = webrtcvad.Vad(2)  # aggressiveness 0-3; 2 is a reasonable default

    print("Pre-generating filler responses...", flush=True)
    filler_audio = [tts_model.generate_audio(voice_state, f).numpy() for f in FILLERS]

    print(f'Listening for wake word "{WAKE_WORD}"...', flush=True)
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=WAKE_CHUNK) as stream:
        while True:
            chunk, _ = stream.read(WAKE_CHUNK)
            prediction = oww_model.predict(chunk.flatten())
            if prediction[WAKE_WORD] > DETECTION_THRESHOLD:
                oww_model.reset()
                print("Wake word detected", flush=True)

                sd.play(random.choice(filler_audio), samplerate=tts_model.sample_rate)
                sd.wait()

                utterance = record_until_silence(stream, vad)
                text = transcribe(stt_model, utterance)
                print(f"Heard: {text!r}", flush=True)
                if text:
                    result = ask_pixie(text)
                    print(f"Pixie: {result}", flush=True)
                    if "reply" in result:
                        speak(tts_model, voice_state, result["reply"])
                oww_model.reset()
                print(f'Listening for wake word "{WAKE_WORD}"...', flush=True)


if __name__ == "__main__":
    main()
