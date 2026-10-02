"""Настройки окна (язык и тема) в файле каталога данных.

Окно работает в приватном режиме WebView2: его профиль живёт во временной папке и удаляется при
выходе, поэтому браузерному хранилищу и автозаполнению негде что-то запоминать. Выбор языка и
темы хранится здесь, в маленьком файле, и принимается только из белого списка значений.
"""

import json
import os
from pathlib import Path

from chatstyle.errors import ChatstyleError
from chatstyle.paths import data_dir

ALLOWED: dict[str, tuple[str, ...]] = {
    "language": ("ru", "en", "ar", "es", "zh", "fr"),
    "theme": ("light", "dark"),
}
FILE_NAME = "gui-settings.json"


def settings_file() -> Path:
    return data_dir() / FILE_NAME


def load_settings() -> dict[str, str]:
    """Сохранённые настройки; всё, чего нет в белом списке, и любые сбои чтения отбрасываются."""
    try:
        raw = json.loads(settings_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        key: value
        for key, value in raw.items()
        if key in ALLOWED and isinstance(value, str) and value in ALLOWED[key]
    }


def save_setting(name: object, value: object) -> dict[str, str]:
    """Сохранить одну настройку; недопустимое имя или значение — ошибка, файл не меняется."""
    if not isinstance(name, str) or name not in ALLOWED:
        raise ChatstyleError("Неизвестная настройка.")
    if not isinstance(value, str) or value not in ALLOWED[name]:
        raise ChatstyleError("Недопустимое значение настройки.")
    current = load_settings()
    current[name] = value
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
    return current
