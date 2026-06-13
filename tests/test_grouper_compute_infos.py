import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from inkmoment.grouping.models import ImageInfo
from inkmoment.grouper import compute_infos, scan_folder


class GrouperComputeInfosTest(unittest.TestCase):
    def test_fast_compute_infos_populates_fast_signals_without_heavy_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = Path(tmp) / "IMG_0001.jpg"
            _save_checkerboard(photo)

            infos, skipped = compute_infos(tmp, engine="fast", workers=1)

        self.assertEqual(skipped, [])
        self.assertEqual(len(infos), 1)
        info = infos[0]
        self.assertEqual(Path(info.path).name, "IMG_0001.jpg")
        self.assertTrue(info.phash)
        self.assertTrue(info.dhash)
        self.assertTrue(info.whash)
        self.assertTrue(info.ahash)
        self.assertIsNotNone(info.color_hist)
        self.assertIsNotNone(info.orb_descs)
        self.assertIsInstance(info.quality, dict)
        self.assertIn("quality_score", info.quality)
        self.assertIsNone(info.dinov2)

    def test_scan_folder_pairs_raw_primary_with_jpeg_companion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "A001.CR3"
            jpg = root / "A001.JPG"
            loose = root / "B001.JPG"
            ignored = root / "_inkmoment" / "ignored.jpg"
            ignored.parent.mkdir()
            raw.write_bytes(b"raw")
            jpg.write_bytes(b"jpg")
            loose.write_bytes(b"jpg")
            ignored.write_bytes(b"jpg")

            pairs = scan_folder(tmp)

        normalized = [(Path(primary).name, [Path(item).name for item in companions]) for primary, companions in pairs]
        self.assertEqual(normalized, [("A001.CR3", ["A001.JPG"]), ("B001.JPG", [])])

    def test_cached_infos_emit_photo_wall_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = Path(tmp) / "IMG_0001.jpg"
            _save_checkerboard(photo)
            cached = ImageInfo(
                path=str(photo),
                phash="0" * 16,
                quality={"quality_score": 88},
                exif_summary={},
            )
            events = []

            infos, skipped = compute_infos(
                tmp,
                engine="fast",
                workers=1,
                cache_get=lambda *_args: cached,
                event_cb=lambda name, path, info, reason: events.append((name, path, info, reason)),
            )

        self.assertEqual(skipped, [])
        self.assertEqual(infos, [cached])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0], ("IMG_0001.jpg", str(photo), cached, None))


def _save_checkerboard(path: Path, size: int = 256, block: int = 16) -> None:
    image = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(image)
    for y in range(0, size, block):
        for x in range(0, size, block):
            if (x // block + y // block) % 2 == 0:
                draw.rectangle((x, y, x + block - 1, y + block - 1), fill="black")
    image.save(path, "JPEG")


if __name__ == "__main__":
    unittest.main()
