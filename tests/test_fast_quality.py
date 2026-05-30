import unittest

from PIL import Image, ImageDraw, ImageFilter

from inkmoment.fast_quality import analyze_image_fast


class FastQualityTest(unittest.TestCase):
    def test_blurry_checkerboard_scores_lower_than_sharp_checkerboard(self):
        sharp = _checkerboard()
        blurry = sharp.filter(ImageFilter.GaussianBlur(radius=8))

        sharp_q = analyze_image_fast(sharp, file_size=500_000, strength="standard")
        blurry_q = analyze_image_fast(blurry, file_size=500_000, strength="standard")

        self.assertGreater(sharp_q.quality_score, blurry_q.quality_score)
        self.assertGreater(sharp_q.blur_score, blurry_q.blur_score)
        self.assertFalse(sharp_q.auto_reject)
        self.assertTrue(blurry_q.auto_reject)
        self.assertIn("very_blurry", blurry_q.flags)

    def test_exposure_and_low_information_flags_are_hard_rejects(self):
        cases = [
            ("dark", Image.new("RGB", (768, 768), (4, 4, 4)), "underexposed"),
            ("bright", Image.new("RGB", (768, 768), (252, 252, 252)), "overexposed"),
            ("flat", Image.new("RGB", (768, 768), (128, 128, 128)), "low_information"),
        ]

        for name, image, expected_flag in cases:
            with self.subTest(name=name):
                quality = analyze_image_fast(image, file_size=500_000, strength="standard")

                self.assertIn(expected_flag, quality.flags)
                self.assertTrue(quality.auto_reject)
                self.assertTrue(quality.reject_reason)

    def test_advanced_strength_is_not_more_lenient_than_standard(self):
        mildly_blurry = _checkerboard(block=24).filter(ImageFilter.GaussianBlur(radius=2.5))

        standard = analyze_image_fast(mildly_blurry, file_size=500_000, strength="standard")
        advanced = analyze_image_fast(mildly_blurry, file_size=500_000, strength="advanced")

        self.assertEqual(standard.blur_score, advanced.blur_score)
        self.assertLessEqual(advanced.quality_score, standard.quality_score)


def _checkerboard(size: int = 768, block: int = 16) -> Image.Image:
    image = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(image)
    for y in range(0, size, block):
        for x in range(0, size, block):
            if (x // block + y // block) % 2 == 0:
                draw.rectangle((x, y, x + block - 1, y + block - 1), fill="black")
    return image


if __name__ == "__main__":
    unittest.main()
