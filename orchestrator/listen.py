"""
Wake word + STT piece of the Pixie orchestrator (see ../ARCHITECTURE.md).

Listens continuously for a wake word, records the utterance that follows,
transcribes it, and forwards it to the brain (server.js's /chat, which also
handles the Arduino serial write). TTS playback of the reply is the next
piece, not built yet -- this just prints what comes back.

Wake word is "hey_jarvis" (an openWakeWord pretrained model) as a stand-in
for "hey pixie" -- no pretrained "hey pixie" model exists. Swap WAKE_WORD
once a real custom model is trained or generated via Picovoice.
"""

import numpy as np
import requests
import sounddevice as sd
from faster_whisper import WhisperModel
from openwakeword.model import Model

WAKE_WORD = "hey_jarvis"
DETECTION_THRESHOLD = 0.5
SAMPLE_RATE = 16000
CHUNK = 1280  # openWakeWord expects 80ms chunks at 16kHz
UTTERANCE_SECONDS = 4  # fixed-length capture after wake word; no VAD yet
CHAT_URL = "http://localhost:4141/chat"


def record_utterance(stream, seconds):
    frames = []
    for _ in range(int(seconds * SAMPLE_RATE / CHUNK)):
        chunk, _ = stream.read(CHUNK)
        frames.append(chunk.copy())
    return np.concatenate(frames).flatten()


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


def main():
    print("Loading models...", flush=True)
    oww_model = Model(wakeword_models=[WAKE_WORD])
    stt_model = WhisperModel("base.en", device="cpu", compute_type="int8")

    print(f'Listening for wake word "{WAKE_WORD}"...', flush=True)
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=CHUNK) as stream:
        while True:
            chunk, _ = stream.read(CHUNK)
            prediction = oww_model.predict(chunk.flatten())
            if prediction[WAKE_WORD] > DETECTION_THRESHOLD:
                oww_model.reset()
                print("Wake word detected -- listening...", flush=True)
                utterance = record_utterance(stream, UTTERANCE_SECONDS)
                text = transcribe(stt_model, utterance)
                print(f"Heard: {text!r}", flush=True)
                if text:
                    result = ask_pixie(text)
                    print(f"Pixie: {result}", flush=True)
                oww_model.reset()
                print(f'Listening for wake word "{WAKE_WORD}"...', flush=True)


if __name__ == "__main__":
    main()
