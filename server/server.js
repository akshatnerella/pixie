const http = require("http");
const { execFile } = require("child_process");
const fs = require("fs");
const path = require("path");

const PORT = 4141;
const BRAIN_DIR = path.join(__dirname, "..", "brain");
const SESSION_FILE = path.join(__dirname, "session.json");
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

  execFile("claude", args, { cwd: BRAIN_DIR, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
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
        res.writeHead(200, { "Content-Type": "application/json" }).end(JSON.stringify(result));
      });
    });
  })
  .listen(PORT, () => console.log(`Pixie server listening on http://localhost:${PORT}`));
