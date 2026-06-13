"""本地照片擂台选片工具。

启动:
    python app.py [--port 5057]

打开 http://localhost:5057，在网页里输入要处理的文件夹路径。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import webbrowser
from typing import Optional

from flask import Flask, send_from_directory
from werkzeug.serving import make_server

from inkmoment.grouper import ImageInfo
from server.domain.models import SessionState
from server.settings import Settings, apply_runtime_environment
from server.services.llm_service import load_llm_config_from_file
from server.services.blueprint_registry_service import BlueprintRegistryDeps, register_app_blueprints
from server.services.job_orchestration_service import JobOrchestrationDeps, start_job_payload
from server.services.selection_service import serialize_group
from server.services.session_builder_service import build_session_from_groups as _build_session_from_groups
from server.services.session_apply_service import apply_pending_groups
from server.services.session_state_service import load_state as load_session_state, save_state
from server.services.auth_client_service import AuthRuntime, auth_summary, ensure_recent_authorization
from server.services.client_runtime_config_service import report_client_error
from server.services.job_event_service import emit_job_image_event
from server.services.job_log_service import close_runtime_job_log, open_runtime_job_log
from server.services.logging_service import configure_app_logger
from server.services.runtime_facade_service import (
    cancel_requested,
    cancel_running_work_for_auth_failure,
    clear_session_state,
    emit_runtime_job_event,
    get_auth_runtime,
    get_dependency_download_manager,
    get_state_store,
    infos_from_memory,
    serialize_runtime_group,
    set_session_state,
    set_watermark_job,
    update_job_progress,
)
from server.services.security_service import (
    create_authorization_check,
    create_no_cache_static_hook,
    create_security_check,
    frontend_dist_dir,
)
from server.runtime.app_runtime import AppRuntime, new_grouping_state as _new_grouping_state

__all__ = ["AuthRuntime", "ImageInfo", "_new_grouping_state", "RUNTIME", "create_app"]

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:
    pass


# 可选：用于脚本/curl 访问的 token（默认不开启）
# 设置 INKMOMENT_TOKEN 环境变量即启用
SETTINGS = Settings.load()
apply_runtime_environment(SETTINGS)
SCRIPT_TOKEN = SETTINGS.script_token
DEV_ORIGINS = SETTINGS.dev_origins

# ---------------- 路径 / 日志 ----------------

logger = logging.getLogger("inkmoment")


def load_state(folder):
    return load_session_state(folder, logger)


# 启动期只载入非敏感模型服务配置；Keychain 读取按需懒加载，避免阻塞 sidecar ready。
load_llm_config_from_file(include_secret=False)


def setup_logger(folder: Optional[str]) -> None:
    configure_app_logger(logger, folder)


RUNTIME = AppRuntime()


def _state_store():
    return get_state_store(RUNTIME)


def _auth_runtime():
    return get_auth_runtime(RUNTIME, _state_store)


def _dependency_download_manager():
    return get_dependency_download_manager(RUNTIME, _state_store)


# ---------------- State 持久化 + 迁移 ----------------


def build_session_from_groups(
    folder: str,
    dry_run: bool,
    mode: str,
    raw_groups,
    infos: list,
    threshold_near: int,
    threshold_far: int,
    near_seconds: int,
    prescreen_enabled: bool = True,
    prescreen_strength: str = "standard",
    engine: str = "fast",
) -> SessionState:
    return _build_session_from_groups(
        folder,
        dry_run,
        mode,
        raw_groups,
        infos,
        threshold_near,
        threshold_far,
        near_seconds,
        prescreen_enabled=prescreen_enabled,
        prescreen_strength=prescreen_strength,
        engine=engine,
        save_state_fn=save_state,
        apply_pending_groups_fn=apply_pending_groups,
        log=logger,
    )


def _start_job_payload(data: dict) -> tuple[dict, int]:
    return start_job_payload(
        data,
        JobOrchestrationDeps(
            runtime=RUNTIME,
            logger=logger,
            state_store=_state_store,
            setup_logger=setup_logger,
            open_job_log=lambda folder, engine, llm_model: open_runtime_job_log(
                RUNTIME,
                logger,
                folder,
                engine,
                llm_model,
            ),
            close_job_log=lambda: close_runtime_job_log(RUNTIME),
            build_session_from_groups=build_session_from_groups,
            set_session_state=lambda session, infos=None: set_session_state(RUNTIME, session, infos),
            job_event=lambda name, path, info, reason: emit_runtime_job_event(
                RUNTIME,
                logger,
                emit_job_image_event,
                name,
                path,
                info,
                reason,
            ),
            job_progress=lambda done, total, label: update_job_progress(RUNTIME, done, total, label),
            cancel_check=lambda: cancel_requested(RUNTIME),
        ),
    )


def create_app() -> Flask:
    """Build the Flask app without starting the server.

    Tauri sidecar packaging and tests both need an importable app factory so they
    can control process lifetime, port allocation, and health checks.
    """
    flask_app = Flask(__name__, static_folder="static", static_url_path="/static")
    flask_app.after_request(create_no_cache_static_hook(DEV_ORIGINS))
    flask_app.before_request(create_security_check(SCRIPT_TOKEN, DEV_ORIGINS))
    flask_app.before_request(
        create_authorization_check(
            _state_store,
            _auth_runtime,
            lambda: cancel_running_work_for_auth_failure(RUNTIME),
            ensure_recent_authorization,
            auth_summary,
            lambda message, context: report_client_error(
                _state_store(), message, context=context, runtime=_auth_runtime()
            ),
        )
    )

    @flask_app.route("/")
    def index():
        dist_dir = frontend_dist_dir(flask_app)
        if (dist_dir / "index.html").is_file():
            return send_from_directory(dist_dir, "index.html")
        return send_from_directory(flask_app.static_folder or "static", "index.html")

    @flask_app.route("/assets/<path:filename>")
    def vue_asset(filename: str):
        return send_from_directory(frontend_dist_dir(flask_app) / "assets", filename)

    register_app_blueprints(
        flask_app,
        BlueprintRegistryDeps(
            runtime=RUNTIME,
            logger=logger,
            state_store=_state_store,
            auth_runtime=_auth_runtime,
            dependency_download_manager=_dependency_download_manager,
            infos_from_memory_or_cache=lambda folder: infos_from_memory(RUNTIME, folder),
            set_session_state=lambda session, infos=None: set_session_state(RUNTIME, session, infos),
            build_session_from_groups=build_session_from_groups,
            clear_session_state=lambda: clear_session_state(RUNTIME),
            serialize_group=lambda group, index: serialize_runtime_group(RUNTIME, group, index, serialize_group),
            start_job_payload=_start_job_payload,
            set_watermark_job=lambda job: set_watermark_job(RUNTIME, job),
        ),
    )
    return flask_app


app = create_app()


# ---------------- 入口 ----------------


def main():
    parser = argparse.ArgumentParser(description="本地照片擂台选片工具")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5057)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--repair-dependencies", action="store_true", help="检查并修复当前模式需要的内置模块资源。")
    parser.add_argument("--engine", default="expert", help="--repair-dependencies 使用的模式")
    parser.add_argument("--model-cache-dir", default="", help="--repair-dependencies 使用的模型缓存目录")
    parser.add_argument("--dependency-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--payload", default="", help=argparse.SUPPRESS)
    parser.add_argument("--events", default="", help=argparse.SUPPRESS)
    parser.add_argument("--json-ready", action="store_true", help="Print one JSON line after binding.")
    args = parser.parse_args()

    if args.dependency_worker:
        from server.services.dependencies.process_worker import main as worker_main

        return worker_main(["--payload", args.payload, "--events", args.events])

    if args.repair_dependencies:
        from server.services.dependencies.repair import main as repair_main

        repair_args = ["--engine", args.engine]
        if args.model_cache_dir:
            repair_args.extend(["--cache-dir", args.model_cache_dir])
        return repair_main(repair_args)

    setup_logger(None)
    server = make_server(args.host, args.port, app, threaded=True)
    actual_port = server.server_port
    display_host = "localhost" if args.host in {"127.0.0.1", "0.0.0.0"} else args.host
    url = f"http://{display_host}:{actual_port}"
    connect_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    health_url = f"http://{connect_host}:{actual_port}/api/health"
    ready_payload = {
        "event": "ready",
        "service": "inkmoment",
        "host": args.host,
        "port": actual_port,
        "url": url,
        "health_url": health_url,
        "pid": os.getpid(),
    }
    if args.json_ready:
        print(json.dumps(ready_payload, ensure_ascii=False), flush=True)
    else:
        print(f"\n启动于 {url}", flush=True)
    if SCRIPT_TOKEN:
        print(f"（脚本访问 token 已启用：X-Token: {SCRIPT_TOKEN[:8]}...）", flush=True)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    sys.exit(main())
