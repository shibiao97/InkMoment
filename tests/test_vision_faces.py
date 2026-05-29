import unittest
from unittest.mock import patch

from PIL import Image

from inkmoment import vision


class VisionFaceExtractionTest(unittest.TestCase):
    def test_insightface_none_shape_error_is_treated_as_no_faces(self):
        class EmptyDetector:
            def get(self, _arr):
                raise AttributeError("'NoneType' object has no attribute 'shape'")

        with patch.object(vision, "_ensure_insightface", return_value=EmptyDetector()):
            faces = vision.extract_faces(Image.new("RGB", (128, 128), "white"))

        self.assertEqual(faces, [])

    def test_insightface_malformed_face_is_skipped(self):
        class MalformedFace:
            bbox = None
            embedding = None

        class Detector:
            def get(self, _arr):
                return [MalformedFace()]

        with patch.object(vision, "_ensure_insightface", return_value=Detector()):
            faces = vision.extract_faces(Image.new("RGB", (128, 128), "white"))

        self.assertEqual(faces, [])

    def test_other_insightface_attribute_errors_still_raise(self):
        class BrokenDetector:
            def get(self, _arr):
                raise AttributeError("unexpected detector failure")

        with patch.object(vision, "_ensure_insightface", return_value=BrokenDetector()):
            with self.assertRaises(AttributeError):
                vision.extract_faces(Image.new("RGB", (128, 128), "white"))


if __name__ == "__main__":
    unittest.main()
