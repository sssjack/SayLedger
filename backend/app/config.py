from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


class Settings:
    def __init__(self) -> None:
        env_file = Path(__file__).resolve().parent.parent / ".env"
        if env_file.exists():
            for raw in env_file.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

        self.data_dir = Path(os.getenv("LEDGER_DATA_DIR", "/data"))
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.data_dir / "ledger.db"
        self.upload_dir = self.data_dir / "uploads"
        self.upload_dir.mkdir(parents=True, exist_ok=True)

        self.jwt_secret = os.getenv("LEDGER_JWT_SECRET", "clockwise-ledger-dev-secret")
        self.password = os.getenv("LEDGER_PASSWORD", "")
        self.allow_register = os.getenv("LEDGER_ALLOW_REGISTER", "1") == "1"
        self.token_days = int(os.getenv("LEDGER_TOKEN_DAYS", "180"))

        self.ai_base_url = os.getenv("AI_BASE_URL", "https://api.apiyi.com/v1").rstrip("/")
        self.ai_api_key = os.getenv("AI_API_KEY", "")
        self.ai_model = os.getenv("AI_MODEL", "gpt-6-luna")
        self.ai_timeout = float(os.getenv("AI_TIMEOUT_SEC", "90"))

        self.timezone = os.getenv("LEDGER_TZ", "Asia/Shanghai")
        self.wechat_enabled = os.getenv("WECHAT_ENABLED", "1") == "1"
        self.wechat_encryption_key = os.getenv("WECHAT_ENCRYPTION_KEY", "")
        self.public_url = os.getenv("LEDGER_PUBLIC_URL", "").rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
