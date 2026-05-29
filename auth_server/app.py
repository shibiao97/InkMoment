from __future__ import annotations

import argparse
import csv
import io
import os
import secrets
import time
from datetime import datetime
from functools import wraps
from typing import Callable

from flask import Flask, Response, g, jsonify, make_response, redirect, render_template_string, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

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
    license_payload,
)


ADMIN_TOKEN_ENV = "INKMOMENT_AUTH_ADMIN_TOKEN"
ADMIN_COOKIE_NAME = "inkmoment_admin_token"
CONFIRM_ACTION_VALUE = "CONFIRM"
HSTS_VALUE = "max-age=31536000; includeSubDomains"
DASHBOARD_PAGE_SIZE_CHOICES = (6, 10, 20, 50)
DEFAULT_DASHBOARD_PAGE_SIZE = 6
ADMIN_API_LIST_LIMIT_MAX = 500
ADMIN_EXPORT_LIMIT_MAX = 5000


def _admin_time(value) -> str:
    if value in (None, ""):
        return "-"
    try:
        return datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return str(value)


def _account_status_label(value: str) -> str:
    return {
        "active": "正常",
        "disabled": "已禁用",
    }.get(str(value or ""), str(value or "-"))


def _license_reason_label(value: str) -> str:
    return {
        "active": "授权有效",
        "not_activated": "未开通",
        "expired": "已过期",
        "revoked": "已撤销",
        "device_mismatch": "设备不匹配",
        "disabled": "账号禁用",
    }.get(str(value or ""), str(value or "-"))


def _cdk_status_label(value: str) -> str:
    return {
        "active": "可兑换",
        "redeemed": "已兑换",
        "disabled": "已禁用",
    }.get(str(value or ""), str(value or "-"))


def _event_source_label(value: str) -> str:
    return {
        "license": "授权",
        "device": "设备",
        "admin": "管理员",
    }.get(str(value or ""), str(value or "-"))


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _bounded_limit(value, default: int = 200, maximum: int = ADMIN_API_LIST_LIMIT_MAX) -> int:
    return _bounded_int(value, default, 1, maximum)


def _pagination_meta(page_param: str, size_param: str, total: int) -> dict:
    page_size = _bounded_int(
        request.args.get(size_param),
        DEFAULT_DASHBOARD_PAGE_SIZE,
        min(DASHBOARD_PAGE_SIZE_CHOICES),
        max(DASHBOARD_PAGE_SIZE_CHOICES),
    )
    if page_size not in DASHBOARD_PAGE_SIZE_CHOICES:
        page_size = DEFAULT_DASHBOARD_PAGE_SIZE
    total = max(0, int(total or 0))
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = _bounded_int(request.args.get(page_param), 1, 1, total_pages)
    offset = (page - 1) * page_size
    start = offset + 1 if total else 0
    end = min(total, offset + page_size) if total else 0

    def page_url(next_page: int) -> str:
        args = request.args.to_dict(flat=True)
        args[page_param] = str(next_page)
        args[size_param] = str(page_size)
        return url_for("admin_dashboard", **args)

    first = max(1, page - 2)
    last = min(total_pages, page + 2)
    return {
        "page": page,
        "page_size": page_size,
        "page_size_choices": DASHBOARD_PAGE_SIZE_CHOICES,
        "total": total,
        "total_pages": total_pages,
        "offset": offset,
        "start": start,
        "end": end,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_url": page_url(max(1, page - 1)),
        "next_url": page_url(min(total_pages, page + 1)),
        "first_url": page_url(1),
        "last_url": page_url(total_pages),
        "page_links": [
            {"page": value, "url": page_url(value), "active": value == page}
            for value in range(first, last + 1)
        ],
    }


