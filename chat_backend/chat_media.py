import mimetypes
from datetime import datetime
from pathlib import Path
from .chat_utils import MEDIA_DIR, ensure_dirs

ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm"}
ALLOWED_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".aac"}
ALLOWED_FILE_EXTS = ALLOWED_IMAGE_EXTS | ALLOWED_VIDEO_EXTS | ALLOWED_AUDIO_EXTS | {".pdf", ".txt", ".csv", ".docx", ".xlsx"}


def _safe_filename(name: str) -> str:
    keep = []
    for ch in name:
        if ch.isalnum() or ch in (".", "_", "-", " "):
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep).strip() or "upload"


def save_upload(uploaded_file, prefix="file"):
    ensure_dirs()
    original = _safe_filename(uploaded_file.name)
    suffix = Path(original).suffix.lower()
    if suffix not in ALLOWED_FILE_EXTS:
        raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_path = MEDIA_DIR / f"{prefix}_{stamp}_{original}"
    with open(out_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    mime = getattr(uploaded_file, "type", None) or mimetypes.guess_type(str(out_path))[0] or "application/octet-stream"
    return str(out_path), mime


def is_image_file(name):
    return Path(name).suffix.lower() in ALLOWED_IMAGE_EXTS


def is_video_file(name):
    return Path(name).suffix.lower() in ALLOWED_VIDEO_EXTS


def is_audio_file(name):
    return Path(name).suffix.lower() in ALLOWED_AUDIO_EXTS
