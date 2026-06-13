from __future__ import annotations

from datetime import datetime

from jinja2.runtime import Undefined


def admin_time(value) -> str:
    if value in (None, "") or isinstance(value, Undefined):
        return "-"
    try:
        return datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return str(value)


def account_status_label(value: str) -> str:
    return {
        "active": "正常",
        "disabled": "已禁用",
    }.get(str(value or ""), str(value or "-"))


def license_reason_label(value: str) -> str:
    return {
        "active": "授权有效",
        "not_activated": "未开通",
        "expired": "已过期",
        "revoked": "已撤销",
        "device_mismatch": "设备不匹配",
        "disabled": "账号禁用",
    }.get(str(value or ""), str(value or "-"))


def cdk_status_label(value: str) -> str:
    return {
        "active": "可兑换",
        "redeemed": "已兑换",
        "disabled": "已禁用",
    }.get(str(value or ""), str(value or "-"))


def event_source_label(value: str) -> str:
    return {
        "license": "授权",
        "device": "设备",
        "admin": "管理员",
    }.get(str(value or ""), str(value or "-"))
