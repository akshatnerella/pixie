use std::{env, net::SocketAddr, path::PathBuf, time::Duration};

use pixie::gateway::{GatewayClient, GatewayConfig};
use pixie::web::{self, WebConfig};
use pixie::{event_for_tick, transition, EmotionState, Event};
use tokio::time::{interval, MissedTickBehavior};

#[derive(Debug, Clone)]
struct Config {
    serve: bool,
    bind: String,
    web_dir: String,
    states_dir: String,
    ticks: u64,
    interval_ms: u64,
    gateway_enabled: bool,
    gateway_every: u64,
    gateway_url: String,
    pairing_code: Option<String>,
    message: String,
    token_path: Option<PathBuf>,
    webhook_secret: Option<String>,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            serve: false,
            bind: "127.0.0.1:8787".to_string(),
            web_dir: "web".to_string(),
            states_dir: "states".to_string(),
            ticks: 24,
            interval_ms: 800,
            gateway_enabled: false,
            gateway_every: 6,
            gateway_url: "http://127.0.0.1:8080".to_string(),
            pairing_code: None,
            message: "Pixie proactive heartbeat check-in".to_string(),
            token_path: None,
            webhook_secret: env::var("PIXIE_WEBHOOK_SECRET").ok(),
        }
    }
}

fn print_usage() {
    println!("pixie - web frontend + emotion state machine + ZeroClaw gateway");
    println!("Usage:");
    println!("  cargo run -- --serve [--bind <ip:port>] [--gateway-url <url>]");
    println!("  cargo run -- --gateway [--pairing-code <code>] [--message <text>]");
    println!("  cargo run -- [--ticks <n>] [--interval-ms <n>]");
    println!();
    println!("Flags:");
    println!("  --serve                   Run fullscreen Pixie web frontend server");
    println!("  --bind <ip:port>          Web server bind (default: 127.0.0.1:8787)");
    println!("  --web-dir <path>          Web asset directory (default: web)");
    println!("  --states-dir <path>       State video directory (default: states)");
    println!("  --gateway                 Enable ZeroClaw gateway calls in loop");
    println!("  --gateway-url <url>       Gateway base URL (default: http://127.0.0.1:8080)");
    println!("  --pairing-code <code>     One-time code for /pair token exchange");
    println!("  --token-path <path>       Location for saved gateway token");
    println!("  --gateway-every <n>       Call gateway every n ticks (default: 6)");
    println!("  --message <text>          Message sent on proactive gateway ticks");
    println!("  --webhook-secret <value>  Optional X-Webhook-Secret for gateway auth");
}

fn parse_u64_arg(flag: &str, value: Option<String>) -> Result<u64, String> {
    let raw = value.ok_or_else(|| format!("Missing value for {flag}"))?;
    let parsed = raw
        .parse::<u64>()
        .map_err(|_| format!("Invalid numeric value for {flag}: {raw}"))?;

    if parsed == 0 {
        return Err(format!("{flag} must be greater than zero"));
    }

    Ok(parsed)
}

