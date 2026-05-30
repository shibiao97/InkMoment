import json
import subprocess
import sys
import textwrap
import unittest


HEAVY_MODULES = [
    "inkmoment.vision",
    "torch",
    "torchvision",
    "pyiqa",
    "insightface",
    "onnxruntime",
    "transformers",
]


class LazyImportTest(unittest.TestCase):
    def test_importing_flask_app_does_not_load_expert_stack(self):
        loaded = _run_probe(
            """
            import app
            print(json.dumps([name for name in HEAVY_MODULES if name in sys.modules]))
            """
        )

        self.assertEqual(loaded, [])

    def test_fast_compute_infos_does_not_load_expert_stack(self):
        loaded = _run_probe(
            """
            import tempfile
            from pathlib import Path
            from PIL import Image
            from inkmoment.grouper import compute_infos

            with tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                Image.new("RGB", (96, 96), "white").save(folder / "one.jpg")
                infos, skipped = compute_infos(str(folder), engine="fast", workers=1)
                assert len(infos) == 1, (infos, skipped)
            print(json.dumps([name for name in HEAVY_MODULES if name in sys.modules]))
            """
        )

        self.assertEqual(loaded, [])

    def test_fast_compute_infos_importtime_does_not_import_expert_stack(self):
        imported = _run_importtime_probe(
            """
            import tempfile
            from pathlib import Path
            from PIL import Image
            from inkmoment.grouper import compute_infos

            with tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                Image.new("RGB", (96, 96), "white").save(folder / "one.jpg")
                infos, skipped = compute_infos(str(folder), engine="fast", workers=1)
                assert len(infos) == 1, (infos, skipped)
            """
        )

        self.assertEqual(imported, [])


def _run_probe(body: str) -> list[str]:
    script = "\n".join(
        [
            "import json",
            "import sys",
            f"HEAVY_MODULES = {HEAVY_MODULES!r}",
            textwrap.dedent(body).strip(),
        ]
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
        text=True,
        capture_output=True,
    )
    return json.loads(result.stdout.strip())


def _run_importtime_probe(body: str) -> list[str]:
    result = subprocess.run(
        [sys.executable, "-X", "importtime", "-c", textwrap.dedent(body).strip()],
        check=True,
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
        text=True,
        capture_output=True,
    )
    modules = [
        line.rsplit("|", 1)[-1].strip()
        for line in result.stderr.splitlines()
        if line.startswith("import time:") and "|" in line
    ]
    return [
        name for name in HEAVY_MODULES if any(module == name or module.startswith(f"{name}.") for module in modules)
    ]


if __name__ == "__main__":
    unittest.main()