ADMIN_BASE_CSS = """
<style>
  :root {
    --bg: #f6f7fb;
    --surface: #ffffff;
    --surface-soft: #f8fafc;
    --text: #111827;
    --muted: #667085;
    --line: #d9e2ec;
    --soft-line: #edf1f6;
    --primary: #2457d6;
    --primary-dark: #1d43a8;
    --success: #168254;
    --warning: #9a6200;
    --danger: #b42318;
    --purple: #6f45b7;
    --shadow: 0 18px 44px rgba(15, 23, 42, .08);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    color: var(--text);
    background: var(--bg);
    font: 14px -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
    overflow-x: hidden;
  }
  h1, h2, h3, p { margin: 0; letter-spacing: 0; }
  h1 { font-size: 26px; line-height: 1.15; }
  h2 { font-size: 17px; line-height: 1.25; }
  h3 { font-size: 14px; line-height: 1.3; }
  a { color: var(--primary); text-decoration: none; }
  a:hover { text-decoration: underline; }
  input, select, button { font: inherit; }
  input, select {
    min-height: 40px;
    padding: 9px 11px;
    color: var(--text);
    background: #fff;
    border: 1px solid var(--line);
    border-radius: 8px;
    outline: none;
  }
  input:focus, select:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(37, 99, 235, .12); }
  button, .btn {
    min-height: 40px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 9px 13px;
    color: #fff;
    background: var(--primary);
    border: 1px solid var(--primary);
    border-radius: 8px;
    cursor: pointer;
    font-weight: 700;
    white-space: nowrap;
  }
  button:hover, .btn:hover { background: var(--primary-dark); text-decoration: none; }
  button.secondary, .btn.secondary { color: var(--text); background: #fff; border-color: var(--line); }
  button.secondary:hover, .btn.secondary:hover { background: #f8fafc; }
  button.danger { background: var(--danger); border-color: var(--danger); }
  button.danger:hover { background: #991b1b; }
  button.subtle, .btn.subtle { color: var(--primary); background: #eef4ff; border-color: #c8d7ff; }
  button.subtle:hover, .btn.subtle:hover { background: #dfe9ff; }
  table { width: 100%; border-collapse: separate; border-spacing: 0; background: var(--surface); }
  th, td { padding: 12px 14px; border-bottom: 1px solid var(--soft-line); text-align: left; vertical-align: top; }
  th {
    color: var(--muted);
    font-size: 12px;
    font-weight: 750;
    background: #f8fafc;
    position: sticky;
    top: 0;
    z-index: 1;
  }
  tr:last-child td { border-bottom: 0; }
  pre {
    max-width: min(680px, 70vw);
    margin: 0;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
    color: #344054;
    font: 12px ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  .app-shell {
    width: 100%;
    min-height: 100vh;
    display: flex;
  }
  .sidebar {
    position: sticky;
    top: 0;
    z-index: 20;
    width: 244px;
    height: 100vh;
    flex: 0 0 244px;
    display: flex;
    flex-direction: column;
    gap: 18px;
    padding: 20px 16px;
    background: #101828;
    color: #e5e7eb;
  }
  .brand-block { display: grid; gap: 7px; padding: 4px 8px 14px; border-bottom: 1px solid rgba(255,255,255,.10); }
  .brand-title { font-size: 17px; font-weight: 800; }
  .brand-subtitle { color: #a7b0c0; font-size: 12px; line-height: 1.5; }
  .nav-list { display: grid; gap: 6px; }
  .nav-link {
    min-height: 40px;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 11px;
    color: #cbd5e1;
    border-radius: 8px;
  }
  .nav-link:hover { background: rgba(255,255,255,.08); color: #fff; text-decoration: none; }
  .nav-link.active { color: #fff; background: #2457d6; }
  .nav-dot { width: 8px; height: 8px; border-radius: 999px; background: currentColor; opacity: .85; }
  .sidebar-footer { margin-top: auto; display: grid; gap: 10px; }
  .sidebar-footer button { width: 100%; color: #f8fafc; background: rgba(255,255,255,.08); border-color: rgba(255,255,255,.14); }
  .content {
    min-width: 0;
    width: 100%;
    max-width: 1720px;
    flex: 1;
    margin: 0 auto;
    padding: clamp(18px, 2vw, 34px);
  }
  .page-head {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: flex-start;
    margin-bottom: 18px;
  }
  .title-block { display: grid; gap: 6px; min-width: 0; }
  .title-block p { color: var(--muted); line-height: 1.6; }
  .nav-actions, .row, form { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .nav-actions { justify-content: flex-end; }
  .stack { display: grid; gap: 16px; }
  .section { margin-top: 16px; }
  .card {
    padding: 18px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 8px;
    box-shadow: var(--shadow);
  }
  .card.compact { padding: 14px; box-shadow: none; }
  .card-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 14px;
  }
  .card-head p { margin-top: 5px; color: var(--muted); font-size: 12px; line-height: 1.5; }
  .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; }
  .metric {
    min-height: 94px;
    padding: 16px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 8px;
    box-shadow: var(--shadow);
  }
  .metric span { color: var(--muted); font-size: 12px; }
  .metric strong { display: block; margin-top: 8px; color: var(--text); font-size: 24px; line-height: 1.1; overflow-wrap: anywhere; }
  .metric small { display: block; margin-top: 8px; color: var(--muted); }
  .split-grid { display: grid; grid-template-columns: minmax(420px, .92fr) minmax(480px, 1.08fr); gap: 16px; align-items: start; }
  .form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; align-items: end; }
  .form-grid.five { grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); }
  .field, .form-grid label {
    display: grid;
    gap: 6px;
    color: var(--muted);
    font-size: 12px;
  }
  .field input, .field select, .form-grid input, .form-grid select { width: 100%; }
  .filters {
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
  }
  .filters input { min-width: min(260px, 100%); flex: 1 1 240px; }
  .filters select { flex: 0 1 140px; }
  .segment {
    display: inline-flex;
    gap: 4px;
    padding: 4px;
    background: #eef2f7;
    border-radius: 8px;
  }
  .segment a {
    min-height: 32px;
    display: inline-flex;
    align-items: center;
    padding: 6px 10px;
    color: #475467;
    border-radius: 6px;
    font-weight: 700;
    font-size: 12px;
  }
  .segment a:hover { background: #fff; text-decoration: none; }
  .segment a.active { color: #fff; background: var(--primary); }
  .table-card {
    min-width: 0;
    overflow: hidden;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 8px;
    box-shadow: var(--shadow);
  }
  .table-toolbar {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: center;
    padding: 16px;
    border-bottom: 1px solid var(--soft-line);
  }
  .table-scroll {
    max-height: min(620px, calc(100vh - 260px));
    overflow: auto;
    overscroll-behavior: contain;
    -webkit-overflow-scrolling: touch;
    touch-action: pan-x pan-y;
    scrollbar-gutter: stable;
  }
  .table-scroll:focus { outline: 3px solid rgba(36, 87, 214, .16); outline-offset: -3px; }
  .table-scroll.short { max-height: 360px; }
  .table-scroll table { min-width: 720px; }
  .event-detail table { min-width: 980px; }
  .scroll-hint {
    padding: 8px 16px;
    color: var(--muted);
    background: #fbfcfe;
    border-bottom: 1px solid var(--soft-line);
    font-size: 12px;
  }
  .pager {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: center;
    padding: 12px 16px;
    border-top: 1px solid var(--soft-line);
    background: #fbfcfe;
  }
  .pager-info { color: var(--muted); font-size: 12px; line-height: 1.5; }
  .pager-actions, .pager-pages, .page-size-form {
    display: inline-flex;
    gap: 6px;
    align-items: center;
    flex-wrap: wrap;
  }
  .pager-link {
    min-height: 34px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 6px 10px;
    color: var(--text);
    background: #fff;
    border: 1px solid var(--line);
    border-radius: 8px;
    font-size: 12px;
    font-weight: 750;
  }
  .pager-link:hover { background: #f8fafc; text-decoration: none; }
  .pager-link.active { color: #fff; background: var(--primary); border-color: var(--primary); }
  .pager-link.disabled { color: #98a2b3; pointer-events: none; background: #f8fafc; }
  .page-size-form { color: var(--muted); font-size: 12px; }
  .page-size-form select {
    min-height: 34px;
    padding: 6px 9px;
    font-size: 12px;
  }
  .identity { display: grid; gap: 4px; min-width: 0; }
  .identity strong, .truncate { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .identity small { color: var(--muted); }
  .muted { color: var(--muted); }
  .danger-text { color: var(--danger); }
  .small { font-size: 12px; }
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .badge {
    display: inline-flex;
    align-items: center;
    min-height: 23px;
    padding: 3px 8px;
    border-radius: 999px;
    background: #eef2ff;
    color: #34418a;
    font-size: 12px;
    font-weight: 750;
    white-space: nowrap;
  }
  .badge-active { background: #e8f6ef; color: var(--success); }
  .badge-redeemed { background: #eef2ff; color: #34418a; }
  .badge-disabled, .badge-expired, .badge-revoked { background: #fff0ed; color: var(--danger); }
  .badge-not_activated { background: #fff7df; color: var(--warning); }
  .badge-device_mismatch { background: #fff7df; color: var(--warning); }
  .badge-license { background: #e8f6ef; color: var(--success); }
  .badge-admin { background: #f0eafa; color: var(--purple); }
  .badge-device { background: #eef4ff; color: var(--primary); }
  .empty { padding: 30px; color: var(--muted); text-align: center; }
  .kv {
    display: grid;
    grid-template-columns: minmax(120px, 150px) minmax(0, 1fr);
    gap: 10px 14px;
  }
  .kv dt { color: var(--muted); }
  .kv dd { margin: 0; overflow-wrap: anywhere; }
  .action-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
  .action-card {
    display: grid;
    gap: 12px;
    padding: 14px;
    background: var(--surface-soft);
    border: 1px solid var(--soft-line);
    border-radius: 8px;
  }
  .action-card p { color: var(--muted); font-size: 12px; line-height: 1.55; }
  .danger-zone { border-color: #f4c7c1; background: #fff8f6; }
  .event-detail pre { max-width: 620px; }
  .login-shell {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 28px 16px;
  }
  .login-panel {
    width: min(1040px, 100%);
    min-height: 560px;
    display: grid;
    grid-template-columns: minmax(0, .9fr) minmax(360px, 1fr);
    overflow: hidden;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 10px;
    box-shadow: 0 30px 80px rgba(15, 23, 42, .16);
  }
  .login-side {
    display: grid;
    align-content: space-between;
    padding: 30px;
    color: #fff;
    background: #101828;
  }
  .login-side h1 { font-size: 30px; }
  .login-side p { margin-top: 10px; color: #cbd5e1; line-height: 1.7; }
  .login-form-wrap { padding: 34px; display: grid; align-content: center; gap: 18px; }
  .login-form { display: grid; gap: 12px; }
  .login-hints { display: grid; gap: 8px; color: #cbd5e1; font-size: 12px; }
  .hint-pill {
    display: inline-flex;
    align-items: center;
    width: fit-content;
    padding: 5px 9px;
    color: #dbeafe;
    background: rgba(36, 87, 214, .22);
    border-radius: 999px;
  }
  @media (min-width: 1800px) {
    .content { max-width: 1840px; padding-inline: 38px; }
    .split-grid { grid-template-columns: minmax(520px, .95fr) minmax(620px, 1.05fr); }
    .table-scroll { max-height: min(720px, calc(100vh - 260px)); }
  }
  @media (max-width: 1320px) {
    .split-grid { grid-template-columns: 1fr; }
    .table-scroll { max-height: 520px; }
  }
  @media (max-width: 1080px) {
    .sidebar {
      width: 220px;
      flex-basis: 220px;
      padding: 18px 14px;
    }
    .content { padding: 18px; }
    .page-head { align-items: stretch; flex-direction: column; }
    .nav-actions { justify-content: flex-start; }
  }
  @media (max-width: 900px) {
    .app-shell { display: block; }
    .sidebar {
      position: sticky;
      width: auto;
      height: auto;
      flex: auto;
      gap: 12px;
      padding: 14px;
      border-bottom: 1px solid rgba(255,255,255,.12);
    }
    .brand-block { padding: 0 4px 10px; }
    .nav-list {
      display: flex;
      gap: 8px;
      overflow-x: auto;
      padding-bottom: 2px;
      scrollbar-width: none;
    }
    .nav-list::-webkit-scrollbar { display: none; }
    .nav-link {
      flex: 0 0 auto;
      min-height: 38px;
      padding: 9px 12px;
      white-space: nowrap;
    }
    .sidebar-footer { margin-top: 0; }
    .content { padding: 16px; }
    .page-head, .card-head, .table-toolbar { align-items: stretch; flex-direction: column; }
    .nav-actions, .filters { justify-content: flex-start; }
    .metric-grid, .split-grid, .form-grid, .form-grid.five, .action-grid { grid-template-columns: 1fr; }
    .kv { grid-template-columns: 1fr; }
    .filters input, .filters select { flex: 1 1 100%; }
    .table-scroll { max-height: min(540px, 64vh); }
    .pager { align-items: stretch; flex-direction: column; }
    .pager-actions { justify-content: space-between; }
    .pager-actions .pager-link { flex: 1 1 auto; }
    .login-shell { align-items: stretch; padding: 16px; }
    .login-panel { grid-template-columns: 1fr; min-height: 0; }
    .login-side { gap: 24px; }
  }
  @media (max-width: 520px) {
    body { font-size: 13px; }
    h1 { font-size: 23px; }
    .content { padding: 12px; }
    .card, .metric { padding: 14px; }
    .metric-grid { grid-template-columns: 1fr 1fr; gap: 10px; }
    .metric strong { font-size: 21px; }
    .nav-actions, .row, form, .filters { align-items: stretch; flex-direction: column; }
    input, select, button, .btn { width: 100%; }
    .pager-link, .page-size-form select { width: auto; }
    .page-size-form button { width: auto; }
    .table-toolbar { padding: 14px; }
    th, td { padding: 10px 12px; }
    .table-scroll table { min-width: 680px; }
    .event-detail table { min-width: 860px; }
    pre { max-width: 76vw; }
    .login-form-wrap, .login-side { padding: 22px; }
  }
  @media (max-width: 380px) {
    .metric-grid { grid-template-columns: 1fr; }
  }
</style>
"""


ADMIN_INTERACTION_JS = """
<script>
  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (!form || !form.dataset.confirm) return;
    if (!window.confirm(form.dataset.confirm)) {
      event.preventDefault();
    }
  });

  document.addEventListener("click", async function (event) {
    const button = event.target.closest("[data-copy]");
    if (!button) return;
    try {
      await navigator.clipboard.writeText(button.dataset.copy || "");
      const original = button.textContent;
      button.textContent = "已复制";
      window.setTimeout(function () { button.textContent = original; }, 1400);
    } catch (_) {}
  });
</script>
"""


