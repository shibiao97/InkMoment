use std::{env, path::{Path, PathBuf}};
use tauri::{AppHandle, Manager};

const DEFAULT_BACKEND_ORIGINS: &str = concat!(
    "http://127.0.0.1:5173,",
    "http://localhost:5173,",
    "tauri://localhost,",
    "http://tauri.localhost,",
    "https://tauri.localhost"
);

pub(crate) fn bundled_sidecar_path(resource_dir: &Path) -> Option<PathBuf> {
    let mut base_names = vec!["inkmoment-sidecar".to_string()];
    if let Some(target) = option_env!("TARGET") {
        base_names.push(format!("inkmoment-sidecar-{target}"));
    }
    for dir in bundled_sidecar_search_dirs(resource_dir) {
        for base_name in &base_names {
            let mut candidate = dir.join(base_name);
            if cfg!(windows) {
                candidate.set_extension("exe");
            }
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }
    None
}

fn bundled_sidecar_search_dirs(resource_dir: &Path) -> Vec<PathBuf> {
    let mut dirs = vec![
        resource_dir.join("binaries").join("inkmoment-sidecar"),
        resource_dir.join("inkmoment-sidecar"),
        resource_dir.to_path_buf(),
    ];
    if cfg!(target_os = "macos")
        && resource_dir.file_name().and_then(|name| name.to_str()) == Some("Resources")
    {
        if let Some(contents_dir) = resource_dir.parent() {
            dirs.push(contents_dir.join("MacOS"));
        }
    }
    dirs
}

pub(crate) fn should_use_bundled_sidecar(app_handle: &AppHandle) -> bool {
    if matches!(env::var("INKMOMENT_USE_BUNDLED_SIDECAR"), Ok(value) if value == "0" || value.eq_ignore_ascii_case("false"))
    {
        return false;
    }
    if matches!(env::var("INKMOMENT_USE_BUNDLED_SIDECAR"), Ok(value) if value == "1" || value.eq_ignore_ascii_case("true"))
    {
        return true;
    }
    app_handle
        .path()
        .resource_dir()
        .ok()
        .and_then(|resource_dir| bundled_sidecar_path(&resource_dir))
        .is_some()
}

pub(crate) fn resolve_app_root() -> Result<PathBuf, String> {
    if let Ok(root) = env::var("INKMOMENT_APP_ROOT") {
        let root = PathBuf::from(root);
        if root.join("app.py").is_file() {
            return Ok(root);
        }
        return Err(format!("INKMOMENT_APP_ROOT 下找不到 app.py：{}", root.display()));
    }

    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .map(Path::to_path_buf)
        .ok_or_else(|| "无法解析项目根目录".to_string())
}

pub(crate) fn resolve_python(app_root: &Path) -> PathBuf {
    if let Ok(python) = env::var("INKMOMENT_PYTHON") {
        if !python.trim().is_empty() {
            return PathBuf::from(python);
        }
    }

    let venv_python = if cfg!(windows) {
        app_root.join(".venv").join("Scripts").join("python.exe")
    } else {
        app_root.join(".venv").join("bin").join("python")
    };
    if venv_python.is_file() {
        return venv_python;
    }

    PathBuf::from("python3")
}

pub(crate) fn merged_backend_origins() -> String {
    match env::var("INKMOMENT_DEV_ORIGINS") {
        Ok(existing) if !existing.trim().is_empty() => {
            format!("{existing},{DEFAULT_BACKEND_ORIGINS}")
        }
        _ => DEFAULT_BACKEND_ORIGINS.to_string(),
    }
}


#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bundled_sidecar_search_dirs_include_macos_executable_dir() {
        let resource_dir = PathBuf::from("/tmp/InkMoment.app/Contents/Resources");
        let dirs = bundled_sidecar_search_dirs(&resource_dir);
        assert!(dirs.contains(&resource_dir));
        assert!(dirs.contains(
            &PathBuf::from("/tmp/InkMoment.app/Contents/Resources")
                .join("binaries")
                .join("inkmoment-sidecar")
        ));
        if cfg!(target_os = "macos") {
            assert!(dirs.contains(&PathBuf::from("/tmp/InkMoment.app/Contents/MacOS")));
        }
    }

}
