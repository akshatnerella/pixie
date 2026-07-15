# Pixie Architecture

Locked in 2026-07-14. This is the target design — see "Status" on each
component for what's actually built vs. still to do.

## Overview

Pixie is one big state machine running on the PC, driven by a wake word.
The PC owns all audio (wake word, STT, TTS) and the brain (headless Claude
Code). The Arduino is a dumb display peripheral — it only ever receives a
short emotion string over serial and draws a face for it. Nothing about the
Arduino's role changes from what's already built.

## State machine

```
IDLE_AWAKE ──(2 min no wake word)──> IDLE_GLANCE ──(glance sequence done)──> IDLE_AWAKE
IDLE_AWAKE / IDLE_GLANCE ──(5 min no wake word, total)──> IDLE_ASLEEP

IDLE_AWAKE / IDLE_GLANCE / IDLE_ASLEEP ──("hey pixie" detected)──> LISTENING
LISTENING ──(STT captures utterance, end-of-speech)──> [trigger match?]
  [matches known trigger, e.g. time/weather/stock] ──> DETERMINISTIC ──> SPEAKING
  [no match] ──> THINKING ──(brain returns {reply, emotion})──> SPEAKING
SPEAKING ──(TTS playback finishes)──> IDLE_AWAKE (neutral, idle timer resets)
```

- **IDLE_AWAKE** — neutral face, centered, blinking normally. Wake-word
  engine is always listening in the background regardless of state.
- **IDLE_GLANCE** — one-off 2-3 direction glance sequence, then back to
  center. Already built (Arduino-side timer).
- **IDLE_ASLEEP** — eyes closed, sleepy/tired mood. Already built
  (Arduino-side timer). Wake word still wakes it from here.
- **LISTENING** — wake word triggered; capturing the actual command/question
  via STT.
- **THINKING** — STT transcript sent to the brain; waiting on
  `{reply, emotion}`.
- **SPEAKING** — TTS speaks `reply` aloud through the speaker, screen shows
  `emotion` for the duration.
- **DETERMINISTIC** — the STT transcript matched a known trigger phrase
  (see below); a local handler answers it directly, skipping the brain
  call entirely. Falls through into SPEAKING same as a normal brain reply.
- Back to **IDLE_AWAKE** (neutral) once TTS playback finishes; idle timers
  restart from that moment.

Any wake-word detection resets the idle timer and wakes the face
immediately, regardless of which idle sub-state it was in.

## Deterministic trigger paths

Some queries don't need the LLM at all — cheaper and faster to answer
directly. STT transcript gets checked against known trigger phrases before
falling through to the brain; on a match, a local handler runs instead of
calling `claude`.

Known triggers so far (list will grow):
- "what's the time" → read system clock
- "what's the weather today" → weather API call
- "what's the current price of tesla" (stock lookups generally) → stock
  price API call

**Each trigger gets its own animated UI element on the display** — not one
of the 6 mood faces, a purpose-built widget (e.g. a clock face, a weather
icon, a stock ticker). This means the Arduino side eventually needs a
second class of screen beyond RoboEyes' expressions. Not designed yet —
placeholder for when we get to this step.

Open design questions for this piece specifically:
- How triggers are matched (exact phrase list vs. fuzzy/keyword match vs.
  a fast local intent classifier)
- Where the trigger-matching logic lives (PC orchestrator, presumably,
  same place STT output first lands)
- What each widget actually looks like on a 320×240 screen, and how it
  transitions in/out against the eyes

## Components

### Brain — PC, headless Claude Code
**Status: built.** `server/server.js` shells out to `claude -p ... -r
<session_id> --tools "" --system-prompt ... --json-schema {reply, emotion}`
per turn, in `brain/CLAUDE.md`'s working directory. Session-resumed, so
conversation memory persists across turns. Currently exposed as an HTTP
`/chat` endpoint for testing (curl / `client/client.js`) — will likely get
called directly by the new orchestrator instead of over HTTP once that
exists (open question, see below).

### Emotion vocabulary
**Status: partially built, needs consolidating.** Currently lives only in
`server.js`'s `--json-schema` enum (`happy, excited, curious, sleepy,
concerned, neutral`). Per this design, the list should also be declared in
`brain/CLAUDE.md` itself so the persona doc is self-contained — the two need
to stay in sync (manually for now; could generate the schema from
CLAUDE.md's list later if it becomes annoying).

### Display — Arduino Uno + ILI9341 TFT shield
**Status: built.** `arduino/pixie_face/pixie_face.ino`, `TFT_RoboEyes`-based
animated eyes, yellow, 85×85, 30px gap. Listens on Serial for a one-word
emotion command, draws the matching mood. Owns its own idle-glance
(2 min) / sleep (5 min) timers independently, driven by "did a command
arrive recently," not by the wake-word state machine directly — the PC
resets the Arduino's idle clock simply by sending it any command.

### Serial bridge — PC → Arduino
**Status: built.** `server.js` opens `COM5` via the `serialport` npm
package at startup, writes the emotion string after every brain response.

### TTS — PC, local
**Status: not built.** Pocket TTS (Kyutai Labs) — CPU-only, ~200ms
time-to-first-chunk, `pip install`, runs as a local server (`pocket-tts
serve`) or callable directly. Speaks `reply` through the PC's speaker /
the user's speaker module during SPEAKING.

### STT — PC, local
**Status: not built, engine not chosen.** Captures the user's utterance
during LISTENING, after the wake word fires. Candidates to evaluate:
Whisper.cpp (accurate, heavier), Vosk (lighter, less accurate). Not decided
yet — next step.

### Wake word — PC, local
**Status: not built, engine not chosen.** Listens continuously for "hey
pixie," triggers the IDLE→LISTENING transition. Candidates: openWakeWord
(trainable, open-source), Porcupine (polished, has a free tier with usage
limits). Not decided yet — next step.

### Orchestrator — PC, Python (decided 2026-07-14)
**Status: not built — building now.** A background Python process, since
Pocket TTS and openWakeWord are both Python-only (no solid Node bindings) —
keeps the whole voice loop in one language instead of splitting it.

Runs the state machine: wake-word listener always on → on "hey pixie",
capture STT → POST transcript to the *existing* `server.js` `/chat`
endpoint (reused as-is — brain logic and the Arduino serial write both
stay there, not duplicated) → TTS-speak the returned `reply`.

Deliberately does **not** touch the Arduino's serial port itself — `COM5`
is already owned by `server.js`, which writes the emotion as a side effect
of `/chat`. Two processes fighting over one serial port would just break
things, so the Python side stays HTTP-only.

## Open questions (to resolve step by step, not now)

1. STT engine choice (Whisper.cpp vs Vosk vs other)
2. Wake-word engine choice (openWakeWord vs Porcupine vs other)
3. Orchestrator shape — does `/chat` HTTP stay for debugging, or does
   everything move inside one always-on process?
4. Where exactly the mic/speaker hardware plugs in (PC's own audio vs. the
   separate mic module + speaker Akshat already owns)
