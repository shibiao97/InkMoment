from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from flask import Flask

from inkmoment.grouper import (
    NEAR_SECONDS,
    THRESHOLD_FAR,
    THRESHOLD_NEAR,
    ImageInfo,
    group_infos,
)
from server.domain.models import GroupState, SessionState
from server.routes.auth import AuthDeps, create_auth_blueprint
from server.routes.dependencies import DependenciesDeps, create_dependencies_blueprint
from server.routes.export import ExportDeps, create_export_blueprint
from server.routes.folder import FolderDeps, create_folder_blueprint
from server.routes.grouping import GroupingDeps, create_grouping_blueprint
from server.routes.image import ImageDeps, create_image_blueprint
from server.routes.job import JobDeps, create_job_blueprint
from server.routes.llm import LlmDeps, create_llm_blueprint
from server.routes.results import ResultsDeps, create_results_blueprint
from server.routes.selection import create_selection_blueprint
from server.routes.session import SessionDeps, create_session_blueprint
from server.routes.start import StartDeps, create_start_blueprint
from server.routes.system import SystemDeps, create_system_blueprint
from server.routes.task_history import TaskHistoryDeps, create_task_history_blueprint
from server.routes.watermark import WatermarkDeps, create_watermark_blueprint
from server.runtime.app_runtime import AppRuntime
from server.services.auth_client_service import (
    auth_summary,
    login as auth_login,
    logout as auth_logout,
    redeem_cdk as auth_redeem_cdk,
    refresh_status as auth_refresh_status,
    register as auth_register,
    unbind_device as auth_unbind_device,
)
from server.services.dependency_service import preflight_dependencies_payload
from server.services.export_service import (
    export_cancel_payload,
    export_open_out_dir_payload,
    export_preview_payload,
    export_start_payload,
    export_status_payload,
)
from server.services.grouping_service import create_confirm_prescreen_handler
from server.services.job_file_service import pic_dir, record_skipped_items, skipped_log_path
from server.services.llm_service import (
    clear_ark_key,
    diagnostics_payload,
    get_ark_key_status,
    get_llm_concurrency,
    list_llm_models,
    set_ark_key,
)
from server.services.result_service import restore_rejected_payload
from server.services.selection_service import create_selection_handlers
from server.services.session_apply_service import (
    apply_group,
    apply_pending_groups,
    losers_dir,
    reopen_group,
    unique_target,
    winners_dir,
)
from server.services.session_state_service import group_from_dict, save_state
from server.services.task_history_service import record_job_finished
from server.services.watermark_service import (
    WatermarkJobState,
    watermark_cancel_payload,
    watermark_open_out_dir_payload,
    watermark_preview_payload,
    watermark_start_payload,
    watermark_status_payload,
    watermark_templates_payload,
)


@dataclass(frozen=True)
class BlueprintRegistryDeps:
    runtime: AppRuntime
    logger: object
    state_store: Callable[[], object]
    auth_runtime: Callable[[], object]
    dependency_download_manager: Callable[[], object]
    infos_from_memory_or_cache: Callable[[str], list[ImageInfo]]
    set_session_state: Callable[[SessionState, Optional[list[ImageInfo]]], None]
    build_session_from_groups: Callable
    clear_session_state: Callable[[], None]
    serialize_group: Callable[[GroupState, int], dict]
    start_job_payload: Callable[[dict], tuple[dict, int]]
    set_watermark_job: Callable[[WatermarkJobState], None]


