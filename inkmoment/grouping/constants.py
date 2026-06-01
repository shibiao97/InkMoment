# PIL 直接能解码的格式
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".bmp", ".tif", ".tiff"}

# RAW 格式：靠 rawpy 提取内嵌 JPEG 预览图来分析，原文件搬运时整个搬。
# 如果同 stem 同目录有 JPG/JPEG 等 IMAGE_EXTS 文件，则优先用那个（更高质量，不需要 rawpy）。
RAW_EXTS = {
    ".cr2",
    ".cr3",
    ".crw",  # Canon
    ".nef",
    ".nrw",  # Nikon
    ".arw",
    ".srf",
    ".sr2",  # Sony
    ".dng",  # Adobe / 通用
    ".raf",  # Fuji
    ".orf",  # Olympus
    ".rw2",  # Panasonic
    ".pef",  # Pentax
    ".rwl",  # Leica
    ".srw",  # Samsung
    ".x3f",  # Sigma
}

ALL_INPUT_EXTS = IMAGE_EXTS | RAW_EXTS

# 分析尺寸：所有 AI 模型 / 质量算法吃的最大长边。
ANALYSIS_MAX_SIDE = 2048

# 阈值：时间间隔近时（同一拍摄场景），允许更大的视觉差异
THRESHOLD_NEAR = 10  # 同场景内 (<= 5 分钟)
THRESHOLD_FAR = 6  # 跨场景 (> 5 分钟)
NEAR_SECONDS = 300  # 5 分钟
