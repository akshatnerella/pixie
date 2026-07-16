const http = require("http");
const { execFile } = require("child_process");
const fs = require("fs");
const path = require("path");
const { SerialPort } = require("serialport");

const PORT = 4141;
const ARDUINO_PORT = "COM5";
const BRAIN_DIR = path.join(__dirname, "..", "brain");
const SESSION_FILE = path.join(__dirname, "session.json");

function log(msg) {
  console.log(`[${new Date().toISOString().slice(11, 23)}] ${msg}`);
}

const arduino = new SerialPort({ path: ARDUINO_PORT, baudRate: 9600 }, (err) => {
  if (err) console.error(`Arduino not connected on ${ARDUINO_PORT}: ${err.message} (chat will still work, face won't update)`);
});
// Without this listener, serialport's default behavior on any port-level
// error (e.g. a transient WriteFileEx failure) is to throw and crash the
// whole process -- log it instead so the server survives a serial hiccup.
arduino.on("error", (err) => log(`Arduino serial error: ${err.message}`));

function sendEmotionToArduino(emotion) {
  if (!arduino.isOpen) return;
  const t0 = Date.now();
  arduino.write(emotion + "\n", (err) => {
    if (err) console.error("Failed to write to Arduino:", err.message);
    else log(`Arduino write "${emotion}" took ${Date.now() - t0}ms`);
  });
}

function formatTime() {
  const now = new Date();
  let hours = now.getHours() % 12;
  if (hours === 0) hours = 12;
  const minutes = String(now.getMinutes()).padStart(2, "0");
  return `${hours}:${minutes}`;
}

// Silent periodic sync so the Arduino has a roughly-fresh time to show in
// the corner while asleep, without needing an RTC of its own.
setInterval(() => sendEmotionToArduino(`settime:${formatTime()}`), 60 * 1000);
sendEmotionToArduino(`settime:${formatTime()}`);

const SYSTEM_PROMPT = "You are Pixie.";
const EMOTION_SCHEMA = JSON.stringify({
  type: "object",
  properties: {
    reply: { type: "string" },
    emotion: {
      type: "string",
      enum: ["happy", "excited", "curious", "sleepy", "concerned", "neutral"],
    },
  },
  required: ["reply", "emotion"],
});

function loadSessionId() {
  try {
    return JSON.parse(fs.readFileSync(SESSION_FILE, "utf8")).sessionId;
  } catch {
    return null;
  }
}

function saveSessionId(sessionId) {
  fs.writeFileSync(SESSION_FILE, JSON.stringify({ sessionId }));
}

function askPixie(message, callback) {
  const t0 = Date.now();
  const sessionId = loadSessionId();
  const args = [
    "-p",
    message,
    "--output-format",
    "json",
    "--tools",
    "",
    "--system-prompt",
    SYSTEM_PROMPT,
    "--json-schema",
    EMOTION_SCHEMA,
  ];
  if (sessionId) args.push("-r", sessionId);

  log(`askPixie() spawning claude CLI for: ${message}`);
  execFile("claude", args, { cwd: BRAIN_DIR, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
    log(`askPixie() claude CLI took ${Date.now() - t0}ms`);
    if (err) return callback(err.message + "\n" + stderr);
    let parsed;
    try {
      parsed = JSON.parse(stdout);
    } catch {
      return callback("Could not parse Claude output: " + stdout);
    }
    saveSessionId(parsed.session_id);
    callback(null, {
      reply: parsed.structured_output.reply,
      emotion: parsed.structured_output.emotion,
      costUsd: parsed.total_cost_usd,
    });
  });
}

http
  .createServer((req, res) => {
    const reqT0 = Date.now();
    log(`${req.method} ${req.url} received`);
    if (req.method === "POST" && req.url === "/wake") {
      // Fired the instant the wake word fires, before STT/brain even start --
      // small red dot overlay, doesn't disturb whatever's already on screen.
      sendEmotionToArduino("listening");
      res.writeHead(200).end("ok");
      log(`/wake total ${Date.now() - reqT0}ms`);
      return;
    }
    if (req.method === "POST" && req.url === "/widget") {
      let widgetBody = "";
      req.on("data", (chunk) => (widgetBody += chunk));
      req.on("end", () => {
        let command;
        try {
          command = JSON.parse(widgetBody).command;
        } catch {
          res.writeHead(400).end("bad json");
          return;
        }
        sendEmotionToArduino(command);
        res.writeHead(200).end("ok");
        log(`/widget total ${Date.now() - reqT0}ms`);
      });
      return;
    }
    if (req.method !== "POST" || req.url !== "/chat") {
      res.writeHead(404).end();
      return;
    }
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      let message;
      try {
        message = JSON.parse(body).message;
      } catch {
        res.writeHead(400).end("bad json");
        return;
      }
      askPixie(message, (err, result) => {
        if (err) {
          res.writeHead(500, { "Content-Type": "application/json" }).end(JSON.stringify({ error: err }));
          return;
        }
        sendEmotionToArduino(result.emotion);
        res.writeHead(200, { "Content-Type": "application/json" }).end(JSON.stringify(result));
        log(`/chat total ${Date.now() - reqT0}ms`);
      });
    });
  })
  .listen(PORT, () => log(`Pixie server listening on http://localhost:${PORT}`));
