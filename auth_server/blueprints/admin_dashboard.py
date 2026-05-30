from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Callable

from flask import Blueprint, redirect, render_template, request, url_for

from auth_server.security import confirmed as _confirmed
from auth_server.services.pagination import pagination_meta as _pagination_meta
from auth_server.store import (
    ADMIN_PERMISSION_ADMINS_READ,
    ADMIN_PERMISSION_ADMINS_WRITE,
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
        cdk_page = _pagination_meta(
            "cdk_page",
            "cdk_page_size",
            cdk_total,
            endpoint=ADMIN_DASHBOARD_ENDPOINT,
        )
        user_page = _pagination_meta(
            "user_page",
            "user_page_size",
            user_total,
            endpoint=ADMIN_DASHBOARD_ENDPOINT,
        )
        users = store.admin_list_users(
            query,
            limit=user_page["page_size"],
            offset=user_page["offset"],
        )
        cdks = store.admin_list_cdks(
            cdk_query,
            cdk_status,
            limit=cdk_page["page_size"],
            offset=cdk_page["offset"],
        )
        active_cdk_total = store.admin_count_cdks(cdk_query, "active")
        admins = store.admin_list_admins(limit=100) if can_admin(ADMIN_PERMISSION_ADMINS_READ) else []
        return render_template(
            "admin/dashboard.html",
            users=users,
            cdks=cdks,
            admins=admins,
            cdk_page=cdk_page,
            user_page=user_page,
            active_cdk_total=active_cdk_total,
            query=query,
            cdk_query=cdk_query,
            cdk_status=cdk_status,
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
        events = store.admin_list_events(
            source=filters["source"],
            email=filters["email"],
            event_type=filters["event_type"],
            query=filters["q"],
            limit=200,
        )
        return render_template(
            "admin/events.html",
            events=events,
            filters=filters,
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
        return redirect(url_for(".admin_dashboard"))

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
        return redirect(url_for(".admin_dashboard"))

    @bp.route("/admin/ui/cdks/<path:code>/disable", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_CDKS_WRITE)
    def admin_ui_disable_cdk(code):
        if not _confirmed(request.form):
            return admin_error_page("禁用 CDK 需要二次确认", 409)
        try:
            store.admin_disable_cdk(
                code,
                reason=request.form.get("reason") or "",
                actor=admin_actor(),
            )
        except ValueError as exc:
            return admin_error_page(str(exc), 400)
        return redirect(url_for(".admin_dashboard"))

    @bp.route("/admin/ui/users/<path:email>")
    @require_admin_page(ADMIN_PERMISSION_USERS_READ)
    def admin_user_page(email):
        user = store.admin_get_user(email)
        if user is None:
            return render_template("admin/message.html", message="账号不存在"), 404
        return render_template("admin/user.html", user=user, can=can_admin)

    @bp.route("/admin/ui/users/<path:email>/status", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_USERS_WRITE)
    def admin_ui_set_status(email):
        next_status = request.form.get("status") or ""
        if next_status.strip().lower() == "disabled" and not _confirmed(request.form):
            return admin_error_page("禁用账号需要二次确认", 409)
        try:
            store.admin_set_user_status(
                email,
                next_status,
                request.form.get("reason") or "",
                operator=admin_actor(),
            )
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
