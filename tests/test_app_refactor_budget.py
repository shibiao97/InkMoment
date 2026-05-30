import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AppRefactorBudgetTest(unittest.TestCase):
    def test_app_py_stays_within_refactor_budget(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertLessEqual(len(source.splitlines()), 300)
        self.assertLessEqual(source.count("RUNTIME."), 10)

    def test_tauri_shell_stays_modular(self):
        src_root = ROOT / "src-tauri" / "src"
        self.assertLessEqual(_line_count(src_root / "lib.rs"), 100)
        for path in src_root.rglob("*.rs"):
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertLessEqual(_line_count(path), 200)

    def test_frontend_app_is_shell_not_flow_state_machine(self):
        app_vue = ROOT / "frontend" / "src" / "App.vue"
        source = app_vue.read_text(encoding="utf-8")

        self.assertLessEqual(_line_count(app_vue), 180)
        self.assertNotIn("currentView ===", source)
        self.assertNotIn("currentView.value =", source)
        self.assertTrue((ROOT / "frontend" / "src" / "composables" / "useFlowState.js").is_file())


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


if __name__ == "__main__":
    unittest.main()
