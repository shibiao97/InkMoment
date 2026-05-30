from PIL import Image, ImageDraw, ImageFilter

from inkmoment.grouper import ImageInfo
from inkmoment.quality import analyze_image
from server.services.analysis_cache_service import ImageAnalysisCache
from server.state.local_store import LocalStateStore


def checkerboard(size=256, block=8):
    img = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(img)
    for y in range(0, size, block):
        for x in range(0, size, block):
            if (x // block + y // block) % 2 == 0:
                draw.rectangle((x, y, x + block - 1, y + block - 1), fill="black")
    return img


def test_blurry_image_is_rejected_more_than_sharp_image():
    sharp = checkerboard()
    blurry = sharp.filter(ImageFilter.GaussianBlur(radius=8))

    sharp_q = analyze_image(sharp, file_size=200_000, strength="standard", face_aware=False)
    blurry_q = analyze_image(blurry, file_size=200_000, strength="standard", face_aware=False)

    assert sharp_q.blur_score > blurry_q.blur_score
    assert "blurry" not in sharp_q.flags
    assert {"blurry", "very_blurry"} & set(blurry_q.flags)
    assert blurry_q.auto_reject is True


def test_under_and_over_exposed_images_are_rejected():
    dark = Image.new("RGB", (256, 256), (4, 4, 4))
    bright = Image.new("RGB", (256, 256), (252, 252, 252))

    dark_q = analyze_image(dark, file_size=200_000, strength="standard", face_aware=False)
    bright_q = analyze_image(bright, file_size=200_000, strength="standard", face_aware=False)

    assert "underexposed" in dark_q.flags
    assert dark_q.auto_reject is True
    assert "overexposed" in bright_q.flags
    assert bright_q.auto_reject is True


def test_low_information_image_is_rejected():
    flat = Image.new("RGB", (256, 256), (128, 128, 128))

    q = analyze_image(flat, file_size=200_000, strength="standard", face_aware=False)

    assert "low_information" in q.flags
    assert q.auto_reject is True
    assert q.reject_reason


def test_prescreen_strength_changes_blur_strictness():
    mildly_blurry = checkerboard(block=16).filter(ImageFilter.GaussianBlur(radius=2.2))

    conservative = analyze_image(mildly_blurry, file_size=200_000, strength="conservative", face_aware=False)
    aggressive = analyze_image(mildly_blurry, file_size=200_000, strength="aggressive", face_aware=False)

    assert aggressive.blur_score == conservative.blur_score
    assert aggressive.quality_score <= conservative.quality_score
    assert ("blurry" in aggressive.flags) or aggressive.auto_reject


def test_quality_info_can_be_serialized_to_plain_dict():
    q = analyze_image(checkerboard(), file_size=123_456, strength="standard", face_aware=False)
    data = q.to_dict()

    assert data["blur_score"] == q.blur_score
    assert data["file_size"] == 123_456
    assert isinstance(data["flags"], list)


def test_grouper_cache_round_trips_quality_metrics(tmp_path):
    photo = tmp_path / "a.jpg"
    photo.write_bytes(b"fake")
    info = ImageInfo(
        path=str(photo),
        phash="0" * 16,
        size=photo.stat().st_size,
        mtime=photo.stat().st_mtime,
        quality={"quality_score": 72.5, "flags": ["blurry"], "reject_reason": "画面模糊"},
    )
    store = LocalStateStore(tmp_path / "state.sqlite3")
    store.initialize()
    cache = ImageAnalysisCache(store, str(tmp_path))

    cache.put(info, engine="fast", strength="standard", face_aware=False, llm_model=None)
    loaded = cache.get(str(photo), [], engine="fast", strength="standard", face_aware=False, llm_model=None)

    assert loaded is not None
    assert loaded.quality["quality_score"] == 72.5
    assert loaded.quality["flags"] == ["blurry"]
