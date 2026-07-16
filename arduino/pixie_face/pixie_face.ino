#define ROBOEYES_TFT_MODE
#include <MCUFRIEND_kbv.h>
#include <TFT_RoboEyes.h>

MCUFRIEND_kbv tft;
TFTRoboEyes<MCUFRIEND_kbv> roboEyes(tft);

#define BG 0x0000
#define YELLOW 0xFFE0
#define RED 0xF800
#define DIMYELLOW 0x8400

const unsigned long GLANCE_AFTER_MS = 2UL * 60 * 1000;
const unsigned long SLEEP_AFTER_MS = 5UL * 60 * 1000;
const unsigned long GLANCE_HOLD_MS = 900;
// ponytail: fixed-duration stand-in for "how long Pixie is speaking" --
// once TTS exists, drive this off actual playback finishing instead.
const unsigned long EMOTION_DISPLAY_MS = 5000;

bool emotionActive = false;
unsigned long emotionSetAt = 0;

enum State { AWAKE, GLANCING, ASLEEP, CLOCK, THINKING };
State state = AWAKE;
unsigned long lastActivity = 0;
bool glancedThisIdle = false;

const int16_t DOT_SIZE = 14;
uint8_t thinkPhase = 0;
unsigned long thinkLastStep = 0;

const unsigned long CLOCK_DISPLAY_MS = 6000;
const unsigned long COLON_BLINK_MS = 500;
String clockTimeStr = "";
unsigned long clockEnteredAt = 0;
unsigned long lastColonToggle = 0;
bool colonVisible = true;
int16_t clockX = 0;
const int16_t CLOCK_Y = 88;
const int16_t CLOCK_CHAR_W = 6 * 8;  // 6px glyph cell * text size 8
const int16_t CLOCK_CHAR_H = 8 * 8;

String sleepClockStr = "";  // last known time, shown small while asleep

uint8_t glanceStep = 0;
uint8_t glanceTotal = 0;
uint8_t glancePositions[3];
unsigned long glanceStepStart = 0;
bool glanceHolding = false;

const uint8_t DIRS[] = { N, NE, E, SE, S, SW, W, NW };

void startGlance(uint8_t count = 0) {
  glanceTotal = count > 0 ? count : 2 + random(0, 2);  // 2 or 3 glances if not specified
  for (uint8_t i = 0; i < glanceTotal; i++) {
    glancePositions[i] = DIRS[random(0, 8)];
  }
  glanceStep = 0;
  glanceHolding = false;
  state = GLANCING;
}

void updateGlance() {
  unsigned long now = millis();
  if (!glanceHolding) {
    roboEyes.setPosition(glancePositions[glanceStep]);
    tft.fillScreen(BG);  // avoid smart-erase artifacts on position jumps
    glanceHolding = true;
    glanceStepStart = now;
  } else if (now - glanceStepStart >= GLANCE_HOLD_MS) {
    glanceStep++;
    glanceHolding = false;
    if (glanceStep >= glanceTotal) {
      roboEyes.setPosition(DEFAULT);
      tft.fillScreen(BG);
      state = AWAKE;
      glancedThisIdle = true;
    }
  }
}

void drawSleepClock() {
  if (sleepClockStr.length() == 0) return;
  // Mirrors the Zzz's corner on the opposite side. Small text (size 3),
  // fixed-width cell erase so it can be redrawn without disturbing Zzz or
  // the sleepy eyes.
  const int16_t w = 6 * 3 * 5;  // room for up to "12:15"
  const int16_t h = 8 * 3;
  tft.fillRect(10, 25, w, h, BG);
  tft.setTextColor(YELLOW);
  tft.setTextSize(3);
  tft.setCursor(10, 25);
  tft.print(sleepClockStr);
}

void goToSleep() {
  roboEyes.setAutoblinker(OFF);
  // TIRED mood draws a diagonal drooping eyelid -- reads as sad, not
  // sleepy. Flat squinted rectangles (full width, short height) instead:
  // DEFAULT mood (no diagonal cutout) + manually forced short height.
  roboEyes.setMood(DEFAULT);
  roboEyes.eyeLheightCurrent = roboEyes.eyeLheightNext = 20;
  roboEyes.eyeRheightCurrent = roboEyes.eyeRheightNext = 20;
  state = ASLEEP;
  tft.setTextColor(YELLOW);
  tft.setTextSize(3);
  tft.setCursor(240, 25);  // corner, well outside the eyes' bounding box
  tft.print("Zzz");
  drawSleepClock();
}