ADMIN_LOGIN_TEMPLATE = f"""
<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>InkMoment Admin</title>{ADMIN_BASE_CSS}
<main class="login-shell">
  <section class="login-panel">
    <div class="login-side">
      <div>
        <span class="hint-pill">独立授权服务</span>
        <h1 class="section">InkMoment Admin</h1>
        <p>管理用户授权、CDK 兑换、设备绑定和审计日志。后台只做运营控制，不和桌面端运行进程耦合。</p>
      </div>
      <div class="login-hints">
        <span>用户登录后绑定首台设备</span>
        <span>CDK 决定使用期限</span>
        <span>换机解绑默认扣除 3 天</span>
      </div>
    </div>
    <div class="login-form-wrap">
      <div class="title-block">
        <h2>管理员登录</h2>
        <p>使用部署时创建的管理员账号进入后台。</p>
      </div>
      {{% if error %}}<p class="danger-text">{{{{ error }}}}</p>{{% endif %}}
      <form method="post" class="login-form">
        <label class="field">管理员账号<input name="username" placeholder="admin" autocomplete="username" required></label>
        <label class="field">管理员密码<input name="password" type="password" placeholder="请输入密码" autocomplete="current-password" required></label>
        <button type="submit">进入后台</button>
      </form>
      {{% if allow_bootstrap %}}
        <div class="card compact section">
          <h3>初始化管理员</h3>
          <p class="muted section">首次部署时使用 Bootstrap Token 创建第一个管理员。</p>
          <form method="post" action="{{{{ url_for('admin_bootstrap') }}}}" class="login-form section">
            <label class="field">账号<input name="username" placeholder="admin" autocomplete="username" required></label>
            <label class="field">密码<input name="password" type="password" placeholder="至少 12 位" autocomplete="new-password" required></label>
            <label class="field">Bootstrap Token<input name="admin_token" type="password" placeholder="部署时生成的 token" required></label>
            <button type="submit">创建并登录</button>
          </form>
        </div>
      {{% endif %}}
    </div>
  </section>
</main>{ADMIN_INTERACTION_JS}
"""


ADMIN_DASHBOARD_TEMPLATE = f"""
<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>InkMoment Admin</title>{ADMIN_BASE_CSS}
<main class="app-shell">
  <aside class="sidebar">
    <div class="brand-block">
      <div class="brand-title">InkMoment</div>
      <div class="brand-subtitle">授权管理后台</div>
    </div>
    <nav class="nav-list" aria-label="管理导航">
      <a class="nav-link active" href="{{{{ url_for('admin_dashboard') }}}}"><span class="nav-dot"></span>总览</a>
      <a class="nav-link" href="{{{{ url_for('admin_events_page') }}}}"><span class="nav-dot"></span>审计日志</a>
    </nav>
    <div class="sidebar-footer">
      <form method="post" action="{{{{ url_for('admin_logout') }}}}"><button type="submit">退出登录</button></form>
    </div>
  </aside>

  <section class="content">
    <header class="page-head">
      <div class="title-block">
        <h1>授权管理</h1>
        <p>集中处理用户开通、CDK 发放、设备绑定和异常账号。</p>
      </div>
      <div class="nav-actions">
        <a class="btn secondary" href="{{{{ url_for('admin_events_page') }}}}">查看审计</a>
        <a class="btn secondary" href="{{{{ url_for('admin_export_cdks', q=cdk_query, status=cdk_status, limit=1000) }}}}">导出 CDK</a>
      </div>
    </header>

    <div class="stack">
      <section class="metric-grid">
        <div class="metric"><span>筛选用户</span><strong>{{{{ user_page.total }}}}</strong><small>{{{{ query or '全部用户' }}}}</small></div>
        <div class="metric"><span>筛选 CDK</span><strong>{{{{ cdk_page.total }}}}</strong><small>{{{{ cdk_status|cdk_status_label if cdk_status else '全部状态' }}}}</small></div>
        <div class="metric"><span>可兑换 CDK</span><strong>{{{{ active_cdk_total }}}}</strong><small>{{{{ cdk_query or '全部批次' }}}}</small></div>
        <div class="metric"><span>当前页设备</span><strong>{{{{ users|selectattr('device.bound')|list|length }}}}</strong><small>本页用户内</small></div>
      </section>

      {{% if can('cdks:write') %}}
      <section class="card">
        <div class="card-head">
          <div>
            <h2>发放 CDK</h2>
            <p>单个 CDK 可手动填写；批量生成时使用前缀并自动生成唯一代码。</p>
          </div>
        </div>
        <form method="post" action="{{{{ url_for('admin_ui_create_cdk') }}}}" class="form-grid five" data-confirm="确认生成 CDK？">
          <label>CDK<input name="code" placeholder="留空自动生成"></label>
          <label>授权天数<input name="duration_days" type="number" min="1" placeholder="30" required></label>
          <label>数量<input name="count" type="number" min="1" max="1000" value="1"></label>
          <label>批量前缀<input name="prefix" placeholder="INKMOMENT"></label>
          <input name="confirm_action" type="hidden" value="CONFIRM">
          <button type="submit">生成</button>
        </form>
      </section>
      {{% endif %}}

      {{% if can('admins:read') %}}
      <section class="card">
        <div class="card-head">
          <div>
            <h2>代理子用户</h2>
            <p>创建受限后台账号。agent 可查看用户/CDK 并创建 CDK，不能修改用户授权或解绑设备。</p>
          </div>
        </div>
        {{% if can('admins:write') %}}
        <form method="post" action="{{{{ url_for('admin_ui_create_admin') }}}}" class="form-grid five" data-confirm="确认创建后台子账号？">
          <label>账号<input name="username" placeholder="agent001" autocomplete="off" required></label>
          <label>密码<input name="password" type="password" minlength="12" placeholder="至少 12 位" autocomplete="new-password" required></label>
          <label>显示名<input name="display_name" placeholder="代理名称"></label>
          <label>角色
            <select name="role">
              <option value="agent" selected>代理 agent</option>
              <option value="operator">运营 operator</option>
              <option value="auditor">审计 auditor</option>
            </select>
          </label>
          <input name="confirm_action" type="hidden" value="CONFIRM">
          <button type="submit">创建子用户</button>
        </form>
        {{% endif %}}
        <div class="table-scroll" tabindex="0" aria-label="管理员子用户列表，可上下左右滚动">
          <table>
            <thead><tr><th>账号</th><th>角色</th><th>状态</th><th>最近登录</th><th>权限</th></tr></thead>
            <tbody>
            {{% for admin in admins %}}
              <tr>
                <td><div class="identity"><strong>{{{{ admin.username }}}}</strong><small>{{{{ admin.display_name or '未设置显示名' }}}}</small></div></td>
                <td><span class="badge badge-admin">{{{{ admin.role }}}}</span></td>
                <td>{{{{ admin.status }}}}</td>
                <td>{{{{ admin.last_login_at|admin_time }}}}</td>
                <td><span class="muted small">{{{{ admin.permissions|join(', ') }}}}</span></td>
              </tr>
            {{% else %}}
              <tr><td colspan="5"><div class="empty">暂无后台子用户</div></td></tr>
            {{% endfor %}}
            </tbody>
          </table>
        </div>
      </section>
      {{% endif %}}

      <section class="split-grid">
        <div class="table-card">
          <div class="table-toolbar">
            <div>
              <h2>CDK</h2>
              <p class="muted small">发放、导出和禁用兑换码。</p>
            </div>
            <form class="filters" method="get" action="{{{{ url_for('admin_dashboard') }}}}">
              <input type="hidden" name="q" value="{{{{ query }}}}">
              <input type="hidden" name="user_page" value="{{{{ user_page.page }}}}">
              <input type="hidden" name="user_page_size" value="{{{{ user_page.page_size }}}}">
              <input type="hidden" name="cdk_page_size" value="{{{{ cdk_page.page_size }}}}">
              <input name="cdk_q" value="{{{{ cdk_query }}}}" placeholder="CDK / 账号 / 批次">
              <select name="cdk_status">
                <option value="" {{{{ 'selected' if cdk_status == '' else '' }}}}>全部</option>
                <option value="active" {{{{ 'selected' if cdk_status == 'active' else '' }}}}>可兑换</option>
                <option value="redeemed" {{{{ 'selected' if cdk_status == 'redeemed' else '' }}}}>已兑换</option>
                <option value="disabled" {{{{ 'selected' if cdk_status == 'disabled' else '' }}}}>已禁用</option>
              </select>
              <button type="submit">筛选</button>
            </form>
          </div>
          <div class="scroll-hint">支持鼠标滚轮、触控板和手机滑动；内容较宽时可左右拖动。</div>
          <div class="table-scroll" tabindex="0" aria-label="CDK 列表，可上下左右滚动">
            <table>
              <thead><tr><th>CDK</th><th>状态</th><th>天数</th><th>兑换账号</th><th>操作</th></tr></thead>
              <tbody>
              {{% for cdk in cdks %}}
                <tr>
                  <td>
                    <div class="identity">
                      <strong class="mono">{{{{ cdk.code }}}}</strong>
                      <small>{{{{ cdk.batch_id or '单个创建' }}}} · {{{{ cdk.created_at|admin_time }}}}</small>
                    </div>
                  </td>
                  <td><span class="badge badge-{{{{ cdk.status }}}}">{{{{ cdk.status|cdk_status_label }}}}</span></td>
                  <td>{{{{ cdk.duration_days }}}}</td>
                  <td>
                    {{% if cdk.redeemed_by %}}
                      <a href="{{{{ url_for('admin_user_page', email=cdk.redeemed_by) }}}}">{{{{ cdk.redeemed_by }}}}</a><br><span class="muted small">{{{{ cdk.redeemed_at|admin_time }}}}</span>
                    {{% else %}}
                      <span class="muted">未兑换</span>
                    {{% endif %}}
                  </td>
                  <td>
                    {{% if cdk.status == 'active' and can('cdks:write') %}}
                      <form method="post" action="{{{{ url_for('admin_ui_disable_cdk', code=cdk.code) }}}}" data-confirm="确认禁用这个 CDK？">
                        <input name="reason" placeholder="原因" style="width: 150px;">
                        <input name="confirm_action" type="hidden" value="CONFIRM">
                        <button class="danger" type="submit">禁用</button>
                      </form>
                    {{% else %}}
                      <span class="muted">-</span>
                    {{% endif %}}
                  </td>
                </tr>
              {{% else %}}
                <tr><td colspan="5"><div class="empty">暂无 CDK</div></td></tr>
              {{% endfor %}}
              </tbody>
            </table>
          </div>
          <div class="pager">
            <div class="pager-info">
              CDK：{{{{ cdk_page.start }}}}-{{{{ cdk_page.end }}}} / {{{{ cdk_page.total }}}}，第 {{{{ cdk_page.page }}}} / {{{{ cdk_page.total_pages }}}} 页
            </div>
            <div class="pager-actions">
              <a class="pager-link {{{{ '' if cdk_page.has_prev else 'disabled' }}}}" href="{{{{ cdk_page.first_url }}}}">首页</a>
              <a class="pager-link {{{{ '' if cdk_page.has_prev else 'disabled' }}}}" href="{{{{ cdk_page.prev_url }}}}">上一页</a>
              <div class="pager-pages">
                {{% for item in cdk_page.page_links %}}
                  <a class="pager-link {{{{ 'active' if item.active else '' }}}}" href="{{{{ item.url }}}}">{{{{ item.page }}}}</a>
                {{% endfor %}}
              </div>
              <a class="pager-link {{{{ '' if cdk_page.has_next else 'disabled' }}}}" href="{{{{ cdk_page.next_url }}}}">下一页</a>
              <a class="pager-link {{{{ '' if cdk_page.has_next else 'disabled' }}}}" href="{{{{ cdk_page.last_url }}}}">末页</a>
              <form class="page-size-form" method="get" action="{{{{ url_for('admin_dashboard') }}}}">
                <input type="hidden" name="q" value="{{{{ query }}}}">
                <input type="hidden" name="cdk_q" value="{{{{ cdk_query }}}}">
                <input type="hidden" name="cdk_status" value="{{{{ cdk_status }}}}">
                <input type="hidden" name="user_page" value="{{{{ user_page.page }}}}">
                <input type="hidden" name="user_page_size" value="{{{{ user_page.page_size }}}}">
                <label>每页
                  <select name="cdk_page_size">
                    {{% for size in cdk_page.page_size_choices %}}
                      <option value="{{{{ size }}}}" {{{{ 'selected' if size == cdk_page.page_size else '' }}}}>{{{{ size }}}}</option>
                    {{% endfor %}}
                  </select>
                </label>
                <button type="submit" class="secondary">应用</button>
              </form>
            </div>
          </div>
        </div>

        <div class="table-card">
          <div class="table-toolbar">
            <div>
              <h2>用户</h2>
              <p class="muted small">查看账号授权、设备和最近登录。</p>
            </div>
            <form class="filters" method="get" action="{{{{ url_for('admin_dashboard') }}}}">
              <input type="hidden" name="cdk_q" value="{{{{ cdk_query }}}}">
              <input type="hidden" name="cdk_status" value="{{{{ cdk_status }}}}">
              <input type="hidden" name="cdk_page" value="{{{{ cdk_page.page }}}}">
              <input type="hidden" name="cdk_page_size" value="{{{{ cdk_page.page_size }}}}">
              <input type="hidden" name="user_page_size" value="{{{{ user_page.page_size }}}}">
              <input name="q" value="{{{{ query }}}}" placeholder="邮箱或显示名">
              <button type="submit">搜索</button>
              {{% if query %}}<a class="btn secondary" href="{{{{ url_for('admin_dashboard', cdk_q=cdk_query, cdk_status=cdk_status, cdk_page=cdk_page.page, cdk_page_size=cdk_page.page_size, user_page_size=user_page.page_size) }}}}">清空</a>{{% endif %}}
            </form>
          </div>
          <div class="scroll-hint">支持鼠标滚轮、触控板和手机滑动；设备指纹较长时可左右拖动。</div>
          <div class="table-scroll" tabindex="0" aria-label="用户列表，可上下左右滚动">
            <table>
              <thead><tr><th>账号</th><th>状态</th><th>授权</th><th>设备</th><th></th></tr></thead>
              <tbody>
              {{% for user in users %}}
                <tr>
                  <td><div class="identity"><strong>{{{{ user.email }}}}</strong><small>{{{{ user.display_name or '未设置显示名' }}}}</small></div></td>
                  <td><span class="badge badge-{{{{ user.status }}}}">{{{{ user.status|account_status_label }}}}</span></td>
                  <td><span class="badge badge-{{{{ user.license.reason }}}}">{{{{ user.license.reason|license_reason_label }}}}</span><br><span class="muted small">{{{{ user.license_expires_at|admin_time }}}}</span></td>
                  <td>{{% if user.device.bound %}}<span class="truncate">{{{{ user.device.name or '已绑定设备' }}}}</span><br><span class="muted small mono truncate">{{{{ user.device.fingerprint }}}}</span>{{% else %}}<span class="muted">未绑定</span>{{% endif %}}</td>
                  <td><a class="btn secondary" href="{{{{ url_for('admin_user_page', email=user.email) }}}}">详情</a></td>
                </tr>
              {{% else %}}
                <tr><td colspan="5"><div class="empty">暂无用户</div></td></tr>
              {{% endfor %}}
              </tbody>
            </table>
          </div>
          <div class="pager">
            <div class="pager-info">
              用户：{{{{ user_page.start }}}}-{{{{ user_page.end }}}} / {{{{ user_page.total }}}}，第 {{{{ user_page.page }}}} / {{{{ user_page.total_pages }}}} 页
            </div>
            <div class="pager-actions">
              <a class="pager-link {{{{ '' if user_page.has_prev else 'disabled' }}}}" href="{{{{ user_page.first_url }}}}">首页</a>
              <a class="pager-link {{{{ '' if user_page.has_prev else 'disabled' }}}}" href="{{{{ user_page.prev_url }}}}">上一页</a>
              <div class="pager-pages">
                {{% for item in user_page.page_links %}}
                  <a class="pager-link {{{{ 'active' if item.active else '' }}}}" href="{{{{ item.url }}}}">{{{{ item.page }}}}</a>
                {{% endfor %}}
              </div>
              <a class="pager-link {{{{ '' if user_page.has_next else 'disabled' }}}}" href="{{{{ user_page.next_url }}}}">下一页</a>
              <a class="pager-link {{{{ '' if user_page.has_next else 'disabled' }}}}" href="{{{{ user_page.last_url }}}}">末页</a>
              <form class="page-size-form" method="get" action="{{{{ url_for('admin_dashboard') }}}}">
                <input type="hidden" name="q" value="{{{{ query }}}}">
                <input type="hidden" name="cdk_q" value="{{{{ cdk_query }}}}">
                <input type="hidden" name="cdk_status" value="{{{{ cdk_status }}}}">
                <input type="hidden" name="cdk_page" value="{{{{ cdk_page.page }}}}">
                <input type="hidden" name="cdk_page_size" value="{{{{ cdk_page.page_size }}}}">
                <label>每页
                  <select name="user_page_size">
                    {{% for size in user_page.page_size_choices %}}
                      <option value="{{{{ size }}}}" {{{{ 'selected' if size == user_page.page_size else '' }}}}>{{{{ size }}}}</option>
                    {{% endfor %}}
                  </select>
                </label>
                <button type="submit" class="secondary">应用</button>
              </form>
            </div>
          </div>
        </div>
      </section>
    </div>
  </section>
</main>{ADMIN_INTERACTION_JS}
"""


