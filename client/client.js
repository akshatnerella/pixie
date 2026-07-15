const http = require("http");
const readline = require("readline");

const SERVER = "http://localhost:4141/chat";

const rl = readline.createInterface({ input: process.stdin, output: process.stdout, prompt: "you> " });

function send(message) {
  const data = JSON.stringify({ message });
  const req = http.request(
    SERVER,
    { method: "POST", headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) } },
    (res) => {
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () => {
        const result = JSON.parse(body);
        if (result.error) {
          console.log("error:", result.error);
        } else {
          console.log(`pixie [${result.emotion}]> ${result.reply}  ($${result.costUsd.toFixed(3)})`);
        }
        rl.prompt();
      });
    }
  );
  req.on("error", (e) => {
    console.log("request failed:", e.message);
    rl.prompt();
  });
  req.write(data);
  req.end();
}

console.log("Pixie POC client. Type a message and press enter.");
rl.prompt();
rl.on("line", (line) => {
  if (!line.trim()) return rl.prompt();
  send(line.trim());
});
