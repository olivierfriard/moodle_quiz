"""Application settings loaded from the project `.env` file."""

import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).with_name(".env"))


def _env_bool(name: str) -> bool:
    value = os.environ[name].strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


APPLICATION_ROOT = os.environ["APPLICATION_ROOT"]
ADMIN_PASSWORD_SHA256 = os.environ["ADMIN_PASSWORD_SHA256"]
DATABASE_URL = os.environ["DATABASE_URL"]
DEBUG = _env_bool("DEBUG")
