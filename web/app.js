const stateVideo = document.getElementById("stateVideo");
const statusText = document.getElementById("statusText");
const heardText = document.getElementById("heardText");
const userText = document.getElementById("userText");
const replyText = document.getElementById("replyText");
const pairInput = document.getElementById("pairingCode");
const pairButton = document.getElementById("pairButton");
const pairRow = document.getElementById("pairRow");
const listenButton = document.getElementById("listenButton");
const stopButton = document.getElementById("stopButton");

const stateVideos = {
  neutral: "/states/neutral.mp4",
  blink: "/states/blink.mp4",
  excited: "/states/excited.mp4",
  love: "/states/love.mp4",
  sad: "/states/sad.mp4",
  angry: "/states/angry.mp4",
  shock: "/states/shock.mp4",
  sleepy: "/states/sleepy.mp4",
};

let currentState = "";
let recognition = null;
let listening = false;
let wakeMode = true;
let commandBuffer = [];
let commandTimer = null;

function showPairingRow(show) {
  if (!pairRow) return;
  pairRow.classList.toggle("hidden", !show);
}

function setStatus(message) {
  statusText.textContent = `Status: ${message}`;
}

function setState(name) {
  const resolved = stateVideos[name] ? name : "neutral";
  if (resolved === currentState) return;
  currentState = resolved;
  stateVideo.src = stateVideos[resolved];
  void stateVideo.play().catch(() => {});
}

function speak(text) {
  if (!window.speechSynthesis || !text) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.0;
  utterance.pitch = 1.05;
  utterance.onstart = () => setState("love");
  utterance.onend = () => setState("neutral");
  window.speechSynthesis.speak(utterance);
}

async function pairGateway() {
  const pairingCode = pairInput.value.trim();
  if (!pairingCode) {
    setStatus("enter pairing code first");
    return;
  }

  pairButton.disabled = true;
  setStatus("pairing...");
  try {
    const res = await fetch("/api/pairing", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pairing_code: pairingCode }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "pairing failed");
    }
    setStatus("paired");
    setState("excited");
    setTimeout(() => setState("neutral"), 900);
  } catch (error) {
    setStatus(`pairing failed: ${error.message}`);
    setState("sad");
  } finally {
    pairButton.disabled = false;
  }
}

async function sendCommand(message) {
  if (!message) return;

  userText.textContent = message;
  replyText.textContent = "...";
  setState("shock");
  setStatus("asking zeroclaw...");

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "chat failed");
    }
    replyText.textContent = data.reply;
    setStatus("ready");
    setState("love");
    speak(data.reply);
  } catch (error) {
    replyText.textContent = `Error: ${error.message}`;
    setStatus("request failed");
    setState("angry");
    if (String(error.message).toLowerCase().includes("unauthorized")) {
      showPairingRow(true);
      setStatus("pairing required");
    }
  }
}

function resetCommandTimer() {
  if (commandTimer) {
    window.clearTimeout(commandTimer);
  }
  commandTimer = window.setTimeout(async () => {
    const message = commandBuffer.join(" ").trim();
    commandBuffer = [];
    wakeMode = true;
    heardText.textContent = "";
    await sendCommand(message);
  }, 2200);
}

function handleTranscript(text) {
  const cleaned = text.trim().toLowerCase();
  if (!cleaned) return;

  heardText.textContent = cleaned;

  if (wakeMode) {
    if (cleaned.includes("pixie")) {
      wakeMode = false;
      setStatus("wake word detected");
      setState("blink");

      const tail = cleaned.split("pixie").slice(1).join(" ").trim();
      if (tail) commandBuffer.push(tail);
      resetCommandTimer();
    }
    return;
  }

  commandBuffer.push(cleaned);
  setStatus("listening command...");
  resetCommandTimer();
}

function stopListening() {
  if (recognition && listening) {
    recognition.stop();
  }
}

function startListening() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    setStatus("speech recognition not supported in this browser");
    return;
  }

  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "en-US";

  recognition.onstart = () => {
    listening = true;
    setStatus("listening for wake word: pixie");
    setState("neutral");
  };

  recognition.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i];
      const text = result[0].transcript;
      if (result.isFinal) {
        handleTranscript(text);
      }
    }
  };

  recognition.onerror = (event) => {
    setStatus(`speech error: ${event.error}`);
    setState("sad");
  };

  recognition.onend = () => {
    listening = false;
    if (commandTimer) {
      window.clearTimeout(commandTimer);
      commandTimer = null;
    }
    setStatus("listener stopped");
  };

  recognition.start();
}

async function bootstrapPairingState() {
  try {
    const res = await fetch("/api/pairing/status");
    const data = await res.json();
    const tokenPresent = !!data.token_present;
    showPairingRow(!tokenPresent);
    setStatus(tokenPresent ? "paired token loaded" : "pairing required");
  } catch (_) {
    showPairingRow(true);
    setStatus("unable to check pairing state");
  }
}

pairButton.addEventListener("click", pairGateway);
listenButton.addEventListener("click", startListening);
stopButton.addEventListener("click", stopListening);

setState("neutral");
bootstrapPairingState();