ADMIN_USER_TEMPLATE = f"""
<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>InkMoment Admin User</title>{ADMIN_BASE_CSS}
<main class="app-shell">
  <aside class="sidebar">
    <div class="brand-block">
      <div class="brand-title">InkMoment</div>
      <div class="brand-subtitle">用户详情</div>
    </div>
    <nav class="nav-list" aria-label="管理导航">
      <a class="nav-link" href="{{{{ url_for('admin_dashboard') }}}}"><span class="nav-dot"></span>总览</a>
      <a class="nav-link" href="{{{{ url_for('admin_events_page', email=user.email) }}}}"><span class="nav-dot"></span>相关审计</a>
    </nav>
    <div class="sidebar-footer">
      <form method="post" action="{{{{ url_for('admin_logout') }}}}"><button type="submit">退出登录</button></form>
    </div>
  </aside>

  <section class="content">
    <header class="page-head">
      <div class="title-block">
        <a href="{{{{ url_for('admin_dashboard') }}}}">← 返回总览</a>
        <h1>{{{{ user.email }}}}</h1>
        <p>{{{{ user.display_name or '未设置显示名' }}}}</p>
      </div>
      <div class="nav-actions">
        <a class="btn secondary" href="{{{{ url_for('admin_events_page', email=user.email) }}}}">相关审计日志</a>
      </div>
    </header>

    <div class="stack">
      <section class="metric-grid">
        <div class="metric"><span>账号状态</span><strong><span class="badge badge-{{{{ user.status }}}}">{{{{ user.status|account_status_label }}}}</span></strong><small>{{{{ user.created_at|admin_time }}}} 创建</small></div>
        <div class="metric"><span>授权状态</span><strong><span class="badge badge-{{{{ user.license.reason }}}}">{{{{ user.license.reason|license_reason_label }}}}</span></strong><small>{{{{ user.license_expires_at|admin_time }}}}</small></div>
        <div class="metric"><span>设备绑定</span><strong>{{{{ '已绑定' if user.device.bound else '未绑定' }}}}</strong><small>{{{{ user.device.name or user.device.fingerprint or '-' }}}}</small></div>
        <div class="metric"><span>最近登录</span><strong>{{{{ user.last_login_at|admin_time }}}}</strong><small>Session：{{{{ user.sessions|length }}}}</small></div>
      </section>

      <section class="split-grid">
        <div class="card">
          <div class="card-head">
            <div>
              <h2>账号与设备</h2>
              <p>设备变更需要先解除绑定，默认扣除 3 天授权时长。</p>
            </div>
            {{% if user.device.bound %}}<span class="badge badge-active">已绑定</span>{{% else %}}<span class="badge badge-not_activated">未绑定</span>{{% endif %}}
          </div>
          <dl class="kv">
            <dt>账号 ID</dt><dd class="mono">{{{{ user.id }}}}</dd>
            <dt>设备名称</dt><dd>{{{{ user.device.name or '-' }}}}</dd>
            <dt>设备指纹</dt><dd class="mono">{{{{ user.device.fingerprint or '-' }}}}</dd>
            <dt>系统 / 架构</dt><dd>{{{{ user.device.os or '-' }}}} / {{{{ user.device.arch or '-' }}}}</dd>
            <dt>App 版本</dt><dd>{{{{ user.device.app_version or '-' }}}}</dd>
            <dt>绑定时间</dt><dd>{{{{ user.device.bound_at|admin_time }}}}</dd>
            <dt>备注</dt><dd>{{{{ user.notes or '-' }}}}</dd>
            <dt>标签</dt><dd>{{{{ user.tags or '-' }}}}</dd>
          </dl>
          {{% if user.device.details %}}
            <div class="section">
              <h3>设备详情</h3>
              <pre class="section">{{{{ user.device.details|tojson(indent=2) }}}}</pre>
            </div>
          {{% endif %}}
        </div>

        {{% if can('users:write') %}}
        <div class="card">
          <div class="card-head">
            <div>
              <h2>运营操作</h2>
              <p>所有操作都会写入审计日志。禁用、解绑和吊销 session 需要确认。</p>
            </div>
          </div>
          <div class="action-grid">
            <div class="action-card">
              <h3>账号状态</h3>
              <p>禁用账号会同步吊销有效 session。</p>
              <form method="post" action="{{{{ url_for('admin_ui_set_status', email=user.email) }}}}">
                <select name="status">
                  <option value="active" {{{{ 'selected' if user.status == 'active' else '' }}}}>启用</option>
                  <option value="disabled" {{{{ 'selected' if user.status == 'disabled' else '' }}}}>禁用</option>
                </select>
                <input name="reason" placeholder="原因">
                <input name="confirm_action" type="hidden" value="CONFIRM">
                <button type="submit">更新状态</button>
              </form>
            </div>
            <div class="action-card">
              <h3>授权期限</h3>
              <p>正数增加时长，负数扣减时长。</p>
              <form method="post" action="{{{{ url_for('admin_ui_adjust_license', email=user.email) }}}}" data-confirm="确认调整授权期限？">
                <input name="add_days" type="number" placeholder="例如 30 或 -3" required>
                <input name="reason" placeholder="原因">
                <input name="confirm_action" type="hidden" value="CONFIRM">
                <button type="submit">调整期限</button>
              </form>
            </div>
            <div class="action-card danger-zone">
              <h3>设备绑定</h3>
              <p class="danger-text">解除绑定默认扣除 3 天，用户下一次可绑定新设备。</p>
              <form method="post" action="{{{{ url_for('admin_ui_unbind_device', email=user.email) }}}}" data-confirm="确认解除设备绑定并按填写天数扣除？">
                <input name="deduct_days" type="number" value="3" min="0">
                <input name="reason" placeholder="解绑原因">
                <input name="confirm_action" type="hidden" value="CONFIRM">
                <button class="danger" type="submit">解除绑定</button>
              </form>
            </div>
            <div class="action-card danger-zone">
              <h3>Session</h3>
              <p>吊销后客户端会在下一次授权检查时退出可用状态。</p>
              <form method="post" action="{{{{ url_for('admin_ui_revoke_sessions', email=user.email) }}}}" data-confirm="确认吊销该用户全部 session？">
                <input name="confirm_action" type="hidden" value="CONFIRM">
                <button class="danger" type="submit">吊销全部 session</button>
              </form>
            </div>
          </div>
        </div>
        {{% endif %}}
      </section>

      <section class="table-card">
        <div class="table-toolbar"><h2>CDK 兑换记录</h2></div>
        <div class="table-scroll short">
          <table><thead><tr><th>CDK</th><th>天数</th><th>状态</th><th>兑换时间</th></tr></thead><tbody>
          {{% for cdk in user.redeemed_cdks %}}<tr><td class="mono">{{{{ cdk.code }}}}</td><td>{{{{ cdk.duration_days }}}}</td><td><span class="badge badge-{{{{ cdk.status }}}}">{{{{ cdk.status|cdk_status_label }}}}</span></td><td>{{{{ cdk.redeemed_at|admin_time }}}}</td></tr>{{% else %}}<tr><td colspan="4"><div class="empty">无兑换记录</div></td></tr>{{% endfor %}}
          </tbody></table>
        </div>
      </section>

      <section class="table-card">
        <div class="table-toolbar"><h2>Session</h2></div>
        <div class="table-scroll short">
          <table><thead><tr><th>Token</th><th>设备</th><th>创建</th><th>最近</th><th>状态</th><th>操作</th></tr></thead><tbody>
          {{% for session in user.sessions %}}
            <tr>
              <td class="mono">{{{{ session.token_prefix }}}}</td>
              <td class="mono">{{{{ session.device_fingerprint }}}}</td>
              <td>{{{{ session.created_at|admin_time }}}}</td>
              <td>{{{{ session.last_seen_at|admin_time }}}}</td>
              <td>{{% if session.revoked_at %}}<span class="badge badge-disabled">已吊销</span><br><span class="muted small">{{{{ session.revoked_at|admin_time }}}}</span>{{% else %}}<span class="badge badge-active">有效</span>{{% endif %}}</td>
              <td>
                {{% if not session.revoked_at and can('users:write') %}}
                  <form method="post" action="{{{{ url_for('admin_ui_revoke_session', email=user.email, token_prefix=session.token_prefix) }}}}" data-confirm="确认吊销这个 session？">
                    <input name="confirm_action" type="hidden" value="CONFIRM">
                    <button class="danger" type="submit">吊销</button>
                  </form>
                {{% else %}}<span class="muted">-</span>{{% endif %}}
              </td>
            </tr>
          {{% else %}}<tr><td colspan="6"><div class="empty">无 session</div></td></tr>{{% endfor %}}
          </tbody></table>
        </div>
      </section>

      <section class="split-grid">
        <div class="table-card">
          <div class="table-toolbar"><h2>授权事件</h2></div>
          <div class="table-scroll short event-detail">
            <table><thead><tr><th>类型</th><th>详情</th><th>时间</th></tr></thead><tbody>
            {{% for event in user.license_events %}}<tr><td><span class="badge">{{{{ event.event_type }}}}</span></td><td><pre>{{{{ event.detail|tojson(indent=2) }}}}</pre></td><td>{{{{ event.created_at|admin_time }}}}</td></tr>{{% else %}}<tr><td colspan="3"><div class="empty">无授权事件</div></td></tr>{{% endfor %}}
            </tbody></table>
          </div>
        </div>
        <div class="table-card">
          <div class="table-toolbar"><h2>设备事件</h2></div>
          <div class="table-scroll short event-detail">
            <table><thead><tr><th>设备</th><th>类型</th><th>详情</th><th>时间</th></tr></thead><tbody>
            {{% for event in user.device_events %}}<tr><td class="mono">{{{{ event.device_fingerprint or '-' }}}}</td><td><span class="badge badge-device">{{{{ event.event_type }}}}</span></td><td><pre>{{{{ event.detail|tojson(indent=2) }}}}</pre></td><td>{{{{ event.created_at|admin_time }}}}</td></tr>{{% else %}}<tr><td colspan="4"><div class="empty">无设备事件</div></td></tr>{{% endfor %}}
            </tbody></table>
          </div>
        </div>
      </section>

      <section class="table-card">
        <div class="table-toolbar"><h2>管理员操作</h2></div>
        <div class="table-scroll short event-detail">
          <table><thead><tr><th>管理员</th><th>类型</th><th>详情</th><th>时间</th></tr></thead><tbody>
          {{% for event in user.admin_events %}}<tr><td>{{{{ event.actor }}}}</td><td><span class="badge badge-admin">{{{{ event.event_type }}}}</span></td><td><pre>{{{{ event.detail|tojson(indent=2) }}}}</pre></td><td>{{{{ event.created_at|admin_time }}}}</td></tr>{{% else %}}<tr><td colspan="4"><div class="empty">无管理员操作</div></td></tr>{{% endfor %}}
          </tbody></table>
        </div>
      </section>
    </div>
  </section>
</main>{ADMIN_INTERACTION_JS}
"""


