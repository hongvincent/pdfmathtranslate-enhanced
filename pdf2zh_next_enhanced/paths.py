from __future__ import annotations

import os
from pathlib import Path

DATA_ROOT = Path(os.environ.get("PDF2ZH_ENHANCED_DATA_DIR", "/data")).expanduser()
UPLOADS_DIR = DATA_ROOT / "uploads"
ARTIFACTS_DIR = DATA_ROOT / "artifacts"
LOGS_DIR = DATA_ROOT / "logs"
SECRETS_DIR = DATA_ROOT / "secrets"
STATE_DIR = DATA_ROOT / "state"
DATABASE_PATH = DATA_ROOT / "app.db"
ENCRYPTION_KEY_PATH = SECRETS_DIR / "app.key"
DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("PDF2ZH_ENHANCED_DEFAULT_TIMEOUT", "3600"))
WORKER_POLL_INTERVAL = float(os.environ.get("PDF2ZH_ENHANCED_WORKER_POLL", "1.5"))
WORKER_STALE_SECONDS = int(os.environ.get("PDF2ZH_ENHANCED_STALE_SECONDS", "600"))
FRONTEND_DIST_DIR = Path(
    os.environ.get(
        "PDF2ZH_ENHANCED_FRONTEND_DIST",
        str(Path(__file__).resolve().parents[1] / "frontend" / "dist"),
    )
).expanduser()


def ensure_data_dirs() -> None:
    for path in (
        DATA_ROOT,
        UPLOADS_DIR,
        ARTIFACTS_DIR,
        LOGS_DIR,
        SECRETS_DIR,
        STATE_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
