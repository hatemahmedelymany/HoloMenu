"""
Centralized Configuration Loader and Environment Settings.
"""
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 3306)),
    "db":       os.getenv("DB_NAME", "holomenu_db"),
    "user":     os.getenv("DB_USER", "holomenu_app"),
    "password": os.getenv("DB_PASSWORD", ""),
    "charset":  "utf8mb4",
    "autocommit": True,
}

CORS_ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000,http://localhost:8080,http://127.0.0.1:8080"
).split(",")
