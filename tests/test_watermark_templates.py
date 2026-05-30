import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from inkmoment.watermark import WatermarkConfig, render
from inkmoment.watermark.templates.registry import get_style_spec, list_templates


class WatermarkTemplatesTest(unittest.TestCase):
    def test_template_ids_are_unique_and_registered(self):
        templates = list_templates()
        ids = [item["id"] for item in templates]

        self.assertEqual(len(ids), len(set(ids)))
        for template_id in ids:
            with self.subTest(template=template_id):
                render_fn, _show_params = get_style_spec(template_id)
                self.assertTrue(callable(render_fn))

    def test_unknown_template_falls_back_to_default_jpeg_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "sample.jpg"
            Image.new("RGB", (180, 120), (80, 120, 160)).save(image_path, "JPEG")

            data = render(image_path, WatermarkConfig(template="unknown"), preview_max_side=96)

        self.assertTrue(data.startswith(b"\xff\xd8"))
        rendered = Image.open(io.BytesIO(data))
        self.assertGreater(rendered.size[0], 0)
        self.assertGreater(rendered.size[1], 0)


if __name__ == "__main__":
    unittest.main()