void wakeUp() {
  bool wasAsleep = (state == ASLEEP);
  bool wasRepositioning = (state != AWAKE);  // coming from ASLEEP or GLANCING
  roboEyes.open();
  roboEyes.setAutoblinker(ON, 4, 2);
  if (wasRepositioning) {
    roboEyes.setPosition(DEFAULT);
    tft.fillScreen(BG);  // only needed when position actually changes
  }

  if (wasAsleep) {
    roboEyes.setMood(DEFAULT);
    // Smooth continuous grow from the sleepy squint up to wide-eyed, then
    // back down to normal -- a single fluid motion, no separate blink step.
    int wideHeight = roboEyes.eyeLheightDefault * 1.2;
    int normalHeight = roboEyes.eyeLheightDefault;
    for (int h = 20; h <= wideHeight; h += 4) {
      roboEyes.eyeLheightCurrent = roboEyes.eyeLheightNext = h;
      roboEyes.eyeRheightCurrent = roboEyes.eyeRheightNext = h;
      roboEyes.update();
      delay(15);
    }
    for (int h = wideHeight; h >= normalHeight; h -= 4) {
      roboEyes.eyeLheightCurrent = roboEyes.eyeLheightNext = h;
      roboEyes.eyeRheightCurrent = roboEyes.eyeRheightNext = h;
      roboEyes.update();
      delay(15);
    }
    roboEyes.eyeLheightCurrent = roboEyes.eyeLheightNext = normalHeight;
    roboEyes.eyeRheightCurrent = roboEyes.eyeRheightNext = normalHeight;
  }

  state = AWAKE;
  glancedThisIdle = false;
  lastActivity = millis();
}

void drawClockFull() {
  tft.fillScreen(BG);
  tft.setTextColor(YELLOW);
  tft.setTextSize(8);
  int16_t textWidth = clockTimeStr.length() * CLOCK_CHAR_W;
  clockX = max(0, (320 - textWidth) / 2);
  tft.setCursor(clockX, CLOCK_Y);
  tft.print(clockTimeStr);
}

void toggleColon() {
  // Only erase/redraw the colon's own glyph cell -- redrawing the whole
  // screen every 500ms caused a visible full-screen flash.
  int colonIndex = clockTimeStr.indexOf(':');
  if (colonIndex < 0) return;
  int16_t charX = clockX + colonIndex * CLOCK_CHAR_W;
  tft.fillRect(charX, CLOCK_Y, CLOCK_CHAR_W, CLOCK_CHAR_H, BG);
  if (colonVisible) {
    tft.setTextColor(YELLOW);
    tft.setTextSize(8);
    tft.setCursor(charX, CLOCK_Y);
    tft.print(':');
  }
}

void showClock(const String &timeStr) {
  clockTimeStr = timeStr;
  roboEyes.setMood(DEFAULT);
  roboEyes.setCuriosity(false);

  // Instant cut, no morph animation -- drawClockFull() clears the eyes
  // and draws the full time text in one shot.
  clockEnteredAt = millis();
  lastColonToggle = millis();
  colonVisible = true;
  drawClockFull();
  state = CLOCK;
}

void updateClock() {
  if (millis() - lastColonToggle >= COLON_BLINK_MS) {
    colonVisible = !colonVisible;
    lastColonToggle = millis();
    toggleColon();
  }
  if (millis() - clockEnteredAt >= CLOCK_DISPLAY_MS) {
    // Instant cut back to normal eyes -- clear the clock text, sync roboEyes'
    // state to defaults, and let the next roboEyes.update() (below, once
    // state is AWAKE again) draw the eyes fresh.
    tft.fillScreen(BG);
    roboEyes.open();
    roboEyes.eyeLx = roboEyes.eyeLxNext = roboEyes.eyeLxDefault;
    roboEyes.eyeLy = roboEyes.eyeLyNext = roboEyes.eyeLyDefault;
    roboEyes.eyeRx = roboEyes.eyeRxNext = roboEyes.eyeRxDefault;
    roboEyes.eyeRy = roboEyes.eyeRyNext = roboEyes.eyeRyDefault;
    roboEyes.eyeLwidthCurrent = roboEyes.eyeLwidthNext = roboEyes.eyeLwidthDefault;
    roboEyes.eyeLheightCurrent = roboEyes.eyeLheightNext = roboEyes.eyeLheightDefault;
    roboEyes.eyeRwidthCurrent = roboEyes.eyeRwidthNext = roboEyes.eyeRwidthDefault;
    roboEyes.eyeRheightCurrent = roboEyes.eyeRheightNext = roboEyes.eyeRheightDefault;
    state = AWAKE;
    lastActivity = millis();
  }
}

// Small overlay dot, bottom-right, on top of whatever's already on screen --
// fires the instant the wake word triggers, before STT/brain even start.
void drawListeningDot() {
  tft.fillRect(295, 214, DOT_SIZE, DOT_SIZE, RED);
}

// Three-dot loader, same bottom-right corner as the listening dot, overlaid
// on whatever's already on screen -- rightmost dot exactly covers where the
// listening dot was, so the handoff is a clean overdraw. One dot bright,
// other two dim, cycling -- fakes a fade without real alpha blending.
void updateThinking() {
  if (millis() - thinkLastStep < 250) return;
  thinkLastStep = millis();
  const int16_t gap = 18, y = 214;
  for (uint8_t i = 0; i < 3; i++) {
    tft.fillRect(295 - (2 - i) * gap, y, DOT_SIZE, DOT_SIZE, i == thinkPhase ? YELLOW : DIMYELLOW);
  }
  thinkPhase = (thinkPhase + 1) % 3;
}

