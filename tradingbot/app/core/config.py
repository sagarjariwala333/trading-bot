import os
from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to the directory containing the `app` package (i.e. tradingbot/).
# Used to resolve relative paths (DATA_DIR, sqlite URLs) consistently regardless of CWD,
# so the API process and the bot subprocess always share the same database.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Binance Futures HA-ALMA Bot API"

    # CORS configuration: expects a comma-separated list or JSON array of origins
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json
                return json.loads(v)
            return [i.strip() for i in v.split(",") if i.strip()]
        raise ValueError(v)

    # API Keys & secrets (fallback to empty string, can be loaded from env or .env file)
    BINANCE_API_KEY: str = ""
    BINANCE_API_SECRET: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    DATABASE_URL: str = ""

    # Bot settings
    DATA_DIR: str = "data"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()

# Normalize DATA_DIR to an absolute path rooted at the project root, so the sqlite
# database and any other derived paths resolve identically no matter what process CWD is.
if not os.path.isabs(settings.DATA_DIR):
    settings.DATA_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, settings.DATA_DIR))

# Ensure required directories exist
os.makedirs(settings.DATA_DIR, exist_ok=True)
