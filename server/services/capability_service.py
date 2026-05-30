def get_capabilities() -> dict:
    try:
        from inkmoment.quality import has_face_support

        face = bool(has_face_support())
    except Exception:
        face = False
    return {"face_aware": face}
