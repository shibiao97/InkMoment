from __future__ import annotations

import logging

from inkmoment.grouper import ImageInfo


logger = logging.getLogger("inkmoment")


def _identify_main_subjects(
    infos: list[ImageInfo],
    log: logging.Logger | None = logger,
) -> set:
    import numpy as np

    all_embs = []
    for index, info in enumerate(infos):
        for face_index, embedding in enumerate(info.face_embeddings or []):
            all_embs.append((index, face_index, embedding))

    if not all_embs:
        for info in infos:
            info._main_subject_ids = set()
        return set()

    cluster_centers = []
    cluster_counts = []
    cluster_members = []
    similarity_threshold = 0.65

    for _index, _face_index, embedding in all_embs:
        if not cluster_centers:
            cluster_centers.append(embedding.copy())
            cluster_counts.append(1)
            cluster_members.append(0)
            continue
        sims = [float(np.dot(embedding, center)) for center in cluster_centers]
        best = int(np.argmax(sims))
        if sims[best] > similarity_threshold:
            old_count = cluster_counts[best]
            new_center = (cluster_centers[best] * old_count + embedding) / (old_count + 1)
            norm = float(np.linalg.norm(new_center)) + 1e-8
            cluster_centers[best] = (new_center / norm).astype(np.float32)
            cluster_counts[best] += 1
            cluster_members.append(best)
        else:
            cluster_centers.append(embedding.copy())
            cluster_counts.append(1)
            cluster_members.append(len(cluster_centers) - 1)

    face_count = len(all_embs)
    main_threshold = max(3, int(face_count * 0.20))
    main_ids = {cluster_id for cluster_id, count in enumerate(cluster_counts) if count >= main_threshold}

    per_image: dict[int, set] = {}
    for (image_index, _face_index, _), cluster_id in zip(all_embs, cluster_members):
        per_image.setdefault(image_index, set()).add(cluster_id)
    for index, info in enumerate(infos):
        info._main_subject_ids = per_image.get(index, set())

    if main_ids and log is not None:
        log.info(
            "主角识别：发现 %s 个主角脸簇（总簇数 %s，总人脸 %s）。出现次数 %s",
            len(main_ids),
            len(cluster_centers),
            face_count,
            [cluster_counts[index] for index in main_ids],
        )
    return main_ids
