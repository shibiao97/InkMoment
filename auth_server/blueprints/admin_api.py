from __future__ import annotations

import csv
import io
import secrets
from dataclasses import dataclass
from typing import Callable

from flask import Blueprint, Response, jsonify, request, send_file

from auth_server.config import ADMIN_EXPORT_LIMIT_MAX
from auth_server.security import (
    confirmation_required_response,
    confirmed,
    permission_denied_response,
)
from auth_server.services.pagination import bounded_limit
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


@dataclass(frozen=True)
class AdminApiDeps:
    store: AuthStore
    require_admin: Callable
    can_admin: Callable[[str], bool]
    admin_actor: Callable[[], str]


def create_admin_api_blueprint(deps: AdminApiDeps) -> Blueprint:
    bp = Blueprint("admin_api", __name__)
    store = deps.store
    require_admin = deps.require_admin
    can_admin = deps.can_admin
    admin_actor = deps.admin_actor

    @bp.route("/admin/cdks", methods=["GET", "POST"])
    @require_admin
    def admin_cdks():
        if request.method == "GET":
            if not can_admin(ADMIN_PERMISSION_CDKS_READ):
                return permission_denied_response(ADMIN_PERMISSION_CDKS_READ)
            return jsonify(
                {
                    "cdks": store.admin_list_cdks(
                        request.args.get("q", ""),
                        request.args.get("status", ""),
                        limit=bounded_limit(request.args.get("limit"), 200),
                    )
                }
            )
        if not can_admin(ADMIN_PERMISSION_CDKS_WRITE):
            return permission_denied_response(ADMIN_PERMISSION_CDKS_WRITE)
        data = request.get_json(silent=True) or {}
        try:
            count = int(data.get("count") or 1)
            if count > 1:
                if not confirmed(data):
                    return confirmation_required_response()
                payload = store.admin_create_cdks(
                    int(data.get("duration_days") or 0),
                    count,
                    prefix=data.get("prefix") or "INKMOMENT",
                    actor=admin_actor(),
                )
            else:
                payload = store.create_cdk(
                    data.get("code") or secrets.token_urlsafe(12).upper(),
                    int(data.get("duration_days") or 0),
                    actor=admin_actor(),
                )
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify(payload), 201

    @bp.route("/admin/dashboard")
    @require_admin(ADMIN_PERMISSION_USERS_READ)
    def admin_dashboard_metrics():
        return jsonify({"metrics": store.admin_dashboard_metrics()})

    @bp.route("/admin/cdks/<path:code>/disable", methods=["POST"])
    @require_admin(ADMIN_PERMISSION_CDKS_WRITE)
    def admin_disable_cdk(code):
        data = request.get_json(silent=True) or {}
        if not confirmed(data):
            return confirmation_required_response()
        try:
            payload = store.admin_disable_cdk(
                code,
                reason=data.get("reason") or "",
                actor=admin_actor(),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify(payload)

    @bp.route("/admin/cdks/export")
    @require_admin(ADMIN_PERMISSION_CDKS_READ)
    def admin_export_cdks():
        cdks = store.admin_list_cdks(
            request.args.get("q", ""),
            request.args.get("status", ""),
            limit=bounded_limit(request.args.get("limit"), 1000, ADMIN_EXPORT_LIMIT_MAX),
            max_limit=ADMIN_EXPORT_LIMIT_MAX,
        )
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "code",
                "duration_days",
                "status",
                "batch_id",
                "redeemed_by",
                "redeemed_at",
                "created_at",
                "disabled_at",
                "disabled_reason",
            ],
        )
        writer.writeheader()
        writer.writerows(cdks)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=inkmoment-cdks.csv"},
        )

    @bp.route("/admin/users")
    @require_admin(ADMIN_PERMISSION_USERS_READ)
    def admin_users():
        query = request.args.get("q", "")
        return jsonify(
            {
                "users": store.admin_list_users(
                    query,
                    limit=bounded_limit(request.args.get("limit"), 200),
                )
            }
        )

    @bp.route("/admin/devices")
    @require_admin(ADMIN_PERMISSION_USERS_READ)
    def admin_devices():
        return jsonify(
            {
                "devices": store.admin_list_devices(
                    request.args.get("q", ""),
                    request.args.get("status", ""),
                    limit=bounded_limit(request.args.get("limit"), 200),
                )
            }
        )

    @bp.route("/admin/admins", methods=["GET", "POST"])
    @require_admin
    def admin_admins():
        if request.method == "GET":
            if not can_admin(ADMIN_PERMISSION_ADMINS_READ):
                return permission_denied_response(ADMIN_PERMISSION_ADMINS_READ)
            return jsonify(
                {
                    "admins": store.admin_list_admins(
                        limit=bounded_limit(request.args.get("limit"), 200),
                    )
                }
            )
        if not can_admin(ADMIN_PERMISSION_ADMINS_WRITE):
            return permission_denied_response(ADMIN_PERMISSION_ADMINS_WRITE)
        data = request.get_json(silent=True) or {}
        role = (data.get("role") or ADMIN_ROLE_AGENT).strip().lower()
        if role not in {ADMIN_ROLE_AGENT, ADMIN_ROLE_OPERATOR, ADMIN_ROLE_AUDITOR}:
            return jsonify({"error": "只能创建 agent、operator 或 auditor 子账号", "code": "invalid_request"}), 400
        try:
            admin = store.create_admin(
                data.get("username") or "",
                data.get("password") or "",
                display_name=data.get("display_name") or "",
                role=role,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify({"admin": admin}), 201

    @bp.route("/admin/events")
    @require_admin(ADMIN_PERMISSION_USERS_READ)
    def admin_events():
        return jsonify(
            {
                "events": store.admin_list_events(
                    source=request.args.get("source", ""),
                    email=request.args.get("email", ""),
                    event_type=request.args.get("event_type", ""),
                    query=request.args.get("q", ""),
                    limit=bounded_limit(request.args.get("limit"), 100),
                )
            }
        )

    @bp.route("/admin/notices", methods=["GET", "POST"])
    @require_admin
    def admin_notices():
        if request.method == "GET":
            if not can_admin(ADMIN_PERMISSION_USERS_READ):
                return permission_denied_response(ADMIN_PERMISSION_USERS_READ)
            return jsonify(
                {
                    "notices": store.admin_list_notices(
                        request.args.get("audience", ""),
                        published_only=request.args.get("published") == "1",
                        limit=bounded_limit(request.args.get("limit"), 100),
                    )
                }
            )
        if not can_admin(ADMIN_PERMISSION_USERS_WRITE):
            return permission_denied_response(ADMIN_PERMISSION_USERS_WRITE)
        data = request.get_json(silent=True) or {}
        try:
            notice = store.admin_upsert_notice(
                data.get("title") or "",
                data.get("body") or "",
                notice_id=data.get("id") or "",
                audience=data.get("audience") or "all",
                severity=data.get("severity") or "info",
                app_version=data.get("app_version") or "",
                published=bool(data.get("published", True)),
                pinned=bool(data.get("pinned", False)),
                actor=admin_actor(),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify({"notice": notice}), 201

    @bp.route("/admin/notices/<notice_id>/publish", methods=["POST"])
    @require_admin(ADMIN_PERMISSION_USERS_WRITE)
    def admin_publish_notice(notice_id):
        data = request.get_json(silent=True) or {}
        try:
            notice = store.admin_set_notice_published(
                notice_id,
                bool(data.get("published", True)),
                actor=admin_actor(),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify({"notice": notice})

    @bp.route("/admin/client-config", methods=["GET", "POST"])
    @require_admin
    def admin_client_config():
        if request.method == "GET":
            if not can_admin(ADMIN_PERMISSION_USERS_READ):
                return permission_denied_response(ADMIN_PERMISSION_USERS_READ)
            return jsonify({"config": store.admin_get_client_config()})
        if not can_admin(ADMIN_PERMISSION_USERS_WRITE):
            return permission_denied_response(ADMIN_PERMISSION_USERS_WRITE)
        data = request.get_json(silent=True) or {}
        try:
            config = store.admin_update_client_config(data.get("config") or data, actor=admin_actor())
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify({"config": config})

    @bp.route("/admin/error-logs")
    @require_admin(ADMIN_PERMISSION_USERS_READ)
    def admin_error_logs():
        return jsonify(
            {
                "error_logs": store.admin_list_error_logs(
                    request.args.get("q", ""),
                    request.args.get("severity", ""),
                    unresolved_only=request.args.get("unresolved") == "1",
                    limit=bounded_limit(request.args.get("limit"), 100),
                )
            }
        )

    @bp.route("/admin/error-logs/<log_id>/resolve", methods=["POST"])
    @require_admin(ADMIN_PERMISSION_USERS_WRITE)
    def admin_resolve_error_log(log_id):
        try:
            error_log = store.admin_resolve_error_log(log_id, actor=admin_actor())
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify({"error_log": error_log})

    @bp.route("/admin/backups", methods=["GET", "POST"])
    @require_admin
    def admin_backups():
        if request.method == "GET":
            if not can_admin(ADMIN_PERMISSION_ADMINS_READ):
                return permission_denied_response(ADMIN_PERMISSION_ADMINS_READ)
            return jsonify({"backups": store.admin_list_backups(limit=bounded_limit(request.args.get("limit"), 100))})
        if not can_admin(ADMIN_PERMISSION_ADMINS_WRITE):
            return permission_denied_response(ADMIN_PERMISSION_ADMINS_WRITE)
        data = request.get_json(silent=True) or {}
        if not confirmed(data):
            return confirmation_required_response()
        backup = store.admin_create_backup(data.get("label") or "", actor=admin_actor())
        return jsonify({"backup": backup}), 201

    @bp.route("/admin/backups/<backup_id>/download")
    @require_admin(ADMIN_PERMISSION_ADMINS_READ)
    def admin_download_backup(backup_id):
        try:
            path = store.admin_get_backup_path(backup_id)
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return send_file(path, as_attachment=True, download_name=path.name)

    @bp.route("/admin/backups/<backup_id>/restore", methods=["POST"])
    @require_admin(ADMIN_PERMISSION_ADMINS_WRITE)
    def admin_restore_backup(backup_id):
        data = request.get_json(silent=True) or {}
        if not confirmed(data):
            return confirmation_required_response()
        try:
            payload = store.admin_restore_backup(backup_id, actor=admin_actor())
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify(payload)

    @bp.route("/admin/users/<path:email>")
    @require_admin(ADMIN_PERMISSION_USERS_READ)
    def admin_user_detail(email):
        payload = store.admin_get_user(email)
        if payload is None:
            return jsonify({"error": "账号不存在", "code": "not_found"}), 404
        return jsonify(payload)

    @bp.route("/admin/users/<path:email>/status", methods=["POST"])
    @require_admin(ADMIN_PERMISSION_USERS_WRITE)
    def admin_set_status(email):
        data = request.get_json(silent=True) or {}
        next_status = (data.get("status") or "").strip().lower()
        if next_status == "disabled" and not confirmed(data):
            return confirmation_required_response()
        try:
            payload = store.admin_set_user_status(
                email,
                next_status,
                data.get("reason") or "",
                operator=admin_actor(),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify(payload)

    @bp.route("/admin/users/<path:email>/license", methods=["POST"])
    @require_admin(ADMIN_PERMISSION_USERS_WRITE)
    def admin_adjust_license(email):
        data = request.get_json(silent=True) or {}
        try:
            add_days = int(data.get("add_days") or 0)
            if add_days < 0 and not confirmed(data):
                return confirmation_required_response()
            payload = store.admin_adjust_license(
                email,
                add_days=add_days,
                reason=data.get("reason") or "",
                operator=admin_actor(),
            )
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify(payload)

    @bp.route("/admin/users/<path:email>/device/unbind", methods=["POST"])
    @require_admin(ADMIN_PERMISSION_USERS_WRITE)
    def admin_unbind_device(email):
        data = request.get_json(silent=True) or {}
        if not confirmed(data):
            return confirmation_required_response()
        try:
            payload = store.admin_unbind_device(
                email,
                deduct_days=int(data.get("deduct_days", 3)),
                reason=data.get("reason") or "",
                operator=admin_actor(),
            )
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify(payload)

    @bp.route("/admin/users/<path:email>/sessions/revoke", methods=["POST"])
    @require_admin(ADMIN_PERMISSION_USERS_WRITE)
    def admin_revoke_sessions(email):
        data = request.get_json(silent=True) or {}
        if not confirmed(data):
            return confirmation_required_response()
        count = store.admin_revoke_sessions(email, operator=admin_actor())
        return jsonify({"ok": True, "revoked": count})

    @bp.route("/admin/users/<path:email>/sessions/<token_prefix>/revoke", methods=["POST"])
    @require_admin(ADMIN_PERMISSION_USERS_WRITE)
    def admin_revoke_session(email, token_prefix):
        data = request.get_json(silent=True) or {}
        if not confirmed(data):
            return confirmation_required_response()
        try:
            payload = store.admin_revoke_session(
                email,
                token_prefix,
                operator=admin_actor(),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify(payload)

    return bp