ADMIN_EVENTS_TEMPLATE = f"""
<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>InkMoment Admin Events</title>{ADMIN_BASE_CSS}
<main class="app-shell">
  <aside class="sidebar">
    <div class="brand-block">
      <div class="brand-title">InkMoment</div>
      <div class="brand-subtitle">审计中心</div>
    </div>
    <nav class="nav-list" aria-label="管理导航">
      <a class="nav-link" href="{{{{ url_for('admin_dashboard') }}}}"><span class="nav-dot"></span>总览</a>
      <a class="nav-link active" href="{{{{ url_for('admin_events_page') }}}}"><span class="nav-dot"></span>审计日志</a>
    </nav>
    <div class="sidebar-footer">
      <form method="post" action="{{{{ url_for('admin_logout') }}}}"><button type="submit">退出登录</button></form>
    </div>
  </aside>

  <section class="content">
    <header class="page-head">
      <div class="title-block">
        <a href="{{{{ url_for('admin_dashboard') }}}}">← 返回总览</a>
        <h1>审计日志</h1>
        <p>追踪授权、设备绑定和管理员操作。用于定位登录、换机、CDK 兑换问题。</p>
      </div>
      {{% if filters.source or filters.email or filters.event_type or filters.q %}}
        <a class="btn secondary" href="{{{{ url_for('admin_events_page') }}}}">清空筛选</a>
      {{% endif %}}
    </header>

    <div class="stack">
      <section class="card">
        <div class="card-head">
          <div>
            <h2>筛选</h2>
            <p>按来源、账号、事件类型和详情关键字过滤。</p>
          </div>
        </div>
        <form method="get" action="{{{{ url_for('admin_events_page') }}}}" class="form-grid five">
          <label>来源
            <select name="source">
              <option value="" {{{{ 'selected' if filters.source == '' else '' }}}}>全部来源</option>
              <option value="license" {{{{ 'selected' if filters.source == 'license' else '' }}}}>授权</option>
              <option value="device" {{{{ 'selected' if filters.source == 'device' else '' }}}}>设备</option>
              <option value="admin" {{{{ 'selected' if filters.source == 'admin' else '' }}}}>管理员</option>
            </select>
          </label>
          <label>账号邮箱<input name="email" value="{{{{ filters.email }}}}" placeholder="user@example.com"></label>
          <label>事件类型<input name="event_type" value="{{{{ filters.event_type }}}}" placeholder="redeem"></label>
          <label>关键字<input name="q" value="{{{{ filters.q }}}}" placeholder="详情 / 操作者"></label>
          <button type="submit">筛选</button>
        </form>
      </section>

      <section class="table-card">
        <div class="table-toolbar">
          <div>
            <h2>事件列表</h2>
            <p class="muted small">最多显示 200 条</p>
          </div>
        </div>
        <div class="table-scroll event-detail">
          <table>
            <thead><tr><th>来源</th><th>账号</th><th>操作者</th><th>设备</th><th>事件</th><th>详情</th><th>时间</th></tr></thead>
            <tbody>
            {{% for event in events %}}
              <tr>
                <td><span class="badge badge-{{{{ event.source }}}}">{{{{ event.source|event_source_label }}}}</span></td>
                <td>{{% if event.email %}}<a href="{{{{ url_for('admin_user_page', email=event.email) }}}}">{{{{ event.email }}}}</a>{{% else %}}<span class="muted">-</span>{{% endif %}}</td>
                <td>{{{{ event.actor or '-' }}}}</td>
                <td class="mono">{{{{ event.device_fingerprint or '-' }}}}</td>
                <td><span class="badge">{{{{ event.event_type }}}}</span></td>
                <td><pre>{{{{ event.detail|tojson(indent=2) }}}}</pre></td>
                <td>{{{{ event.created_at|admin_time }}}}</td>
              </tr>
            {{% else %}}
              <tr><td colspan="7"><div class="empty">暂无审计事件</div></td></tr>
            {{% endfor %}}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </section>
</main>{ADMIN_INTERACTION_JS}
"""


