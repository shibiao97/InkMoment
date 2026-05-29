import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendLlmModelsTest(unittest.TestCase):
    @unittest.skipIf(shutil.which("node") is None, "node is not installed")
    def test_normalize_models_never_uses_object_label_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = (ROOT / "frontend/src/composables/useLlmConfig.js").read_text(encoding="utf-8")
            module_path = tmp_path / "useLlmConfig-under-test.mjs"
            module_path.write_text(source, encoding="utf-8")
            (tmp_path / "vue.mjs").write_text(
                textwrap.dedent(
                    """
                    export function computed(fn) { return { get value() { return fn(); } }; }
                    export function onMounted() {}
                    export function ref(value) { return { value }; }
                    """
                ),
                encoding="utf-8",
            )
            api_dir = tmp_path / "api"
            api_dir.mkdir()
            (api_dir / "inkmoment.mjs").write_text(
                textwrap.dedent(
                    """
                    export async function clearArkKey() { return {}; }
                    export async function getArkKeyStatus() { return {}; }
                    export async function getDiagnostics() { return {}; }
                    export async function getLlmConcurrency() { return {}; }
                    export async function getLlmModels() { return { models: [] }; }
                    export async function saveArkKey() { return {}; }
                    """
                ),
                encoding="utf-8",
            )
            patched = module_path.read_text(encoding="utf-8")
            patched = patched.replace('from "vue";', f'from "{(tmp_path / "vue.mjs").as_uri()}";')
            patched = patched.replace('from "../api/inkmoment";', f'from "{(api_dir / "inkmoment.mjs").as_uri()}";')
            module_path.write_text(patched, encoding="utf-8")
            script = textwrap.dedent(
                f"""
                import assert from "node:assert/strict";
                import {{ normalizeModels }} from {module_path.as_uri()!r};

                const models = normalizeModels([
                  {{ id: "vision-pro", label: {{ text: "JSON object label" }} }},
                  {{ id: "vision-lite", display_name: "Vision Lite" }},
                  {{ model: "fallback-model", label: {{ nested: true }} }},
                ]);

                assert.equal(models[0].label, "vision-pro");
                assert.equal(models[1].label, "Vision Lite");
                assert.equal(models[2].label, "fallback-model");
                assert(!models.some((model) => model.label.includes("[object Object]")));
                """
            )
            result = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
