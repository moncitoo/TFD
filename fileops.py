"""Descompressió, moviment de fitxers i integració amb Jellyfin."""
import asyncio
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import List

import aiohttp

import config

log = logging.getLogger(__name__)


def sanitize(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip().strip(".")
    return name or "Sense nom"


def _run(cmd: List[str]) -> bool:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("Error executant %s: %s", cmd[0], e)
        return False
    if r.returncode != 0:
        log.warning("%s ha fallat (%s): %s", cmd[0], r.returncode, r.stderr[-500:])
    return r.returncode == 0


def extract_archive(archive: Path, out_dir: Path) -> bool:
    """Extreu amb unrar (per .rar) o 7z; esborra l'original només si té èxit."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = False
    if archive.suffix.lower() == ".rar" and shutil.which("unrar"):
        ok = _run(["unrar", "x", "-o+", "-y", str(archive), str(out_dir) + "/"])
    if not ok and shutil.which("7z"):
        ok = _run(["7z", "x", "-y", f"-o{out_dir}", str(archive)])
    if ok:
        archive.unlink(missing_ok=True)
    return ok


def collect(directory: Path, exts: set) -> List[Path]:
    return sorted(p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in exts)


def final_path(series: str, season: int, ep: int, ext: str) -> Path:
    series = sanitize(series)
    return (config.JELLYFIN_PATH / series / f"Season {season:02d}"
            / f"{series} - S{season:02d}E{ep:02d}{ext}")


def move_unique(src: Path, dest: Path, overwrite: bool) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not overwrite:
        i = 1
        while dest.with_name(f"{dest.stem}.{i}{dest.suffix}").exists():
            i += 1
        dest = dest.with_name(f"{dest.stem}.{i}{dest.suffix}")
    shutil.move(str(src), str(dest))
    return dest


def list_series_folders() -> List[str]:
    if not config.JELLYFIN_PATH.is_dir():
        return []
    return sorted(p.name for p in config.JELLYFIN_PATH.iterdir() if p.is_dir())


async def refresh_jellyfin() -> bool:
    if not (config.JELLYFIN_URL and config.JELLYFIN_API_KEY):
        return False
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(f"{config.JELLYFIN_URL}/Library/Refresh",
                              headers={"X-Emby-Token": config.JELLYFIN_API_KEY}) as r:
                return r.status in (200, 204)
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.error("Jellyfin refresh ha fallat: %s", e)
        return False
