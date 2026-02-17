# pixie
Adorable, real life, AI companion

## Current Build
Pixie now includes:
- emotion state enum (`Idle`, `Success`, `Error`)
- event enum (`Tick`, `WorkSucceeded`, `WorkFailed`, `Reset`)
- transition function to move between states
- async ticker loop that drives state changes
- ZeroClaw gateway client integration (`/pair` and `/webhook`)
- persisted gateway token (default: `~/.pixie/gateway_token`)
- fullscreen web frontend (`web/`) with state video playback
- wake-word flow in browser speech recognition (`pixie`)
- browser text-to-speech reply playback

## Run Locally (Linux/WSL)
1. Install Rust (if needed):
   ```bash
   curl https://sh.rustup.rs -sSf | sh
   source "$HOME/.cargo/env"
   ```
2. Open the project (WSL path for `D:\Projects\pixie`):
   ```bash
   cd /mnt/d/Projects/pixie
   ```
3. Run loop mode with defaults:
   ```bash
   cargo run
   ```
4. Run loop mode with custom ticker settings:
   ```bash
   cargo run -- --ticks 30 --interval-ms 500
   ```
5. Run loop mode with ZeroClaw gateway calls:
   ```bash
   # Start zeroclaw gateway in another terminal:
   # zeroclaw gateway
   cargo run -- \
     --gateway \
     --pairing-code 123456 \
     --gateway-url http://127.0.0.1:8080 \
     --message "Pixie proactive ping" \
     --gateway-every 6
   ```
6. Run the fullscreen frontend:
   ```bash
   # Terminal 1
   zeroclaw gateway

   # Terminal 2
   cargo run -- --serve --bind 127.0.0.1:8787 --gateway-url http://127.0.0.1:8080
   ```
   Open `http://127.0.0.1:8787`, click `Start Listening` and say:
   - `pixie what is the weather today`
   Pairing input only appears if no saved token exists or auth fails.
7. Optional: startup auto-pair (headless install flow):
   ```bash
   cargo run -- --serve --pairing-code 123456
   ```
   After the token is saved once, normal kiosk runs do not need a keyboard.
8. Run tests:
   ```bash
   cargo test
   ```
9. Run backend smoke test (gateway client loop):
   ```bash
   ./scripts/smoke_gateway.sh
   ```
10. Run frontend smoke test (starts gateway + UI server, pairs, chats via API):
   ```bash
   ./scripts/smoke_frontend.sh
   ```

## Notes
- First gateway run needs a valid pairing code from the ZeroClaw gateway terminal.
- After successful pairing, Pixie saves the bearer token and reuses it automatically.
- If gateway has webhook secret enabled, pass `--webhook-secret <value>` or set `PIXIE_WEBHOOK_SECRET`.
- Wake-word detection currently uses browser Web Speech APIs (best support in Chromium/Chrome).
