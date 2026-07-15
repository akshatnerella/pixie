#define ROBOEYES_TFT_MODE
#include <MCUFRIEND_kbv.h>
#include <TFT_RoboEyes.h>

MCUFRIEND_kbv tft;
TFTRoboEyes<MCUFRIEND_kbv> roboEyes(tft);

#define BG 0x0000
#define YELLOW 0xFFE0

const unsigned long GLANCE_AFTER_MS = 2UL * 60 * 1000;
const unsigned long SLEEP_AFTER_MS = 5UL * 60 * 1000;
const unsigned long GLANCE_HOLD_MS = 900;
// ponytail: fixed-duration stand-in for "how long Pixie is speaking" --
// once TTS exists, drive this off actual playback finishing instead.
const unsigned long EMOTION_DISPLAY_MS = 5000;

bool emotionActive = false;
unsigned long emotionSetAt = 0;

enum State { AWAKE, GLANCING, ASLEEP };
State state = AWAKE;
unsigned long lastActivity = 0;
bool glancedThisIdle = false;

uint8_t glanceStep = 0;
uint8_t glanceTotal = 0;
uint8_t glancePositions[3];
unsigned long glanceStepStart = 0;
bool glanceHolding = false;

const uint8_t DIRS[] = { N, NE, E, SE, S, SW, W, NW };

void startGlance() {
  glanceTotal = 2 + random(0, 2);  // 2 or 3 glances
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

void goToSleep() {
  roboEyes.setAutoblinker(OFF);
  roboEyes.setMood(TIRED);
  roboEyes.close();
  state = ASLEEP;
}

void wakeUp() {
  bool wasRepositioning = (state != AWAKE);  // coming from ASLEEP or GLANCING
  roboEyes.open();
  roboEyes.setAutoblinker(ON, 4, 2);
  if (wasRepositioning) {
    roboEyes.setPosition(DEFAULT);
    tft.fillScreen(BG);  // only needed when position actually changes
  }
  state = AWAKE;
  glancedThisIdle = false;
  lastActivity = millis();
}

void applyEmotion(const String &name) {
  wakeUp();
  roboEyes.setCuriosity(false);
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
    roboEyes.setMood(DEFAULT);
    roboEyes.setCuriosity(true);
    roboEyes.anim_curious();
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
    if (line.length() > 0) applyEmotion(line);
  }

  unsigned long idleMs = millis() - lastActivity;

  if (state == ASLEEP) {
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

  roboEyes.update();
}
