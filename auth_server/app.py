from __future__ import annotations

import argparse
import os
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from auth_server.config import ADMIN_TOKEN_ENV as ADMIN_TOKEN_ENV
from auth_server.labels import (
    account_status_label as _account_status_label,
    admin_time as _admin_time,
    cdk_status_label as _cdk_status_label,
    event_source_label as _event_source_label,
    license_reason_label as _license_reason_label,
)
from auth_server.blueprints.admin_api import AdminApiDeps, create_admin_api_blueprint
from auth_server.blueprints.admin_auth import AdminAuthController, create_admin_auth_blueprint
from auth_server.blueprints.admin_dashboard import AdminDashboardDeps, create_admin_dashboard_blueprint
from auth_server.blueprints.health import create_health_blueprint
from auth_server.blueprints.user_api import UserApiDeps, create_user_api_blueprint
from auth_server.security import add_security_headers
from auth_server.store import AuthStore


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

    app.after_request(add_security_headers)

    admin_auth = AdminAuthController(auth_store)
    app.register_blueprint(create_health_blueprint())
    app.register_blueprint(create_user_api_blueprint(UserApiDeps(auth_store)))
    app.register_blueprint(create_admin_auth_blueprint(admin_auth))
    app.register_blueprint(
        create_admin_api_blueprint(
            AdminApiDeps(
                store=auth_store,
                require_admin=admin_auth.require_admin,
                can_admin=admin_auth.can_admin,
                admin_actor=admin_auth.admin_actor,
            )
        )
    )
    app.register_blueprint(
        create_admin_dashboard_blueprint(
            AdminDashboardDeps(
                store=auth_store,
                require_admin_page=admin_auth.require_admin_page,
                can_admin=admin_auth.can_admin,
                admin_actor=admin_auth.admin_actor,
            )
        )
    )
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
