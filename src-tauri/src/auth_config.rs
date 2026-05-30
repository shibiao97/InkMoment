use serde::Deserialize;
use std::{env, fs, path::{Path, PathBuf}};
use tauri::{AppHandle, Manager};

pub(crate) const AUTH_SERVER_URL_ENV: &str = "INKMOMENT_AUTH_SERVER_URL";
const AUTH_CONFIG_PATH_ENV: &str = "INKMOMENT_AUTH_CONFIG";
const AUTH_CONFIG_RESOURCE_NAMES: &[&str] = &[
    "inkmoment-auth.json",
    "auth-config.json",
    "config/inkmoment-auth.json",
];

#[derive(Debug, Deserialize)]
struct AuthConfigFile {
    auth_server_url: Option<String>,
    server_url: Option<String>,
    base_url: Option<String>,
}

pub(crate) fn resolve_auth_server_url(app_handle: &AppHandle) -> Result<Option<String>, String> {
    if let Some(url) = non_empty_env(AUTH_SERVER_URL_ENV) {
        return normalize_auth_server_url(&url, AUTH_SERVER_URL_ENV);
    }

    if let Some(path) = non_empty_env(AUTH_CONFIG_PATH_ENV) {
        return read_auth_config_file(&PathBuf::from(path));
    }

    let Some(resource_dir) = app_handle.path().resource_dir().ok() else {
        return Ok(None);
    };
    for resource_name in AUTH_CONFIG_RESOURCE_NAMES {
        let candidate = resource_dir.join(resource_name);
        if candidate.is_file() {
            return read_auth_config_file(&candidate);
        }
    }
    Ok(None)
}

fn read_auth_config_file(path: &Path) -> Result<Option<String>, String> {
    let content = fs::read_to_string(path)
        .map_err(|err| format!("读取授权配置失败：{}；path={}", err, path.display()))?;
    let config: AuthConfigFile = serde_json::from_str(&content)
        .map_err(|err| format!("授权配置不是有效 JSON：{}；path={}", err, path.display()))?;
    let url = config
        .auth_server_url
        .or(config.server_url)
        .or(config.base_url)
        .unwrap_or_default();
    normalize_auth_server_url(&url, &path.display().to_string())
}

fn normalize_auth_server_url(value: &str, source: &str) -> Result<Option<String>, String> {
    let url = value.trim().trim_end_matches('/').to_string();
    if url.is_empty() {
        return Ok(None);
    }
    if !url.starts_with("https://") && !url.starts_with("http://") {
        return Err(format!("{source} 必须是 http 或 https URL"));
    }
    Ok(Some(url))
}

fn non_empty_env(name: &str) -> Option<String> {
    env::var(name)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}


#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn normalize_auth_server_url_trims_trailing_slashes() {
        assert_eq!(
            normalize_auth_server_url(" https://auth.example.com/// ", "test").unwrap(),
            Some("https://auth.example.com".to_string())
        );
    }

    #[test]
    fn normalize_auth_server_url_rejects_non_http_urls() {
        let err = normalize_auth_server_url("file:///tmp/auth.json", "test").unwrap_err();
        assert!(err.contains("必须是 http 或 https URL"));
    }

    #[test]
    fn read_auth_config_file_accepts_primary_and_compat_keys() {
        let primary = write_temp_auth_config(r#"{"auth_server_url":"https://auth.example.com/"}"#);
        assert_eq!(
            read_auth_config_file(&primary).unwrap(),
            Some("https://auth.example.com".to_string())
        );
        let _ = fs::remove_file(primary);

        let compat = write_temp_auth_config(r#"{"server_url":"http://127.0.0.1:8061/"}"#);
        assert_eq!(
            read_auth_config_file(&compat).unwrap(),
            Some("http://127.0.0.1:8061".to_string())
        );
        let _ = fs::remove_file(compat);
    }

    fn write_temp_auth_config(content: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock before unix epoch")
            .as_nanos();
        let path = env::temp_dir().join(format!("inkmoment-auth-test-{nanos}.json"));
        fs::write(&path, content).expect("write temp auth config");
        path
    }
}
