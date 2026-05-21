import mimetypes
from pathlib import Path
from .chat_utils import MEDIA_DIR

ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic"}
ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}
ALLOWED_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".aac", ".flac"}

def save_upload(uploaded_file, prefix="file"):
    suffix = Path(uploaded_file.name).suffix.lower()
    safe_name = f"{prefix}_{abs(hash(uploaded_file.name + str(uploaded_file.size)))}{suffix}"
    out_path = MEDIA_DIR / safe_name
    with open(out_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    mime = mimetypes.guess_type(str(out_path))[0] or "application/octet-stream"
    return str(out_path), mime

def is_image_file(name):
    return Path(name).suffix.lower() in ALLOWED_IMAGE_EXTS

def is_video_file(name):
    return Path(name).suffix.lower() in ALLOWED_VIDEO_EXTS

def is_audio_file(name):
    return Path(name).suffix.lower() in ALLOWED_AUDIO_EXTS