def register_app_blueprints(flask_app: Flask, deps: BlueprintRegistryDeps) -> None:
    runtime = deps.runtime
    logger = deps.logger

    confirm_prescreen = create_confirm_prescreen_handler(
        get_session=lambda: runtime.session,
        get_infos=deps.infos_from_memory_or_cache,
        grouping_state=runtime.grouping,
        lock=runtime.lock,
        group_infos_fn=group_infos,
        build_session_fn=deps.build_session_from_groups,
        group_state_cls=GroupState,
        apply_pending_groups_fn=apply_pending_groups,
        save_state_fn=save_state,
        set_session_unlocked=lambda session: setattr(runtime, "session", session),
        log_error=logger.error,
    )

    flask_app.register_blueprint(
        create_folder_blueprint(
            FolderDeps(
                get_session=lambda: runtime.session,
                pic_dir_factory=pic_dir,
                skipped_log_path_factory=skipped_log_path,
            )
        )
    )
    flask_app.register_blueprint(
        create_auth_blueprint(
            AuthDeps(
                get_status=lambda: auth_summary(deps.auth_runtime()),
                login=lambda email, password: auth_login(deps.state_store(), deps.auth_runtime(), email, password),
                register=lambda email, password, display_name: auth_register(
                    deps.state_store(),
                    deps.auth_runtime(),
                    email,
                    password,
                    display_name,
                ),
                redeem=lambda code: auth_redeem_cdk(deps.state_store(), deps.auth_runtime(), code),
                unbind_device=lambda confirm_penalty, reason: auth_unbind_device(
                    deps.state_store(),
                    deps.auth_runtime(),
                    confirm_penalty,
                    reason,
                ),
                logout=lambda: auth_logout(deps.state_store(), deps.auth_runtime()),
                refresh=lambda: auth_refresh_status(deps.state_store(), deps.auth_runtime()),
            )
        )
    )
    flask_app.register_blueprint(
        create_dependencies_blueprint(
            DependenciesDeps(
                preflight_dependencies=lambda data: preflight_dependencies_payload(data, deps.state_store()),
                download_dependencies=lambda data: deps.dependency_download_manager().start(data),
                download_status=lambda: deps.dependency_download_manager().status(),
                download_cancel=lambda: deps.dependency_download_manager().cancel(),
            )
        )
    )
    flask_app.register_blueprint(
        create_job_blueprint(
            JobDeps(
                get_job=lambda: runtime.job,
                get_job_log=lambda: runtime.job_log,
                get_session=lambda: runtime.session,
                jobs_dir_factory=lambda folder: pic_dir(folder) / "jobs",
                after_cancel=lambda job: record_job_finished(deps.state_store(), job, logger),
            )
        )
    )
    flask_app.register_blueprint(
        create_grouping_blueprint(
            GroupingDeps(
                get_session=lambda: runtime.session,
                set_session=deps.set_session_state,
                get_last_infos=lambda: runtime.last_infos,
                get_grouping_state=lambda: runtime.grouping,
                group_infos=group_infos,
                build_session_from_groups=deps.build_session_from_groups,
                thresholds={
                    "threshold_near": THRESHOLD_NEAR,
                    "threshold_far": THRESHOLD_FAR,
                    "near_seconds": NEAR_SECONDS,
                },
                confirm_prescreen=confirm_prescreen,
            )
        )
    )
    flask_app.register_blueprint(
        create_image_blueprint(
            ImageDeps(
                get_session_folder=lambda: runtime.session.folder if runtime.session is not None else None,
            )
        )
    )
    flask_app.register_blueprint(
        create_llm_blueprint(
            LlmDeps(
                ark_key_status=get_ark_key_status,
                set_ark_key=set_ark_key,
                clear_ark_key=clear_ark_key,
                list_llm_models=lambda force: list_llm_models(force=force),
                diagnostics=diagnostics_payload,
                llm_concurrency=get_llm_concurrency,
            )
        )
    )
    flask_app.register_blueprint(
        create_results_blueprint(
            ResultsDeps(
                get_session=lambda: runtime.session,
                winners_dir_factory=winners_dir,
                losers_dir_factory=losers_dir,
                restore_rejected=lambda data: restore_rejected_payload(
                    data,
                    lambda: runtime.session,
                    runtime.lock,
                    winners_dir,
                    losers_dir,
                    unique_target,
                    save_state,
                    logger,
                ),
            )
        )
    )
    flask_app.register_blueprint(
        create_session_blueprint(
            SessionDeps(
                get_session=lambda: runtime.session,
                clear_session=deps.clear_session_state,
                get_job=lambda: runtime.job,
                get_job_log=lambda: runtime.job_log,
                infos_provider=deps.infos_from_memory_or_cache,
            )
        )
    )
    flask_app.register_blueprint(
        create_system_blueprint(
            SystemDeps(
                get_job=lambda: runtime.job,
                get_session=lambda: runtime.session,
            )
        )
    )
    flask_app.register_blueprint(
        create_start_blueprint(
            StartDeps(
                start_job=deps.start_job_payload,
            )
        )
    )
    flask_app.register_blueprint(
        create_task_history_blueprint(
            TaskHistoryDeps(
                list_recent_tasks=lambda limit: deps.state_store().list_recent_tasks(limit),
            )
        )
    )
    flask_app.register_blueprint(
        create_watermark_blueprint(
            WatermarkDeps(
                list_templates=watermark_templates_payload,
                preview_watermark=lambda data: watermark_preview_payload(data, runtime.session, winners_dir, logger),
                start_watermark=lambda data: watermark_start_payload(
                    data,
                    runtime.session,
                    runtime.watermark_job,
                    deps.set_watermark_job,
                    winners_dir,
                    logger,
                ),
                get_watermark_status=lambda: watermark_status_payload(runtime.watermark_job),
                cancel_watermark=lambda: watermark_cancel_payload(runtime.watermark_job),
                open_watermark_out_dir=lambda: watermark_open_out_dir_payload(runtime.watermark_job),
            )
        )
    )
    flask_app.register_blueprint(
        create_export_blueprint(
            ExportDeps(
                preview_export=lambda data: export_preview_payload(data, runtime.session, winners_dir, logger),
                start_export=lambda data: export_start_payload(
                    data,
                    runtime.session,
                    runtime.watermark_job,
                    deps.set_watermark_job,
                    winners_dir,
                    logger,
                ),
                get_export_status=lambda: export_status_payload(runtime.watermark_job),
                cancel_export=lambda: export_cancel_payload(runtime.watermark_job),
                open_export_out_dir=lambda: export_open_out_dir_payload(runtime.watermark_job),
            )
        )
    )
    selection_handlers = create_selection_handlers(
        get_session=lambda: runtime.session,
        lock=runtime.lock,
        serialize_group_callback=deps.serialize_group,
        group_from_dict=group_from_dict,
        apply_group_callback=apply_group,
        reopen_group_callback=reopen_group,
        record_skipped_callback=lambda folder, items: record_skipped_items(folder, items, logger),
        save_state=save_state,
        log_warning=logger.warning,
    )
    flask_app.register_blueprint(create_selection_blueprint(selection_handlers))
