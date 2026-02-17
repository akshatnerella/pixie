use std::env;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use reqwest::StatusCode;
use serde_json::Value;

#[derive(Debug, Clone)]
pub struct GatewayConfig {
    pub base_url: String,
    pub token_path: PathBuf,
    pub webhook_secret: Option<String>,
}

impl Default for GatewayConfig {
    fn default() -> Self {
        Self {
            base_url: env::var("PIXIE_GATEWAY_URL")
                .unwrap_or_else(|_| "http://127.0.0.1:8080".to_string()),
            token_path: default_token_path(),
            webhook_secret: env::var("PIXIE_WEBHOOK_SECRET").ok(),
        }
    }
}

pub struct GatewayClient {
    http: reqwest::Client,
    config: GatewayConfig,
    token_cache: Option<String>,
}

impl GatewayClient {
    pub fn new(config: GatewayConfig) -> Self {
        Self {
            http: reqwest::Client::new(),
            config,
            token_cache: None,
        }
    }

    pub fn token_path(&self) -> &Path {
        &self.config.token_path
    }

    pub async fn pair_only(&mut self, pairing_code: &str) -> Result<(), String> {
        let token = self.pair(pairing_code).await?;
        self.persist_token(&token)
            .map_err(|err| format!("Failed to save gateway token: {err}"))?;
        self.token_cache = Some(token);
        Ok(())
    }

    pub async fn send_message(
        &mut self,
        message: &str,
        pairing_code: Option<&str>,
    ) -> Result<String, String> {
        let mut token = self.ensure_token(pairing_code).await?;

        match self.webhook_with_token(&token, message).await {
            Ok(reply) => Ok(reply),
            Err((status, err)) if status == Some(StatusCode::UNAUTHORIZED) => {
                let code = pairing_code.ok_or_else(|| {
                    "Gateway token rejected and no pairing code provided for re-pairing".to_string()
                })?;
                token = self.pair(code).await?;
                self.persist_token(&token)
                    .map_err(|err| format!("Failed to save gateway token: {err}"))?;
                self.token_cache = Some(token.clone());
                self.webhook_with_token(&token, message)
                    .await
                    .map_err(|(_, second_err)| second_err)
            }
            Err((_, err)) => Err(err),
        }
    }

    async fn ensure_token(&mut self, pairing_code: Option<&str>) -> Result<String, String> {
        if let Some(token) = self.token_cache.clone() {
            return Ok(token);
        }

        if let Ok(token) = self.read_token() {
            self.token_cache = Some(token.clone());
            return Ok(token);
        }

        let code = pairing_code.ok_or_else(|| {
            format!(
                "No saved gateway token at {} and no pairing code provided",
                self.config.token_path.display()
            )
        })?;

        let token = self.pair(code).await?;
        self.persist_token(&token)
            .map_err(|err| format!("Failed to save gateway token: {err}"))?;
        self.token_cache = Some(token.clone());
        Ok(token)
    }

    async fn pair(&self, pairing_code: &str) -> Result<String, String> {
        let url = format!("{}/pair", normalize_base_url(&self.config.base_url));
        let response = self
            .http
            .post(&url)
            .header("X-Pairing-Code", pairing_code)
            .send()
            .await
            .map_err(|err| format!("Pair request failed: {err}"))?;

        let status = response.status();
        let body = response
            .text()
            .await
            .map_err(|err| format!("Pair response read failed: {err}"))?;

        if !status.is_success() {
            return Err(format!(
                "Pair request failed (status {}): {}",
                status,
                body.trim()
            ));
        }

        extract_token(&body)
            .ok_or_else(|| format!("Pair response did not contain a token: {}", body.trim()))
    }

    async fn webhook_with_token(
        &self,
        token: &str,
        message: &str,
    ) -> Result<String, (Option<StatusCode>, String)> {
        let url = format!("{}/webhook", normalize_base_url(&self.config.base_url));
        let request = self
            .http
            .post(&url)
            .bearer_auth(token)
            .json(&serde_json::json!({ "message": message }));
        let request = if let Some(secret) = &self.config.webhook_secret {
            request.header("X-Webhook-Secret", secret)
        } else {
            request
        };
        let response = request
            .send()
            .await
            .map_err(|err| (None, format!("Webhook request failed: {err}")))?;

        let status = response.status();
        let body = response
            .text()
            .await
            .map_err(|err| (Some(status), format!("Webhook response read failed: {err}")))?;

        if !status.is_success() {
            return Err((
                Some(status),
                format!("Webhook request failed (status {}): {}", status, body.trim()),
            ));
        }

        Ok(extract_reply(&body))
    }

    fn read_token(&self) -> io::Result<String> {
        let raw = fs::read_to_string(&self.config.token_path)?;
        let token = raw.trim();
        if token.is_empty() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Token file is empty",
            ));
        }
        Ok(token.to_string())
    }

    fn persist_token(&self, token: &str) -> io::Result<()> {
        if let Some(parent) = self.config.token_path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(&self.config.token_path, format!("{token}\n"))
    }
}

fn default_token_path() -> PathBuf {
    if let Ok(path) = env::var("PIXIE_TOKEN_PATH") {
        return PathBuf::from(path);
    }

    if let Ok(home) = env::var("HOME") {
        return PathBuf::from(home).join(".pixie").join("gateway_token");
    }

    PathBuf::from(".pixie").join("gateway_token")
}

fn normalize_base_url(base_url: &str) -> String {
    base_url.trim_end_matches('/').to_string()
}

fn extract_token(body: &str) -> Option<String> {
    let trimmed = body.trim();
    if trimmed.is_empty() {
        return None;
    }

    if let Ok(value) = serde_json::from_str::<Value>(trimmed) {
        if let Some(token) = find_str_key(
            &value,
            &["token", "bearer_token", "access_token", "auth_token"],
        ) {
            return Some(token.to_string());
        }
        if let Some(as_str) = value.as_str() {
            return Some(as_str.to_string());
        }
    }

    if trimmed.contains(char::is_whitespace) {
        None
    } else {
        Some(trimmed.to_string())
    }
}

fn extract_reply(body: &str) -> String {
    let trimmed = body.trim();
    if trimmed.is_empty() {
        return String::new();
    }

    if let Ok(value) = serde_json::from_str::<Value>(trimmed) {
        if let Some(reply) = find_str_key(&value, &["reply", "response", "message", "text"]) {
            return reply.to_string();
        }
    }

    trimmed.to_string()
}

fn find_str_key<'a>(value: &'a Value, keys: &[&str]) -> Option<&'a str> {
    let object = value.as_object()?;
    for key in keys {
        if let Some(found) = object.get(*key).and_then(Value::as_str) {
            return Some(found);
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::{extract_reply, extract_token, normalize_base_url};

    #[test]
    fn normalizes_base_url() {
        assert_eq!(normalize_base_url("http://127.0.0.1:8080/"), "http://127.0.0.1:8080");
    }

    #[test]
    fn extracts_token_from_known_json_key() {
        assert_eq!(
            extract_token(r#"{"token":"abc123"}"#).as_deref(),
            Some("abc123")
        );
    }

    #[test]
    fn extracts_reply_from_json() {
        assert_eq!(
            extract_reply(r#"{"reply":"hello from zeroclaw"}"#),
            "hello from zeroclaw"
        );
    }
}
