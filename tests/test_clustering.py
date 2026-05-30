import unittest
from types import SimpleNamespace

import numpy as np

from inkmoment import clustering, fast_clustering


class ClusteringTest(unittest.TestCase):
    def test_expert_cluster_merges_similar_dino_vectors_and_splits_time_gap(self):
        infos = [
            _expert_info("/photos/IMG_0001.jpg", 0, _unit([1.0, 0.0, 0.0])),
            _expert_info("/photos/IMG_0002.jpg", 1, _unit([0.999, 0.001, 0.0])),
            _expert_info("/photos/IMG_1000.jpg", 4_000, _unit([0.0, 1.0, 0.0])),
        ]

        groups = clustering.cluster(infos)

        self.assertEqual(_as_group_set(groups), {frozenset({0, 1}), frozenset({2})})

    def test_expert_cluster_refuses_missing_dino_vectors(self):
        infos = [
            _expert_info("/photos/a.jpg", 0, None),
            _expert_info("/photos/b.jpg", 1, None),
        ]

        with self.assertRaisesRegex(RuntimeError, "DINOv2"):
            clustering.cluster(infos)

    def test_fast_cluster_merges_same_hash_color_and_splits_time_gap(self):
        color_a = np.zeros(144, dtype=np.float32)
        color_a[0] = 1.0
        color_b = np.zeros(144, dtype=np.float32)
        color_b[1] = 1.0
        infos = [
            _fast_info("/photos/IMG_0001.jpg", 0, "0" * 16, color_a),
            _fast_info("/photos/IMG_0002.jpg", 1, "0" * 16, color_a),
            _fast_info("/photos/IMG_1000.jpg", 4_000, "f" * 16, color_b),
        ]

        groups = fast_clustering.cluster(infos)

        self.assertEqual(_as_group_set(groups), {frozenset({0, 1}), frozenset({2})})


def _expert_info(path: str, timestamp: float, dinov2):
    return SimpleNamespace(
        path=path,
        phash="0" * 16,
        timestamp=timestamp,
        mtime=timestamp,
        exif_summary=_meta(),
        dinov2=dinov2,
        face_embeddings=[],
    )


def _fast_info(path: str, timestamp: float, hash_value: str, color_hist):
    return SimpleNamespace(
        path=path,
        phash=hash_value,
        dhash=hash_value,
        whash=hash_value,
        ahash=hash_value,
        timestamp=timestamp,
        mtime=timestamp,
        exif_summary=_meta(),
        color_hist=color_hist,
        orb_descs=None,
        orb_kps=None,
        quality={"quality_score": 50},
    )


def _meta() -> dict:
    return {
        "camera": "TestCam",
        "lens": "35mm",
        "focal_length": "35mm",
        "aperture": "f/2.8",
        "iso": "100",
    }


def _unit(values) -> np.ndarray:
    arr = np.array(values, dtype=np.float32)
    return arr / np.linalg.norm(arr)


def _as_group_set(groups: list[list[int]]) -> set[frozenset[int]]:
    return {frozenset(group) for group in groups}


if __name__ == "__main__":
    unittest.main()
