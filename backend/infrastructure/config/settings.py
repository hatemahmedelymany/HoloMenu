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

ENV = os.getenv("ENV", "development")
DISABLE_WS_AUTH = os.getenv("DISABLE_WS_AUTH", "false").lower() in ("true", "1", "yes")

# Check config.json as well for consistency
config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.json')
if os.path.exists(config_path):
    try:
        import json
        with open(config_path, 'r') as f:
            file_config = json.load(f)
            if "DISABLE_WS_AUTH" in file_config:
                val = file_config["DISABLE_WS_AUTH"]
                if isinstance(val, bool):
                    DISABLE_WS_AUTH = val
                elif isinstance(val, str):
                    DISABLE_WS_AUTH = val.lower() in ("true", "1", "yes")
            if "websocket" in file_config and "disable_auth" in file_config["websocket"]:
                val = file_config["websocket"]["disable_auth"]
                if isinstance(val, bool):
                    DISABLE_WS_AUTH = val
                elif isinstance(val, str):
                    DISABLE_WS_AUTH = val.lower() in ("true", "1", "yes")
    except Exception:
        pass

if ENV == "production" and DISABLE_WS_AUTH:
    raise RuntimeError("Cannot disable WebSocket auth in production")

