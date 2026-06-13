import io
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from inkmoment.watermark import WatermarkConfig, batch_export, list_templates, render


class WatermarkRefactorTest(unittest.TestCase):
    def test_watermark_is_package_with_small_modules(self):
        project_root = Path(__file__).resolve().parents[1]
        self.assertFalse((project_root / "inkmoment" / "watermark.py").exists())

        package_root = project_root / "inkmoment" / "watermark"
        self.assertTrue(package_root.is_dir())
        for path in package_root.rglob("*.py"):
            with self.subTest(path=path.relative_to(project_root)):
                line_count = len(path.read_text(encoding="utf-8").splitlines())
                self.assertLessEqual(line_count, 200)

    def test_all_templates_render_jpeg_bytes(self):
        with TemporaryDirectory() as tmp:
            img_path = Path(tmp) / "sample.jpg"
            Image.new("RGB", (160, 100), (120, 80, 40)).save(img_path, "JPEG")

            template_ids = [item["id"] for item in list_templates()]
            self.assertEqual(
                template_ids,
                [
                    "A",
                    "B_full",
                    "B_clean",
                    "C_full",
                    "C_clean",
                    "D_full",
                    "D_clean",
                    "F_full",
                    "F_clean",
                    "G",
                    "H",
                ],
            )
            for template_id in template_ids:
                with self.subTest(template=template_id):
                    data = render(
                        img_path,
                        WatermarkConfig(template=template_id),
                        preview_max_side=96,
                    )
                    self.assertTrue(data.startswith(b"\xff\xd8"))
                    out_img = Image.open(io.BytesIO(data))
                    self.assertGreater(out_img.size[0], 0)
                    self.assertGreater(out_img.size[1], 0)

    def test_batch_export_keeps_existing_api_contract(self):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            img_path = tmp_path / "sample.jpg"
            Image.new("RGB", (120, 80), (40, 100, 160)).save(img_path, "JPEG")

            result = batch_export([img_path], tmp_path / "out", WatermarkConfig(template="A"))

            self.assertEqual(result, {"ok": 1, "failed": [], "total": 1})
            self.assertTrue((tmp_path / "out" / "sample.jpg").exists())

    def test_raw_render_uses_embedded_preview(self):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            raw_path = tmp_path / "IMG_0001.CR3"
            raw_path.write_bytes(b"raw")
            preview = io.BytesIO()
            Image.new("RGB", (160, 100), (80, 120, 160)).save(preview, "JPEG")
            rawpy_module = _fake_rawpy(preview.getvalue())
            previous = sys.modules.get("rawpy")
            sys.modules["rawpy"] = rawpy_module
            try:
                data = render(raw_path, WatermarkConfig(template="A"), preview_max_side=96)
            finally:
                if previous is None:
                    sys.modules.pop("rawpy", None)
                else:
                    sys.modules["rawpy"] = previous

        self.assertTrue(data.startswith(b"\xff\xd8"))
        rendered = Image.open(io.BytesIO(data))
        self.assertGreater(rendered.size[0], 0)
        self.assertGreater(rendered.size[1], 0)


def _fake_rawpy(jpeg_bytes: bytes):
    class FakeRaw:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_thumb(self):
            return types.SimpleNamespace(format="jpeg", data=jpeg_bytes)

    return types.SimpleNamespace(
        ThumbFormat=types.SimpleNamespace(JPEG="jpeg", BITMAP="bitmap"),
        imread=lambda _path: FakeRaw(),
    )


if __name__ == "__main__":
    unittest.main()
