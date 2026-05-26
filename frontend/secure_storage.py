from pathlib import Path
import json
import hashlib
from cryptography.fernet import Fernet

BASE = Path("data/users")
BASE.mkdir(parents=True, exist_ok=True)

MASTER_KEY_FILE = Path("data/master.key")


def get_master_key():
    if not MASTER_KEY_FILE.exists():
        MASTER_KEY_FILE.write_bytes(Fernet.generate_key())
    return MASTER_KEY_FILE.read_bytes()


FERNET = Fernet(get_master_key())


def user_dir(user_key: str) -> Path:
    hashed = hashlib.sha256(user_key.encode()).hexdigest()
    path = BASE / hashed
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_secure_json(user_key: str, filename: str, data: dict):
    path = user_dir(user_key) / f"{filename}.enc"

    encrypted = FERNET.encrypt(
        json.dumps(data, default=str).encode()
    )

    path.write_bytes(encrypted)


def load_secure_json(user_key: str, filename: str):
    path = user_dir(user_key) / f"{filename}.enc"

    if not path.exists():
        return {}

    try:
        decrypted = FERNET.decrypt(path.read_bytes())
        return json.loads(decrypted.decode())
    except Exception:
        return {}