ADMIN_MESSAGE_TEMPLATE = f"""
<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>InkMoment Admin</title>{ADMIN_BASE_CSS}
<main>
  <section class="card" style="max-width: 560px; margin: 12vh auto 0;">
    <div class="title-block">
      <h1>操作未完成</h1>
      <p class="danger-text">{{{{ message }}}}</p>
    </div>
    <div class="section">
      <a class="btn secondary" href="{{{{ url_for('admin_dashboard') }}}}">返回后台</a>
    </div>
  </section>
</main>{ADMIN_INTERACTION_JS}
"""


def _bearer_token() -> str:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


def _plan_payload(account: dict | None, license_state: dict) -> dict:
    return {
        "name": "CDK 授权" if license_state.get("source") == "cdk" else "未开通",
        "source": license_state.get("source"),
        "expires_at": license_state.get("expires_at"),
        "status": license_state.get("reason"),
    }


def _account_response(
    auth_store: AuthStore,
    account: dict | None,
    token: str | None = None,
    session_token: str | None = None,
) -> dict:
    license_state = license_payload(account)
    payload = {
        "account": account,
        "license": license_state,
        "device": (account or {}).get("device") or {},
        "limits": (account or {}).get("limits") or {},
        "plan": _plan_payload(account, license_state),
        "latest_session": auth_store.session_for_token(session_token or token or ""),
    }
    if token:
        payload["token"] = token
    return payload


def _device_from_request(data: dict | None = None) -> dict:
    payload = data or {}
    device = dict(payload.get("device") or {})
    header_fingerprint = request.headers.get("X-Device-Fingerprint", "").strip()
    if header_fingerprint and not device.get("fingerprint"):
        device["fingerprint"] = header_fingerprint
    return device


def _admin_session_token_from_request() -> str:
    return (_bearer_token() or request.cookies.get(ADMIN_COOKIE_NAME, "")).strip()


def _admin_bootstrap_token_from_request() -> str:
    return (
        request.headers.get("X-Admin-Token", "")
        or request.form.get("admin_token", "")
    ).strip()


def _admin_token_valid(token: str) -> bool:
    configured = os.environ.get(ADMIN_TOKEN_ENV, "")
    return bool(configured and token and secrets.compare_digest(configured, token))


def _admin_cookie_secure() -> bool:
    return bool(request.is_secure)


def _confirmed(data) -> bool:
    value = data.get("confirm_action")
    if value is None:
        value = data.get("confirm")
    if isinstance(value, bool):
        return value
    return str(value or "").strip().upper() in {CONFIRM_ACTION_VALUE, "TRUE", "YES", "1"}


def _confirmation_required_response():
    return jsonify({
        "error": "高风险管理操作需要二次确认",
        "code": "confirmation_required",
        "confirm_action": CONFIRM_ACTION_VALUE,
    }), 409


def _permission_denied_response(permission: str):
    return jsonify({
        "error": "管理员权限不足",
        "code": "admin_permission_denied",
        "required_permission": permission,
    }), 403


def _user_permission_error_code(error: PermissionError) -> str:
    message = str(error)
    if "锁定" in message:
        return "login_locked"
    if "禁用" in message:
        return "disabled"
    if "绑定" in message or "设备" in message:
        return "device_mismatch"
    return "forbidden"


