from server.settings import Settings


def configured_auth_server_url() -> str:
    return Settings.load().auth_server_url.rstrip("/")


def is_auth_configured() -> bool:
    return bool(configured_auth_server_url())