void applyEmotion(const String &name) {
  wakeUp();
  roboEyes.setCuriosity(false);

  // Jumping straight between two moods' eyelid shapes (e.g. HAPPY's
  // curved bottom lid to ANGRY's slanted top lid) leaves the same kind of
  // erase artifact position jumps did -- settle through DEFAULT first so
  // each transition is a smaller, well-handled delta.
  roboEyes.setMood(DEFAULT);
  unsigned long settleStart = millis();
  while (millis() - settleStart < 300) roboEyes.update();

  if (name == "happy") {
    roboEyes.setMood(HAPPY);
    emotionActive = true;
  } else if (name == "excited") {
    roboEyes.setMood(HAPPY);
    roboEyes.anim_laugh();
    emotionActive = true;
  } else if (name == "sleepy") {
    roboEyes.setMood(TIRED);
    emotionActive = true;
  } else if (name == "concerned") {
    roboEyes.setMood(ANGRY);
    emotionActive = true;
  } else if (name == "curious") {
    // Curiosity only has a visible effect (bigger outer eye) when looking
    // to a side -- centered, setCuriosity(true) does nothing visible.
    roboEyes.setMood(DEFAULT);
    roboEyes.setCuriosity(true);
    startGlance(1);
    emotionActive = true;
  } else {
    roboEyes.setMood(DEFAULT);
    emotionActive = false;
  }
  emotionSetAt = millis();
}

void setup() {
  Serial.begin(9600);
  randomSeed(millis());
  uint16_t ID = tft.readID();
  tft.begin(ID);
  tft.setRotation(3);

  roboEyes.begin(320, 240, 30);
  roboEyes.setDisplayColors(BG, YELLOW);
  roboEyes.setEyeColors(YELLOW, YELLOW);
  roboEyes.setWidth(85, 85);
  roboEyes.setHeight(85, 85);
  roboEyes.setBorderradius(16, 16);
  roboEyes.setSpacebetween(30);
  roboEyes.setAutoblinker(ON, 4, 2);
  roboEyes.setIdleMode(OFF);  // we drive glancing ourselves now
  roboEyes.setMood(DEFAULT);

  // TFT_RoboEyes computes eyeLxDefault/eyeRxDefault etc. once, as in-class
  // member initializers, using its 160x128 built-in defaults -- before our
  // begin()/setWidth() calls above ever run. Recompute + overwrite them here
  // for our real 320x240 screen and 70x70 eyes, or the eyes stay centered
  // against the wrong (smaller) canvas.
  const int eyeW = 85, eyeH = 85, space = 30;
  roboEyes.eyeLxDefault = (320 - (eyeW * 2 + space)) / 2;
  roboEyes.eyeLyDefault = (240 - eyeH) / 2;
  roboEyes.eyeRxDefault = roboEyes.eyeLxDefault + eyeW + space;
  roboEyes.eyeRyDefault = roboEyes.eyeLyDefault;
  roboEyes.eyeLx = roboEyes.eyeLxNext = roboEyes.eyeLxDefault;
  roboEyes.eyeLy = roboEyes.eyeLyNext = roboEyes.eyeLyDefault;
  roboEyes.eyeRx = roboEyes.eyeRxNext = roboEyes.eyeRxDefault;
  roboEyes.eyeRy = roboEyes.eyeRyNext = roboEyes.eyeRyDefault;

  lastActivity = millis();
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line == "listening") {
      if (state == ASLEEP) wakeUp();
      drawListeningDot();
      lastActivity = millis();
    } else if (line == "thinking") {
      state = THINKING;
      thinkPhase = 0;
      thinkLastStep = 0;
    } else if (line.startsWith("settime:")) {
      // Silent time sync (server pushes this periodically) -- only visibly
      // redraws if we're currently asleep, otherwise just updates the
      // stored value for next time we go to sleep.
      sleepClockStr = line.substring(8);
      if (state == ASLEEP) drawSleepClock();
    } else if (line.startsWith("time:")) showClock(line.substring(5));
    else if (line.length() > 0) applyEmotion(line);
  }

  unsigned long idleMs = millis() - lastActivity;

  if (state == CLOCK) {
    updateClock();
  } else if (state == THINKING) {
    updateThinking();
  } else if (state == ASLEEP) {
    // stays asleep until a Serial command wakes it via applyEmotion()
  } else if (state == GLANCING) {
    updateGlance();
  } else {  // AWAKE
    if (idleMs >= SLEEP_AFTER_MS) {
      goToSleep();
    } else if (idleMs >= GLANCE_AFTER_MS && !glancedThisIdle) {
      startGlance();
    } else if (emotionActive && millis() - emotionSetAt >= EMOTION_DISPLAY_MS) {
      roboEyes.setMood(DEFAULT);
      roboEyes.setCuriosity(false);
      emotionActive = false;
    }
  }

  if (state != CLOCK) roboEyes.update();  // don't draw eyes over the clock digits; thinking dots are just a corner overlay
}
