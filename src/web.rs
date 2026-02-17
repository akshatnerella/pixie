use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;

use axum::extract::State;
use axum::http::StatusCode;
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::{Deserialize, Serialize};
use tokio::sync::Mutex;
use tower_http::services::{ServeDir, ServeFile};

use crate::gateway::{GatewayClient, GatewayConfig};

#[derive(Debug, Clone)]
pub struct WebConfig {
    pub bind: SocketAddr,
    pub gateway_url: String,
    pub token_path: Option<PathBuf>,
    pub webhook_secret: Option<String>,
    pub pairing_code: Option<String>,
    pub web_dir: String,
    pub states_dir: String,
}

#[derive(Clone)]
struct AppState {
    gateway: Arc<Mutex<GatewayClient>>,
    pairing_code: Arc<Mutex<Option<String>>>,
}

#[derive(Debug, Deserialize)]
struct PairingRequest {
    pairing_code: String,
}

#[derive(Debug, Serialize)]
struct PairingResponse {
    paired: bool,
    token_path: String,
}

#[derive(Debug, Serialize)]
struct PairingStatusResponse {
    token_present: bool,
}

#[derive(Debug, Deserialize)]
struct ChatRequest {
    message: String,
}

#[derive(Debug, Serialize)]
struct ChatResponse {
    reply: String,
}

#[derive(Debug, Serialize)]
struct HealthResponse {
    status: &'static str,
}

#[derive(Debug, Serialize)]
struct ErrorResponse {
    error: String,
}

pub async fn run_server(config: WebConfig) -> Result<(), String> {
    let mut gateway_config = GatewayConfig {
        base_url: config.gateway_url.clone(),
        ..GatewayConfig::default()
    };
    if let Some(path) = config.token_path {
        gateway_config.token_path = path;
    }
    gateway_config.webhook_secret = config.webhook_secret;

    let token_path = gateway_config.token_path.display().to_string();
    let state = AppState {
        gateway: Arc::new(Mutex::new(GatewayClient::new(gateway_config))),
        pairing_code: Arc::new(Mutex::new(config.pairing_code.clone())),
    };

    if let Some(code) = config.pairing_code {
        let mut client = state.gateway.lock().await;
        if let Err(err) = client.pair_only(&code).await {
            eprintln!("Startup auto-pair failed: {err}");
        } else {
            println!("Startup auto-pair succeeded.");
        }
    }

    let web_root = config.web_dir.clone();
    let index_file = format!("{}/index.html", web_root);
    let app = Router::new()
        .route("/api/health", get(api_health))
        .route("/api/pairing/status", get(api_pairing_status))
        .route("/api/pairing", post(api_pairing))
        .route("/api/chat", post(api_chat))
        .with_state(state)
        .nest_service("/states", ServeDir::new(config.states_dir))
        .fallback_service(ServeDir::new(web_root).fallback(ServeFile::new(index_file)));

    let listener = tokio::net::TcpListener::bind(config.bind)
        .await
        .map_err(|err| format!("Failed to bind web server: {err}"))?;

    println!("Pixie web UI: http://{}", config.bind);
    println!("Gateway URL: {}", config.gateway_url);
    println!("Token file: {}", token_path);
    println!("Open in Chromium kiosk for full-screen mode.");

    axum::serve(listener, app)
        .await
        .map_err(|err| format!("Web server error: {err}"))
}

async fn api_health() -> Json<HealthResponse> {
    Json(HealthResponse { status: "ok" })
}

async fn api_pairing_status(State(state): State<AppState>) -> Json<PairingStatusResponse> {
    let client = state.gateway.lock().await;
    let token_present = client.token_path().exists();
    Json(PairingStatusResponse { token_present })
}

async fn api_pairing(
    State(state): State<AppState>,
    Json(req): Json<PairingRequest>,
) -> Result<Json<PairingResponse>, (StatusCode, Json<ErrorResponse>)> {
    let code = req.pairing_code.trim().to_string();
    if code.is_empty() {
        return Err((
            StatusCode::BAD_REQUEST,
            Json(ErrorResponse {
                error: "pairing_code is required".to_string(),
            }),
        ));
    }

    let mut client = state.gateway.lock().await;
    client
        .pair_only(&code)
        .await
        .map_err(|err| {
            (
                StatusCode::BAD_GATEWAY,
                Json(ErrorResponse {
                    error: format!("Pairing failed: {err}"),
                }),
            )
        })?;

    *state.pairing_code.lock().await = Some(code);

    Ok(Json(PairingResponse {
        paired: true,
        token_path: client.token_path().display().to_string(),
    }))
}

async fn api_chat(
    State(state): State<AppState>,
    Json(req): Json<ChatRequest>,
) -> Result<Json<ChatResponse>, (StatusCode, Json<ErrorResponse>)> {
    let message = req.message.trim();
    if message.is_empty() {
        return Err((
            StatusCode::BAD_REQUEST,
            Json(ErrorResponse {
                error: "message is required".to_string(),
            }),
        ));
    }

    let pairing_code = state.pairing_code.lock().await.clone();
    let mut client = state.gateway.lock().await;
    let reply = client
        .send_message(message, pairing_code.as_deref())
        .await
        .map_err(|err| {
            (
                StatusCode::BAD_GATEWAY,
                Json(ErrorResponse {
                    error: format!("Gateway request failed: {err}"),
                }),
            )
        })?;

    Ok(Json(ChatResponse { reply }))
}