def create_app(store: AuthStore | None = None) -> Flask:
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    auth_store = store or AuthStore()
    auth_store.initialize()
    app.jinja_env.filters["admin_time"] = _admin_time
    app.jinja_env.filters["account_status_label"] = _account_status_label
    app.jinja_env.filters["license_reason_label"] = _license_reason_label
    app.jinja_env.filters["cdk_status_label"] = _cdk_status_label
    app.jinja_env.filters["event_source_label"] = _event_source_label

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", HSTS_VALUE)
        return response

    def require_user(handler: Callable):
        @wraps(handler)
        def wrapped(*args, **kwargs):
            account = auth_store.account_for_token(
                _bearer_token(),
                device_fingerprint=request.headers.get("X-Device-Fingerprint", "").strip(),
            )
            if account is None:
                return jsonify({"error": "登录已失效", "code": "unauthenticated"}), 401
            return handler(account, *args, **kwargs)

        return wrapped

    def require_admin(permission_or_handler=None):
        permission = "" if callable(permission_or_handler) else str(permission_or_handler or "")

        def decorator(handler: Callable):
            @wraps(handler)
            def wrapped(*args, **kwargs):
                identity = _admin_identity_from_request()
                if identity is None:
                    return jsonify({"error": "admin token invalid", "code": "forbidden"}), 403
                g.admin_identity = identity
                if permission and not _admin_identity_has_permission(identity, permission):
                    return _permission_denied_response(permission)
                return handler(*args, **kwargs)

            return wrapped

        if callable(permission_or_handler):
            return decorator(permission_or_handler)
        return decorator

    def require_admin_page(permission_or_handler=None):
        permission = "" if callable(permission_or_handler) else str(permission_or_handler or "")

        def decorator(handler: Callable):
            @wraps(handler)
            def wrapped(*args, **kwargs):
                identity = _admin_identity_from_request()
                if identity is None:
                    return redirect(url_for("admin_login"))
                g.admin_identity = identity
                if permission and not _admin_identity_has_permission(identity, permission):
                    return render_template_string(
                        ADMIN_MESSAGE_TEMPLATE,
                        message="管理员权限不足",
                    ), 403
                return handler(*args, **kwargs)

            return wrapped

        if callable(permission_or_handler):
            return decorator(permission_or_handler)
        return decorator

    def _admin_identity_from_request() -> dict | None:
        admin = auth_store.admin_for_token(_admin_session_token_from_request())
        if admin is not None:
            return {
                "kind": "admin_session",
                "username": admin["username"],
                "role": admin["role"],
                "permissions": admin.get("permissions", []),
                "admin": admin,
            }
        if auth_store.admin_count() == 0 and _admin_token_valid(_admin_bootstrap_token_from_request()):
            return {
                "kind": "bootstrap_token",
                "username": "bootstrap-token",
                "role": "owner",
                "permissions": ["*"],
                "admin": None,
            }
        return None

    def _admin_actor() -> str:
        identity = getattr(g, "admin_identity", None) or {}
        return str(identity.get("username") or identity.get("kind") or "admin")

    def _admin_identity_has_permission(identity: dict, permission: str) -> bool:
        permissions = set(identity.get("permissions") or [])
        return "*" in permissions or permission in permissions

    def _can_admin(permission: str) -> bool:
        identity = getattr(g, "admin_identity", None) or {}
        return _admin_identity_has_permission(identity, permission)

    def _admin_error_page(message: str, status_code: int = 400):
        return render_template_string(ADMIN_MESSAGE_TEMPLATE, message=message), status_code

    @app.route("/health")
    def health():
        return jsonify({"ok": True, "server_time": time.time()})

    @app.route("/auth/register", methods=["POST"])
    def register():
        data = request.get_json(silent=True) or {}
        try:
            auth_store.create_account(
                data.get("email") or "",
                data.get("password") or "",
                display_name=data.get("display_name") or "",
            )
            token, account = auth_store.authenticate(
                data.get("email") or "",
                data.get("password") or "",
                _device_from_request(data),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        except PermissionError as exc:
            return jsonify({"error": str(exc), "code": _user_permission_error_code(exc)}), 403
        return jsonify(_account_response(auth_store, account, token)), 201

    @app.route("/auth/login", methods=["POST"])
    def login():
        data = request.get_json(silent=True) or {}
        try:
            token, account = auth_store.authenticate(
                data.get("email") or "",
                data.get("password") or "",
                _device_from_request(data),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_credentials"}), 401
        except PermissionError as exc:
            return jsonify({"error": str(exc), "code": _user_permission_error_code(exc)}), 403
        return jsonify(_account_response(auth_store, account, token))

    @app.route("/auth/logout", methods=["POST"])
    def logout():
        auth_store.revoke_token(_bearer_token())
        return jsonify({"ok": True})

    @app.route("/auth/status")
    @require_user
    def status(account):
        return jsonify(_account_response(auth_store, account, session_token=_bearer_token()))

    @app.route("/auth/redeem", methods=["POST"])
    @require_user
    def redeem(account):
        data = request.get_json(silent=True) or {}
        try:
            payload = auth_store.redeem_cdk(
                _bearer_token(),
                data.get("code") or "",
                device_fingerprint=request.headers.get("X-Device-Fingerprint", "").strip(),
            )
        except PermissionError as exc:
            return jsonify({"error": str(exc), "code": "unauthenticated"}), 401
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_cdk"}), 400
        response_payload = _account_response(
            auth_store,
            payload.get("account"),
            session_token=_bearer_token(),
        )
        response_payload["duration_days"] = payload.get("duration_days")
        return jsonify(response_payload)

    @app.route("/auth/device/unbind", methods=["POST"])
    @require_user
    def unbind_device(account):
        data = request.get_json(silent=True) or {}
        try:
            payload = auth_store.unbind_device(
                _bearer_token(),
                bool(data.get("confirm_penalty")),
                data.get("reason") or "",
                device_fingerprint=request.headers.get("X-Device-Fingerprint", "").strip(),
            )
        except PermissionError as exc:
            return jsonify({"error": str(exc), "code": "unauthenticated"}), 401
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        response_payload = _account_response(
            auth_store,
            payload.get("account"),
            session_token=_bearer_token(),
        )
        response_payload["ok"] = payload.get("ok", True)
        response_payload["penalty_days"] = payload.get("penalty_days")
        return jsonify(response_payload)

    @app.route("/admin/cdks", methods=["GET", "POST"])
    @require_admin
    def admin_cdks():
        if request.method == "GET":
            if not _can_admin(ADMIN_PERMISSION_CDKS_READ):
                return _permission_denied_response(ADMIN_PERMISSION_CDKS_READ)
            return jsonify({
                "cdks": auth_store.admin_list_cdks(
                    request.args.get("q", ""),
                    request.args.get("status", ""),
                    limit=_bounded_limit(request.args.get("limit"), 200),
                )
            })
        if not _can_admin(ADMIN_PERMISSION_CDKS_WRITE):
            return _permission_denied_response(ADMIN_PERMISSION_CDKS_WRITE)
        data = request.get_json(silent=True) or {}
        try:
            count = int(data.get("count") or 1)
            if count > 1:
                if not _confirmed(data):
                    return _confirmation_required_response()
                payload = auth_store.admin_create_cdks(
                    int(data.get("duration_days") or 0),
                    count,
                    prefix=data.get("prefix") or "INKMOMENT",
                    actor=_admin_actor(),
                )
            else:
                payload = auth_store.create_cdk(
                    data.get("code") or secrets.token_urlsafe(12).upper(),
                    int(data.get("duration_days") or 0),
                    actor=_admin_actor(),
                )
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify(payload), 201

    @app.route("/admin/cdks/<path:code>/disable", methods=["POST"])
    @require_admin(ADMIN_PERMISSION_CDKS_WRITE)
    def admin_disable_cdk(code):
        data = request.get_json(silent=True) or {}
        if not _confirmed(data):
            return _confirmation_required_response()
        try:
            payload = auth_store.admin_disable_cdk(
                code,
                reason=data.get("reason") or "",
                actor=_admin_actor(),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify(payload)

    @app.route("/admin/cdks/export")
    @require_admin(ADMIN_PERMISSION_CDKS_READ)
    def admin_export_cdks():
        cdks = auth_store.admin_list_cdks(
            request.args.get("q", ""),
            request.args.get("status", ""),
            limit=_bounded_limit(request.args.get("limit"), 1000, ADMIN_EXPORT_LIMIT_MAX),
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

    @app.route("/admin/users")
    @require_admin(ADMIN_PERMISSION_USERS_READ)
    def admin_users():
        query = request.args.get("q", "")
        return jsonify({"users": auth_store.admin_list_users(
            query,
            limit=_bounded_limit(request.args.get("limit"), 200),
        )})

    @app.route("/admin/admins", methods=["GET", "POST"])
    @require_admin
    def admin_admins():
        if request.method == "GET":
            if not _can_admin(ADMIN_PERMISSION_ADMINS_READ):
                return _permission_denied_response(ADMIN_PERMISSION_ADMINS_READ)
            return jsonify({"admins": auth_store.admin_list_admins(
                limit=_bounded_limit(request.args.get("limit"), 200),
            )})
        if not _can_admin(ADMIN_PERMISSION_ADMINS_WRITE):
            return _permission_denied_response(ADMIN_PERMISSION_ADMINS_WRITE)
        data = request.get_json(silent=True) or {}
        role = (data.get("role") or ADMIN_ROLE_AGENT).strip().lower()
        if role not in {ADMIN_ROLE_AGENT, ADMIN_ROLE_OPERATOR, ADMIN_ROLE_AUDITOR}:
            return jsonify({"error": "只能创建 agent、operator 或 auditor 子账号", "code": "invalid_request"}), 400
        try:
            admin = auth_store.create_admin(
                data.get("username") or "",
                data.get("password") or "",
                display_name=data.get("display_name") or "",
                role=role,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify({"admin": admin}), 201

    @app.route("/admin/events")
    @require_admin(ADMIN_PERMISSION_USERS_READ)
    def admin_events():
        return jsonify({
            "events": auth_store.admin_list_events(
                source=request.args.get("source", ""),
                email=request.args.get("email", ""),
                event_type=request.args.get("event_type", ""),
                query=request.args.get("q", ""),
                limit=_bounded_limit(request.args.get("limit"), 100),
            )
        })

    @app.route("/admin/users/<path:email>")
    @require_admin(ADMIN_PERMISSION_USERS_READ)
    def admin_user_detail(email):
        payload = auth_store.admin_get_user(email)
        if payload is None:
            return jsonify({"error": "账号不存在", "code": "not_found"}), 404
        return jsonify(payload)

    @app.route("/admin/users/<path:email>/status", methods=["POST"])
    @require_admin(ADMIN_PERMISSION_USERS_WRITE)
    def admin_set_status(email):
        data = request.get_json(silent=True) or {}
        next_status = (data.get("status") or "").strip().lower()
        if next_status == "disabled" and not _confirmed(data):
            return _confirmation_required_response()
        try:
            payload = auth_store.admin_set_user_status(
                email,
                next_status,
                data.get("reason") or "",
                operator=_admin_actor(),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify(payload)

    @app.route("/admin/users/<path:email>/license", methods=["POST"])
    @require_admin(ADMIN_PERMISSION_USERS_WRITE)
    def admin_adjust_license(email):
        data = request.get_json(silent=True) or {}
        try:
            add_days = int(data.get("add_days") or 0)
            if add_days < 0 and not _confirmed(data):
                return _confirmation_required_response()
            payload = auth_store.admin_adjust_license(
                email,
                add_days=add_days,
                reason=data.get("reason") or "",
                operator=_admin_actor(),
            )
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify(payload)

    @app.route("/admin/users/<path:email>/device/unbind", methods=["POST"])
    @require_admin(ADMIN_PERMISSION_USERS_WRITE)
    def admin_unbind_device(email):
        data = request.get_json(silent=True) or {}
        if not _confirmed(data):
            return _confirmation_required_response()
        try:
            payload = auth_store.admin_unbind_device(
                email,
                deduct_days=int(data.get("deduct_days", 3)),
                reason=data.get("reason") or "",
                operator=_admin_actor(),
            )
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify(payload)

    @app.route("/admin/users/<path:email>/sessions/revoke", methods=["POST"])
    @require_admin(ADMIN_PERMISSION_USERS_WRITE)
    def admin_revoke_sessions(email):
        data = request.get_json(silent=True) or {}
        if not _confirmed(data):
            return _confirmation_required_response()
        count = auth_store.admin_revoke_sessions(email, operator=_admin_actor())
        return jsonify({"ok": True, "revoked": count})

    @app.route("/admin/users/<path:email>/sessions/<token_prefix>/revoke", methods=["POST"])
    @require_admin(ADMIN_PERMISSION_USERS_WRITE)
    def admin_revoke_session(email, token_prefix):
        data = request.get_json(silent=True) or {}
        if not _confirmed(data):
            return _confirmation_required_response()
        try:
            payload = auth_store.admin_revoke_session(
                email,
                token_prefix,
                operator=_admin_actor(),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        return jsonify(payload)

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        error = ""
        if request.method == "POST":
            data = request.get_json(silent=True) if request.is_json else request.form
            try:
                token, _admin = auth_store.authenticate_admin(
                    str(data.get("username", "") if data else ""),
                    str(data.get("password", "") if data else ""),
                )
                if request.is_json:
                    return jsonify({"token": token, "admin": _admin})
                response = make_response(redirect(url_for("admin_dashboard")))
                response.set_cookie(
                    ADMIN_COOKIE_NAME,
                    token,
                    httponly=True,
                    secure=_admin_cookie_secure(),
                    samesite="Lax",
                )
                return response
            except ValueError as exc:
                if request.is_json:
                    return jsonify({"error": str(exc), "code": "invalid_credentials"}), 401
                error = str(exc)
            except PermissionError as exc:
                if request.is_json:
                    code = "admin_locked" if "锁定" in str(exc) else "forbidden"
                    return jsonify({"error": str(exc), "code": code}), 403
                error = str(exc)
        return render_template_string(
            ADMIN_LOGIN_TEMPLATE,
            error=error,
            allow_bootstrap=auth_store.admin_count() == 0,
        )

    @app.route("/admin/bootstrap", methods=["POST"])
    def admin_bootstrap():
        data = request.get_json(silent=True) or request.form
        if auth_store.admin_count() > 0:
            return jsonify({"error": "管理员账号已初始化", "code": "admin_exists"}), 409
        if not _admin_token_valid(str(data.get("admin_token") or "")):
            return jsonify({"error": "bootstrap token invalid", "code": "forbidden"}), 403
        try:
            admin = auth_store.create_admin(
                str(data.get("username") or ""),
                str(data.get("password") or ""),
                display_name=str(data.get("display_name") or ""),
            )
            token, admin = auth_store.authenticate_admin(
                admin["username"],
                str(data.get("password") or ""),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        if request.is_json:
            return jsonify({"token": token, "admin": admin}), 201
        response = make_response(redirect(url_for("admin_dashboard")))
        response.set_cookie(
            ADMIN_COOKIE_NAME,
            token,
            httponly=True,
            secure=_admin_cookie_secure(),
            samesite="Lax",
        )
        return response

    @app.route("/admin/logout", methods=["POST"])
    def admin_logout():
        auth_store.revoke_admin_token(_admin_session_token_from_request())
        response = make_response(redirect(url_for("admin_login")))
        response.delete_cookie(
            ADMIN_COOKIE_NAME,
            secure=_admin_cookie_secure(),
            samesite="Lax",
        )
        return response

    @app.route("/admin")
    @require_admin_page(ADMIN_PERMISSION_USERS_READ)
    def admin_dashboard():
        query = request.args.get("q", "")
        cdk_query = request.args.get("cdk_q", "")
        cdk_status = request.args.get("cdk_status", "")
        cdk_total = auth_store.admin_count_cdks(cdk_query, cdk_status)
        user_total = auth_store.admin_count_users(query)
        cdk_page = _pagination_meta("cdk_page", "cdk_page_size", cdk_total)
        user_page = _pagination_meta("user_page", "user_page_size", user_total)
        users = auth_store.admin_list_users(
            query,
            limit=user_page["page_size"],
            offset=user_page["offset"],
        )
        cdks = auth_store.admin_list_cdks(
            cdk_query,
            cdk_status,
            limit=cdk_page["page_size"],
            offset=cdk_page["offset"],
        )
        active_cdk_total = auth_store.admin_count_cdks(cdk_query, "active")
        admins = auth_store.admin_list_admins(limit=100) if _can_admin(ADMIN_PERMISSION_ADMINS_READ) else []
        return render_template_string(
            ADMIN_DASHBOARD_TEMPLATE,
            users=users,
            cdks=cdks,
            admins=admins,
            cdk_page=cdk_page,
            user_page=user_page,
            active_cdk_total=active_cdk_total,
            query=query,
            cdk_query=cdk_query,
            cdk_status=cdk_status,
            can=_can_admin,
        )

    @app.route("/admin/ui/events")
    @require_admin_page(ADMIN_PERMISSION_USERS_READ)
    def admin_events_page():
        filters = {
            "source": request.args.get("source", "").strip().lower(),
            "email": request.args.get("email", "").strip(),
            "event_type": request.args.get("event_type", "").strip(),
            "q": request.args.get("q", "").strip(),
        }
        events = auth_store.admin_list_events(
            source=filters["source"],
            email=filters["email"],
            event_type=filters["event_type"],
            query=filters["q"],
            limit=200,
        )
        return render_template_string(
            ADMIN_EVENTS_TEMPLATE,
            events=events,
            filters=filters,
        )

    @app.route("/admin/ui/cdks", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_CDKS_WRITE)
    def admin_ui_create_cdk():
        try:
            code = request.form.get("code") or secrets.token_urlsafe(12).upper()
            duration_days = int(request.form.get("duration_days") or 0)
            count = int(request.form.get("count") or 1)
            if count > 1:
                if not _confirmed(request.form):
                    return _admin_error_page("批量生成 CDK 需要二次确认", 409)
                auth_store.admin_create_cdks(
                    duration_days,
                    count,
                    prefix=request.form.get("prefix") or "INKMOMENT",
                    actor=_admin_actor(),
                )
            else:
                auth_store.create_cdk(code, duration_days, actor=_admin_actor())
        except (TypeError, ValueError) as exc:
            return _admin_error_page(str(exc), 400)
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/ui/admins", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_ADMINS_WRITE)
    def admin_ui_create_admin():
        role = (request.form.get("role") or ADMIN_ROLE_AGENT).strip().lower()
        if role not in {ADMIN_ROLE_AGENT, ADMIN_ROLE_OPERATOR, ADMIN_ROLE_AUDITOR}:
            return _admin_error_page("只能创建 agent、operator 或 auditor 子账号", 400)
        try:
            auth_store.create_admin(
                request.form.get("username") or "",
                request.form.get("password") or "",
                display_name=request.form.get("display_name") or "",
                role=role,
            )
        except ValueError as exc:
            return _admin_error_page(str(exc), 400)
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/ui/cdks/<path:code>/disable", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_CDKS_WRITE)
    def admin_ui_disable_cdk(code):
        if not _confirmed(request.form):
            return _admin_error_page("禁用 CDK 需要二次确认", 409)
        try:
            auth_store.admin_disable_cdk(
                code,
                reason=request.form.get("reason") or "",
                actor=_admin_actor(),
            )
        except ValueError as exc:
            return _admin_error_page(str(exc), 400)
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/ui/users/<path:email>")
    @require_admin_page(ADMIN_PERMISSION_USERS_READ)
    def admin_user_page(email):
        user = auth_store.admin_get_user(email)
        if user is None:
            return render_template_string(ADMIN_MESSAGE_TEMPLATE, message="账号不存在"), 404
        return render_template_string(ADMIN_USER_TEMPLATE, user=user, can=_can_admin)

    @app.route("/admin/ui/users/<path:email>/status", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_USERS_WRITE)
    def admin_ui_set_status(email):
        next_status = request.form.get("status") or ""
        if next_status.strip().lower() == "disabled" and not _confirmed(request.form):
            return _admin_error_page("禁用账号需要二次确认", 409)
        try:
            auth_store.admin_set_user_status(
                email,
                next_status,
                request.form.get("reason") or "",
                operator=_admin_actor(),
            )
        except ValueError as exc:
            return _admin_error_page(str(exc), 400)
        return redirect(url_for("admin_user_page", email=email))

    @app.route("/admin/ui/users/<path:email>/license", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_USERS_WRITE)
    def admin_ui_adjust_license(email):
        try:
            add_days = int(request.form.get("add_days") or 0)
            if add_days < 0 and not _confirmed(request.form):
                return _admin_error_page("扣减授权期限需要二次确认", 409)
            auth_store.admin_adjust_license(
                email,
                add_days=add_days,
                reason=request.form.get("reason") or "",
                operator=_admin_actor(),
            )
        except (TypeError, ValueError) as exc:
            return _admin_error_page(str(exc), 400)
        return redirect(url_for("admin_user_page", email=email))

    @app.route("/admin/ui/users/<path:email>/device/unbind", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_USERS_WRITE)
    def admin_ui_unbind_device(email):
        if not _confirmed(request.form):
            return _admin_error_page("解除设备绑定需要二次确认", 409)
        try:
            auth_store.admin_unbind_device(
                email,
                deduct_days=int(request.form.get("deduct_days") or 3),
                reason=request.form.get("reason") or "",
                operator=_admin_actor(),
            )
        except (TypeError, ValueError) as exc:
            return _admin_error_page(str(exc), 400)
        return redirect(url_for("admin_user_page", email=email))

    @app.route("/admin/ui/users/<path:email>/sessions/revoke", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_USERS_WRITE)
    def admin_ui_revoke_sessions(email):
        if not _confirmed(request.form):
            return _admin_error_page("吊销 session 需要二次确认", 409)
        auth_store.admin_revoke_sessions(email, operator=_admin_actor())
        return redirect(url_for("admin_user_page", email=email))

    @app.route("/admin/ui/users/<path:email>/sessions/<token_prefix>/revoke", methods=["POST"])
    @require_admin_page(ADMIN_PERMISSION_USERS_WRITE)
    def admin_ui_revoke_session(email, token_prefix):
        if not _confirmed(request.form):
            return _admin_error_page("吊销 session 需要二次确认", 409)
        try:
            auth_store.admin_revoke_session(email, token_prefix, operator=_admin_actor())
        except ValueError as exc:
            return _admin_error_page(str(exc), 400)
        return redirect(url_for("admin_user_page", email=email))

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="InkMoment standalone authorization server")
    parser.add_argument("--host", default=os.environ.get("INKMOMENT_AUTH_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("INKMOMENT_AUTH_PORT", "8061")))
    args = parser.parse_args()

    create_app().run(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