fn parse_config() -> Result<Config, String> {
    let mut config = Config::default();
    let mut args = env::args().skip(1);

    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--serve" => {
                config.serve = true;
                config.gateway_enabled = true;
            }
            "--bind" => {
                config.bind = args
                    .next()
                    .ok_or_else(|| "Missing value for --bind".to_string())?;
            }
            "--web-dir" => {
                config.web_dir = args
                    .next()
                    .ok_or_else(|| "Missing value for --web-dir".to_string())?;
            }
            "--states-dir" => {
                config.states_dir = args
                    .next()
                    .ok_or_else(|| "Missing value for --states-dir".to_string())?;
            }
            "--gateway" => {
                config.gateway_enabled = true;
            }
            "--ticks" => {
                config.ticks = parse_u64_arg("--ticks", args.next())?;
            }
            "--interval-ms" => {
                config.interval_ms = parse_u64_arg("--interval-ms", args.next())?;
            }
            "--gateway-every" => {
                config.gateway_every = parse_u64_arg("--gateway-every", args.next())?;
            }
            "--gateway-url" => {
                config.gateway_url = args
                    .next()
                    .ok_or_else(|| "Missing value for --gateway-url".to_string())?;
            }
            "--pairing-code" => {
                config.pairing_code = Some(
                    args.next()
                        .ok_or_else(|| "Missing value for --pairing-code".to_string())?,
                );
            }
            "--token-path" => {
                let raw = args
                    .next()
                    .ok_or_else(|| "Missing value for --token-path".to_string())?;
                config.token_path = Some(PathBuf::from(raw));
            }
            "--message" => {
                config.message = args
                    .next()
                    .ok_or_else(|| "Missing value for --message".to_string())?;
            }
            "--webhook-secret" => {
                config.webhook_secret = Some(
                    args.next()
                        .ok_or_else(|| "Missing value for --webhook-secret".to_string())?,
                );
            }
            "--help" | "-h" => {
                print_usage();
                std::process::exit(0);
            }
            _ => {
                return Err(format!("Unknown argument: {arg}"));
            }
        }
    }

    Ok(config)
}

#[tokio::main]
async fn main() {
    let config = match parse_config() {
        Ok(config) => config,
        Err(err) => {
            eprintln!("{err}");
            print_usage();
            std::process::exit(2);
        }
    };

    if config.serve {
        let bind: SocketAddr = match config.bind.parse() {
            Ok(addr) => addr,
            Err(_) => {
                eprintln!("Invalid --bind value: {}", config.bind);
                std::process::exit(2);
            }
        };
        let server_config = WebConfig {
            bind,
            gateway_url: config.gateway_url.clone(),
            token_path: config.token_path.clone(),
            webhook_secret: config.webhook_secret.clone(),
            pairing_code: config.pairing_code.clone(),
            web_dir: config.web_dir.clone(),
            states_dir: config.states_dir.clone(),
        };

        if let Err(err) = web::run_server(server_config).await {
            eprintln!("{err}");
            std::process::exit(1);
        }
        return;
    }

    let mut state = EmotionState::Idle;
    let mut ticker = interval(Duration::from_millis(config.interval_ms));
    ticker.set_missed_tick_behavior(MissedTickBehavior::Skip);
    let mut gateway_client = if config.gateway_enabled {
        let mut gateway_config = GatewayConfig {
            base_url: config.gateway_url.clone(),
            ..GatewayConfig::default()
        };
        if let Some(path) = config.token_path.clone() {
            gateway_config.token_path = path;
        }
        if let Some(secret) = config.webhook_secret.clone() {
            gateway_config.webhook_secret = Some(secret);
        }
        Some(GatewayClient::new(gateway_config))
    } else {
        None
    };

    println!(
        "Starting pixie loop: ticks={} interval_ms={} gateway_enabled={}...",
        config.ticks, config.interval_ms, config.gateway_enabled
    );
    if let Some(client) = &gateway_client {
        println!("gateway_url={} token_path={}", config.gateway_url, client.token_path().display());
    }

    for tick in 1..=config.ticks {
        ticker.tick().await;

        let event = if let Some(client) = &mut gateway_client {
            if tick % config.gateway_every == 0 {
                let prompt = format!("{} (tick {})", config.message, tick);
                match client
                    .send_message(&prompt, config.pairing_code.as_deref())
                    .await
                {
                    Ok(reply) => {
                        println!("gateway reply: {}", reply);
                        Event::WorkSucceeded
                    }
                    Err(err) => {
                        eprintln!("gateway error: {}", err);
                        Event::WorkFailed
                    }
                }
            } else {
                Event::Tick
            }
        } else {
            event_for_tick(tick)
        };

        let next_state = transition(state, event);

        println!(
            "tick {:>3}: event={:?}, state={:?} -> {:?}",
            tick, event, state, next_state
        );

        state = next_state;
    }

    println!("Done. Final state: {:?}", state);
}
