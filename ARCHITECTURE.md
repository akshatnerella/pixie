# Pixie Architecture

What's actually built and running, as of 2026-07-15. Pixie is a state
machine split across three processes: a Python orchestrator that owns all
audio, a Node server that owns the brain and the Arduino serial port, and
the Arduino itself, which is a dumb display peripheral that only ever
receives a short command string over serial and draws something for it.

## Processes

```
orchestrator/listen.py  (Python, owns the mic/speaker)
  ├─ wake word (openWakeWord custom "pixie" model + custom verifier)
  ├─ STT (faster-whisper base.en)
  ├─ deterministic triggers (e.g. clock) — bypass the brain entirely
  └─ TTS (Pocket TTS, cloned voice)
        │  HTTP (localhost:4141)
        ▼
server/server.js  (Node, owns COM5 + the brain)
  ├─ /chat    — shells out to headless `claude` CLI (session-resumed),
  │             writes the returned emotion to the Arduino
  ├─ /wake    — instant "listening" indicator, fired before STT/brain run
  ├─ /widget  — raw passthrough (thinking dots, clock, clear-to-neutral)
  └─ periodic settime: heartbeat, for the sleep-mode corner clock
        │  Serial (9600 baud)
        ▼
arduino/pixie_face/pixie_face.ino  (Arduino Uno + ILI9341 TFT)
  TFT_RoboEyes-based face, one-word commands in, pixels out
```

## Turn flow

```
listen.py: wake word detected (base model score > 0.5, verifier > 0.3)
  → POST /wake                      → Arduino: red dot overlay (wakes from sleep if needed)
  → record until VAD silence (with ~1s preroll, so words said during
    the ~900ms wake-detection window aren't lost)
  → POST /widget {command: thinking} → Arduino: 3 yellow dots, cycling
  → transcribe (discard if < 2 words — near-threshold noise, not a command)
  → [time trigger?]
      yes → local clock handler → POST /widget {command: time:H:MM}
            → Arduino: instant cut to full-screen clock (6s), colon
              blinks, cuts back to normal eyes
      no  → POST /chat {message}    → server spawns `claude`, gets
            {reply, emotion} back, writes emotion to Arduino via serial
            → Arduino: normal mood face, reverts to neutral after ~5s
  → speak the reply (or "It's H:MM" for the clock) via TTS
  → [nothing real heard] → POST /widget {command: neutral} — clears the
    thinking dots, since nothing else would
```

Idle timers (2 min → one-off glance, 5 min → sleep) run entirely on the
Arduino, driven by "did any command arrive recently" — the PC doesn't
track idle state itself.

## Wake word

Custom-trained "pixie" openWakeWord model, two stages:

1. **Base model** (`wakeword_training/train.py`) — small classifier over
   openWakeWord's embeddings, trained on synthetic TTS clips (22 voices) +
   real recordings of Akshat's voice (`record_positives.py`) as positives,
   davidscripka's pre-computed negative feature set as negatives.
2. **Custom verifier** (`wakeword_training/train_verifier.py`) — a
   secondary speaker-conditioned filter (openWakeWord's own
   `train_custom_verifier`), trained on the same real positive clips plus
   real recordings of the actual background noise/talking near the mic
   (`record_negative.py`). The base model alone was scoring high-confidence
   false accepts (0.8-0.97) on background TV/talking; the verifier rejects
   those a second time based on whether the voice actually matches.

Both stages load in `listen.py`'s `Model(...)` call. Retraining either one
is a rerun of the corresponding script — see the docstrings in
`wakeword_training/` for exact steps.

## Deterministic trigger paths

STT transcript is checked against known triggers before ever reaching the
brain — cheaper and much faster (a few seconds vs. an 8+ second `claude`
CLI round trip).

Built so far:
- "what/tell me/current ... time" → system clock, no brain call, own
  full-screen widget on the Arduino (see turn flow above)

More can be added the same way: match in `listen.py`, add a local handler,
give it its own Arduino-side widget if it needs a distinct visual (see
`showClock`/`updateClock` in the `.ino` for the pattern).

## Flash budget (Arduino)

Uno has 32256 bytes of program storage; currently ~91% used. AVR's
floating-point trig routines (`cos`/`sin`) are extremely expensive
(~1.3KB for two call sites) — avoid them if an animation can be done with
linear interpolation or an instant cut instead.
