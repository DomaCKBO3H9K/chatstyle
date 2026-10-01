"""Пути пользовательских файлов chatstyle: ключи, сессия Telegram, кэш.

Файлы лежат в каталоге данных пользователя, а не рядом с exe и не во временной
папке распаковки PyInstaller, поэтому пути не зависят от способа установки.
"""

import os
import sys
from pathlib import Path

APP_NAME = "chatstyle"
HOME_ENV = "CHATSTYLE_HOME"


def data_dir() -> Path:
    """Каталог данных: %APPDATA%\\chatstyle, ~/.local/share/chatstyle или $CHATSTYLE_HOME."""
    override = os.environ.get(HOME_ENV)
    if override:
        return Path(override)
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        root = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return root / APP_NAME


def env_file() -> Path:
    """Файл .env с ключами Telegram в каталоге данных."""
    return data_dir() / ".env"


def session_file() -> Path:
    """Файл сессии Telegram (Telethon)."""
    return data_dir() / "telegram.session"


def cache_dir() -> Path:
    """Каталог кэша сообщений."""
    return data_dir() / "cache"
