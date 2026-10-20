"""Configuració carregada des de .env"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _req(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Falta la variable d'entorn obligatòria: {name}")
    return value


API_ID = int(_req("API_ID"))
API_HASH = _req("API_HASH")
BOT_TOKEN = _req("BOT_TOKEN")
ADMIN_USER_ID = int(_req("ADMIN_USER_ID"))
JELLYFIN_PATH = Path(os.getenv("JELLYFIN_PATH", "/media/jellyfin/series"))
JELLYFIN_URL = os.getenv("JELLYFIN_URL", "").rstrip("/")
JELLYFIN_API_KEY = os.getenv("JELLYFIN_API_KEY", "")
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "/tmp/downloads"))
SESSION_DIR = Path(os.getenv("SESSION_DIR", "./sessions"))
BASE_DIR = Path(__file__).resolve().parent

VIDEO_EXT = {".mkv", ".mp4", ".avi"}
ARCHIVE_EXT = {".rar", ".zip", ".7z"}
SUB_EXT = {".srt", ".ass", ".ssa", ".sub", ".vtt"}
