from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from typing import Callable

from flask import Blueprint, redirect, render_template, request, url_for

from auth_server.security import confirmed as _confirmed
from auth_server.services.pagination import pagination_meta as _pagination_meta
from auth_server.store import (
    ADMIN_PERMISSION_ADMINS_READ,
    ADMIN_PERMISSION_ADMINS_WRITE,
    ADMIN_PERMISSION_CDKS_READ,
    ADMIN_PERMISSION_CDKS_WRITE,
    ADMIN_PERMISSION_USERS_READ,
    ADMIN_PERMISSION_USERS_WRITE,
    ADMIN_ROLE_AGENT,
    ADMIN_ROLE_AUDITOR,
    ADMIN_ROLE_OPERATOR,
    AuthStore,
)


ADMIN_DASHBOARD_ENDPOINT = "admin_dashboard.admin_dashboard"


@dataclass(frozen=True)
class AdminDashboardDeps:
    store: AuthStore
    require_admin_page: Callable
    can_admin: Callable[[str], bool]
    admin_actor: Callable[[], str]


def create_admin_dashboard_blueprint(deps: AdminDashboardDeps) -> Blueprint:
    bp = Blueprint("admin_dashboard", __name__)
    store = deps.store
    require_admin_page = deps.require_admin_page
    can_admin = deps.can_admin
    admin_actor = deps.admin_actor

    def admin_error_page(message: str, status_code: int = 400):
        return render_template("admin/message.html", message=message), status_code

    @bp.route("/admin")
    @require_admin_page(ADMIN_PERMISSION_USERS_READ)
    def admin_dashboard():
        query = request.args.get("q", "")
        cdk_query = request.args.get("cdk_q", "")
        cdk_status = request.args.get("cdk_status", "")
        cdk_total = store.admin_count_cdks(cdk_query, cdk_status)
        user_total = store.admin_count_users(query)
        cdk_page = _pagination_meta("cdk_page", "cdk_page_size", cdk_total, endpoint=ADMIN_DASHBOARD_ENDPOINT)
        user_page = _pagination_meta("user_page", "user_page_size", user_total, endpoint=ADMIN_DASHBOARD_ENDPOINT)
        users = store.admin_list_users(query, limit=user_page["page_size"], offset=user_page["offset"])
        cdks = store.admin_list_cdks(cdk_query, cdk_status, limit=cdk_page["page_size"], offset=cdk_page["offset"])
        return render_template(
            "admin/dashboard.html",
            active_nav="dashboard",
            metrics=store.admin_dashboard_metrics(),
            users=users,
            cdks=cdks,
            cdk_page=cdk_page,
            user_page=user_page,
            active_cdk_total=store.admin_count_cdks(cdk_query, "active"),
            query=query,
            cdk_query=cdk_query,
            cdk_status=cdk_status,
            recent_events=store.admin_list_events(limit=8),
            recent_errors=store.admin_list_error_logs(unresolved_only=True, limit=6),
        )

    @bp.route("/admin/ui/users")
    @require_admin_page(ADMIN_PERMISSION_USERS_READ)
    def admin_users_page():
        query = request.args.get("q", "")
        total = store.admin_count_users(query)
        page = _pagination_meta("page", "page_size", total, endpoint="admin_dashboard.admin_users_page")
        return render_template(
            "admin/users.html",
            active_nav="users",
            users=store.admin_list_users(query, limit=page["page_size"], offset=page["offset"]),
            page=page,
            query=query,
        )

    @bp.route("/admin/ui/cdks")
    @require_admin_page(ADMIN_PERMISSION_CDKS_READ)
    def admin_cdks_page():
        query = request.args.get("q", "")
        status = request.args.get("status", "")
        total = store.admin_count_cdks(query, status)
        page = _pagination_meta("page", "page_size", total, endpoint="admin_dashboard.admin_cdks_page")
        return render_template(
            "admin/cdks.html",
            active_nav="cdks",
            cdks=store.admin_list_cdks(query, status, limit=page["page_size"], offset=page["offset"]),
            page=page,
            query=query,
            status=status,
        )

    @bp.route("/admin/ui/devices")
    @require_admin_page(ADMIN_PERMISSION_USERS_READ)
    def admin_devices_page():
        filters = {
            "q": request.args.get("q", "").strip(),
            "status": request.args.get("status", "").strip().lower(),
        }
        return render_template(
            "admin/devices.html",
            active_nav="devices",
            devices=store.admin_list_devices(filters["q"], filters["status"], limit=300),
            filters=filters,
        )

    @bp.route("/admin/ui/notices")
    @require_admin_page(ADMIN_PERMISSION_USERS_READ)
    def admin_notices_page():
        return render_template(
            "admin/notices.html",
            active_nav="notices",
            notices=store.admin_list_notices(limit=200),
            can=can_admin,
        )

    @bp.route("/admin/ui/client-config")
    @require_admin_page(ADMIN_PERMISSION_USERS_READ)
    def admin_client_config_page():
        return render_template(
            "admin/client_config.html",
            active_nav="client_config",
            config=store.admin_get_client_config(),
            can=can_admin,
        )

    @bp.route("/admin/ui/errors")
    @require_admin_page(ADMIN_PERMISSION_USERS_READ)
    def admin_errors_page():
        filters = {
            "q": request.args.get("q", "").strip(),
            "severity": request.args.get("severity", "").strip().lower(),
            "unresolved": request.args.get("unresolved", "1") == "1",
        }
        return render_template(
            "admin/errors.html",
            active_nav="errors",
            errors=store.admin_list_error_logs(
                filters["q"],
                filters["severity"],
                unresolved_only=filters["unresolved"],
                limit=300,
            ),
            filters=filters,
            can=can_admin,
        )

    @bp.route("/admin/ui/events")
    @require_admin_page(ADMIN_PERMISSION_USERS_READ)
    def admin_events_page():
        filters = {
            "source": request.args.get("source", "").strip().lower(),
            "email": request.args.get("email", "").strip(),
            "event_type": request.args.get("event_type", "").strip(),
            "q": request.args.get("q", "").strip(),
        }
        return render_template(
            "admin/events.html",
            active_nav="audit",
            events=store.admin_list_events(
                source=filters["source"],
                email=filters["email"],
                event_type=filters["event_type"],
                query=filters["q"],
                limit=300,
            ),
            filters=filters,
        )

    @bp.route("/admin/ui/backups")
    @require_admin_page(ADMIN_PERMISSION_ADMINS_READ)
    def admin_backups_page():
        return render_template(
            "admin/backups.html",
            active_nav="backups",
            backups=store.admin_list_backups(limit=200),
            db_path=store.path,
            can=can_admin,
        )

    @bp.route("/admin/ui/admins")
    @require_admin_page(ADMIN_PERMISSION_ADMINS_READ)
    def admin_admins_page():
        return render_template(
            "admin/admins.html",
            active_nav="admins",
            admins=store.admin_list_admins(limit=200),
            can=can_admin,
        )

    @bp.route("/admin/ui/cdks", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_CDKS_WRITE)
    def admin_ui_create_cdk():
        try:
            code = request.form.get("code") or secrets.token_urlsafe(12).upper()
            duration_days = int(request.form.get("duration_days") or 0)
            count = int(request.form.get("count") or 1)
            if count > 1:
                if not _confirmed(request.form):
                    return admin_error_page("批量生成 CDK 需要二次确认", 409)
                store.admin_create_cdks(
                    duration_days,
                    count,
                    prefix=request.form.get("prefix") or "INKMOMENT",
                    actor=admin_actor(),
                )
            else:
                store.create_cdk(code, duration_days, actor=admin_actor())
        except (TypeError, ValueError) as exc:
            return admin_error_page(str(exc), 400)
        return redirect(url_for(".admin_cdks_page"))

    @bp.route("/admin/ui/cdks/<path:code>/disable", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_CDKS_WRITE)
    def admin_ui_disable_cdk(code):
        if not _confirmed(request.form):
            return admin_error_page("禁用 CDK 需要二次确认", 409)
        try:
            store.admin_disable_cdk(code, reason=request.form.get("reason") or "", actor=admin_actor())
        except ValueError as exc:
            return admin_error_page(str(exc), 400)
        return redirect(url_for(".admin_cdks_page"))

    @bp.route("/admin/ui/admins", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_ADMINS_WRITE)
    def admin_ui_create_admin():
        role = (request.form.get("role") or ADMIN_ROLE_AGENT).strip().lower()
        if role not in {ADMIN_ROLE_AGENT, ADMIN_ROLE_OPERATOR, ADMIN_ROLE_AUDITOR}:
            return admin_error_page("只能创建 agent、operator 或 auditor 子账号", 400)
        try:
            store.create_admin(
                request.form.get("username") or "",
                request.form.get("password") or "",
                display_name=request.form.get("display_name") or "",
                role=role,
            )
        except ValueError as exc:
            return admin_error_page(str(exc), 400)
        return redirect(url_for(".admin_admins_page"))

    @bp.route("/admin/ui/notices", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_USERS_WRITE)
    def admin_ui_save_notice():
        try:
            store.admin_upsert_notice(
                request.form.get("title") or "",
                request.form.get("body") or "",
                notice_id=request.form.get("id") or "",
                audience=request.form.get("audience") or "all",
                severity=request.form.get("severity") or "info",
                app_version=request.form.get("app_version") or "",
                published=_form_bool("published", default=True),
                pinned=_form_bool("pinned"),
                actor=admin_actor(),
            )
        except ValueError as exc:
            return admin_error_page(str(exc), 400)
        return redirect(url_for(".admin_notices_page"))

    @bp.route("/admin/ui/notices/<notice_id>/publish", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_USERS_WRITE)
    def admin_ui_publish_notice(notice_id):
        try:
            store.admin_set_notice_published(
                notice_id,
                _form_bool("published", default=True),
                actor=admin_actor(),
            )
        except ValueError as exc:
            return admin_error_page(str(exc), 400)
        return redirect(url_for(".admin_notices_page"))

    @bp.route("/admin/ui/client-config", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_USERS_WRITE)
    def admin_ui_update_client_config():
        try:
            feature_flags = json.loads(request.form.get("feature_flags") or "{}")
            config = {
                "maintenance": _form_bool("maintenance"),
                "maintenance_message": request.form.get("maintenance_message") or "",
                "auth_base_url": request.form.get("auth_base_url") or "",
                "download_concurrency": int(request.form.get("download_concurrency") or 2),
                "feature_flags": feature_flags,
            }
            store.admin_update_client_config(config, actor=admin_actor())
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return admin_error_page(f"客户端配置无效：{exc}", 400)
        return redirect(url_for(".admin_client_config_page"))

    @bp.route("/admin/ui/errors/<log_id>/resolve", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_USERS_WRITE)
    def admin_ui_resolve_error(log_id):
        try:
            store.admin_resolve_error_log(log_id, actor=admin_actor())
        except ValueError as exc:
            return admin_error_page(str(exc), 400)
        return redirect(url_for(".admin_errors_page"))

    @bp.route("/admin/ui/backups", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_ADMINS_WRITE)
    def admin_ui_create_backup():
        if not _confirmed(request.form):
            return admin_error_page("创建备份需要二次确认", 409)
        store.admin_create_backup(request.form.get("label") or "", actor=admin_actor())
        return redirect(url_for(".admin_backups_page"))

    @bp.route("/admin/ui/backups/<backup_id>/restore", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_ADMINS_WRITE)
    def admin_ui_restore_backup(backup_id):
        if not _confirmed(request.form):
            return admin_error_page("恢复备份需要二次确认", 409)
        try:
            store.admin_restore_backup(backup_id, actor=admin_actor())
        except ValueError as exc:
            return admin_error_page(str(exc), 400)
        return redirect(url_for(".admin_backups_page"))

    @bp.route("/admin/ui/users/<path:email>")
    @require_admin_page(ADMIN_PERMISSION_USERS_READ)
    def admin_user_page(email):
        user = store.admin_get_user(email)
        if user is None:
            return render_template("admin/message.html", message="账号不存在"), 404
        return render_template("admin/user.html", active_nav="users", user=user, can=can_admin)

    @bp.route("/admin/ui/users/<path:email>/status", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_USERS_WRITE)
    def admin_ui_set_status(email):
        next_status = request.form.get("status") or ""
        if next_status.strip().lower() == "disabled" and not _confirmed(request.form):
            return admin_error_page("禁用账号需要二次确认", 409)
        try:
            store.admin_set_user_status(email, next_status, request.form.get("reason") or "", operator=admin_actor())
        except ValueError as exc:
            return admin_error_page(str(exc), 400)
        return redirect(url_for(".admin_user_page", email=email))

    @bp.route("/admin/ui/users/<path:email>/license", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_USERS_WRITE)
    def admin_ui_adjust_license(email):
        try:
            add_days = int(request.form.get("add_days") or 0)
            if add_days < 0 and not _confirmed(request.form):
                return admin_error_page("扣减授权期限需要二次确认", 409)
            store.admin_adjust_license(
                email,
                add_days=add_days,
                reason=request.form.get("reason") or "",
                operator=admin_actor(),
            )
        except (TypeError, ValueError) as exc:
            return admin_error_page(str(exc), 400)
        return redirect(url_for(".admin_user_page", email=email))

    @bp.route("/admin/ui/users/<path:email>/device/unbind", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_USERS_WRITE)
    def admin_ui_unbind_device(email):
        if not _confirmed(request.form):
            return admin_error_page("解除设备绑定需要二次确认", 409)
        try:
            store.admin_unbind_device(
                email,
                deduct_days=int(request.form.get("deduct_days") or 3),
                reason=request.form.get("reason") or "",
                operator=admin_actor(),
            )
        except (TypeError, ValueError) as exc:
            return admin_error_page(str(exc), 400)
        return redirect(url_for(".admin_user_page", email=email))

    @bp.route("/admin/ui/users/<path:email>/sessions/revoke", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_USERS_WRITE)
    def admin_ui_revoke_sessions(email):
        if not _confirmed(request.form):
            return admin_error_page("吊销 session 需要二次确认", 409)
        store.admin_revoke_sessions(email, operator=admin_actor())
        return redirect(url_for(".admin_user_page", email=email))

    @bp.route("/admin/ui/users/<path:email>/sessions/<token_prefix>/revoke", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_USERS_WRITE)
    def admin_ui_revoke_session(email, token_prefix):
        if not _confirmed(request.form):
            return admin_error_page("吊销 session 需要二次确认", 409)
        try:
            store.admin_revoke_session(email, token_prefix, operator=admin_actor())
        except ValueError as exc:
            return admin_error_page(str(exc), 400)
        return redirect(url_for(".admin_user_page", email=email))

    return bp


def _form_bool(name: str, default: bool = False) -> bool:
    if name not in request.form:
        return default
    return str(request.form.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}
