from pathlib import Path

ROOT = Path("Chat_data")
MEDIA_DIR = ROOT / "media"
UPLOAD_DIR = ROOT / "uploads"
LOG_DIR = ROOT / "logs"
DB_PATH = ROOT / "chat.db"


def ensure_dirs():
    ROOT.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
