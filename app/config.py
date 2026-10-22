import os
import secrets
from pathlib import Path


def load_secret_key(instance_path):
    from_env = os.environ.get("POGATHER_SECRET_KEY")
    if from_env:
        return from_env
    key_file = Path(instance_path) / "secret_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    key_file.write_text(key, encoding="utf-8")
    return key
