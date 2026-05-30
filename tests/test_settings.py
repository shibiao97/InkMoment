from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from server.settings import CONFIG_ENV_VARS, Settings, apply_runtime_environment


class SettingsTest(unittest.TestCase):
    def test_defaults_are_safe_for_local_desktop(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(env={}, config_file=Path(tmp) / "missing.toml")

        self.assertIsNone(settings.script_token)
        self.assertEqual(settings.dev_origins, frozenset())
        self.assertFalse(settings.legacy_ui)
        self.assertEqual(settings.auth_server_url, "")
        self.assertEqual(settings.app_version, "dev")
        self.assertEqual(settings.model_cache_dir, "")
        self.assertFalse(settings.no_mirror)
        self.assertEqual(settings.ark_timeout, 30.0)
        self.assertEqual(settings.ark_model_check_timeout, 15.0)
        self.assertEqual(settings.ark_model_check_workers, 8)
        self.assertIsNone(settings.ark_max_workers)

    def test_environment_values_are_normalized(self):
        env = {
            "INKMOMENT_TOKEN": " secret ",
            "INKMOMENT_DEV_ORIGINS": " http://localhost:5173/ , http://127.0.0.1:5173 ",
            "INKMOMENT_LEGACY_UI": "yes",
            "INKMOMENT_AUTH_SERVER_URL": " https://auth.example.com/ ",
            "INKMOMENT_DEVICE_ID": " device-a ",
            "INKMOMENT_APP_VERSION": " 1.2.3 ",
            "INKMOMENT_MODEL_CACHE_DIR": " ~/models ",
            "INKMOMENT_NO_MIRROR": "1",
            "HF_ENDPOINT": " https://huggingface.co ",
            "ARK_API_KEY": " ark-key ",
            "ARK_BASE_URL": " https://llm.example.com/v1 ",
            "ARK_TIMEOUT": "45",
            "ARK_MODEL_CHECK_TIMEOUT": "9",
            "ARK_MODEL_CHECK_WORKERS": "4",
            "ARK_MAX_WORKERS": "20",
            "ARK_PRO_MAX_WORKERS": "2",
            "ARK_INITIAL_CONCURRENCY": "6",
        }
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(env=env, config_file=Path(tmp) / "missing.toml")

        self.assertEqual(settings.script_token, "secret")
        self.assertEqual(
            settings.dev_origins,
            frozenset(
                {
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                }
            ),
        )
        self.assertTrue(settings.legacy_ui)
        self.assertEqual(settings.auth_server_url, "https://auth.example.com/")
        self.assertEqual(settings.device_id, "device-a")
        self.assertEqual(settings.app_version, "1.2.3")
        self.assertEqual(settings.model_cache_dir, "~/models")
        self.assertTrue(settings.no_mirror)
        self.assertEqual(settings.hf_endpoint, "https://huggingface.co")
        self.assertEqual(settings.ark_api_key, "ark-key")
        self.assertEqual(settings.ark_base_url, "https://llm.example.com/v1")
        self.assertEqual(settings.ark_timeout, 45.0)
        self.assertEqual(settings.ark_model_check_timeout, 9.0)
        self.assertEqual(settings.ark_model_check_workers, 4)
        self.assertEqual(settings.ark_max_workers, 20)
        self.assertEqual(settings.ark_pro_max_workers, 2)
        self.assertEqual(settings.ark_initial_concurrency, 6)

    def test_toml_is_used_when_environment_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "settings.toml"
            config.write_text(
                """
[app]
script_token = "file-token"
dev_origins = ["http://localhost:5173/"]
legacy_ui = true

[auth]
server_url = "https://auth.example.com"
device_id = "device-from-file"
app_version = "2.0.0"

[storage]
state_db = "/tmp/inkmoment.sqlite3"

[models]
cache_dir = "/tmp/models"
no_mirror = true
hf_endpoint = "https://hf.example.com"

[llm]
api_key = "file-key"
base_url = "https://llm.example.com"
timeout = 12
model_check_timeout = 7
model_check_workers = 3
max_workers = 18
pro_max_workers = 2
initial_concurrency = 5
""",
                encoding="utf-8",
            )

            settings = Settings.load(
                env={"INKMOMENT_TOKEN": "env-token", "ARK_MAX_WORKERS": "9"},
                config_file=config,
            )

        self.assertEqual(settings.script_token, "env-token")
        self.assertEqual(settings.dev_origins, frozenset({"http://localhost:5173"}))
        self.assertTrue(settings.legacy_ui)
        self.assertEqual(settings.auth_server_url, "https://auth.example.com")
        self.assertEqual(settings.device_id, "device-from-file")
        self.assertEqual(settings.app_version, "2.0.0")
        self.assertEqual(settings.state_db, "/tmp/inkmoment.sqlite3")
        self.assertEqual(settings.model_cache_dir, "/tmp/models")
        self.assertTrue(settings.no_mirror)
        self.assertEqual(settings.hf_endpoint, "https://hf.example.com")
        self.assertEqual(settings.ark_api_key, "file-key")
        self.assertEqual(settings.ark_base_url, "https://llm.example.com")
        self.assertEqual(settings.ark_timeout, 12.0)
        self.assertEqual(settings.ark_model_check_timeout, 7.0)
        self.assertEqual(settings.ark_model_check_workers, 3)
        self.assertEqual(settings.ark_max_workers, 9)
        self.assertEqual(settings.ark_pro_max_workers, 2)
        self.assertEqual(settings.ark_initial_concurrency, 5)

    def test_config_document_covers_all_settings_env_vars(self):
        docs = (Path(__file__).resolve().parents[1] / "docs" / "CONFIG.md").read_text(encoding="utf-8")

        missing = [name for name in CONFIG_ENV_VARS if f"`{name}`" not in docs]

        self.assertEqual(missing, [])

    def test_file_backed_settings_are_applied_to_runtime_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "settings.toml"
            config.write_text(
                """
[models]
cache_dir = "/tmp/models"
no_mirror = true
hf_endpoint = "https://hf.example.com"

[llm]
api_key = "file-key"
base_url = "https://llm.example.com"
timeout = 12
model_check_timeout = 7
model_check_workers = 3
max_workers = 18
pro_max_workers = 2
initial_concurrency = 5
""",
                encoding="utf-8",
            )
            settings = Settings.load(env={}, config_file=config)

        with patch.dict(os.environ, {}, clear=True):
            apply_runtime_environment(settings)

            self.assertEqual(os.environ["INKMOMENT_MODEL_CACHE_DIR"], "/tmp/models")
            self.assertEqual(os.environ["INKMOMENT_NO_MIRROR"], "1")
            self.assertEqual(os.environ["HF_ENDPOINT"], "https://hf.example.com")
            self.assertEqual(os.environ["ARK_API_KEY"], "file-key")
            self.assertEqual(os.environ["ARK_BASE_URL"], "https://llm.example.com")
            self.assertEqual(os.environ["ARK_TIMEOUT"], "12.0")
            self.assertEqual(os.environ["ARK_MODEL_CHECK_TIMEOUT"], "7.0")
            self.assertEqual(os.environ["ARK_MODEL_CHECK_WORKERS"], "3")
            self.assertEqual(os.environ["ARK_MAX_WORKERS"], "18")
            self.assertEqual(os.environ["ARK_PRO_MAX_WORKERS"], "2")
            self.assertEqual(os.environ["ARK_INITIAL_CONCURRENCY"], "5")

    def test_runtime_environment_keeps_explicit_env_over_file_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "settings.toml"
            config.write_text(
                """
[llm]
base_url = "https://file.example.com"
max_workers = 18
""",
                encoding="utf-8",
            )
            settings = Settings.load(
                env={"ARK_BASE_URL": "https://env.example.com", "ARK_MAX_WORKERS": "4"},
                config_file=config,
            )

        with patch.dict(os.environ, {"ARK_BASE_URL": "https://env.example.com", "ARK_MAX_WORKERS": "4"}, clear=True):
            apply_runtime_environment(settings)

            self.assertEqual(os.environ["ARK_BASE_URL"], "https://env.example.com")
            self.assertEqual(os.environ["ARK_MAX_WORKERS"], "4")


if __name__ == "__main__":
    unittest.main()
