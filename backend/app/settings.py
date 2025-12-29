import os

def get_env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None and value.strip() != "" else default

APP_NAME = get_env("APP_NAME", "FaSiKo-Werkstatt Backend")
DATABASE_URL = get_env("DATABASE_URL", "sqlite:////data/app.db")

# Where uploaded files are stored (persisted via docker volume)
UPLOAD_DIR = get_env("UPLOAD_DIR", "/data/uploads")

# Where open point evidence files are stored
OPENPOINT_DIR = get_env("OPENPOINT_DIR", "/data/openpoints")

# Max upload size in bytes (30 MB)
MAX_UPLOAD_BYTES = int(get_env("MAX_UPLOAD_BYTES", str(30 * 1024 * 1024)))