from pathlib import Path

from chatstyle.errors import ChatstyleError


def read_txt(path: Path) -> list[str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ChatstyleError(f"Не удалось прочитать файл {path}: {exc}") from exc

    try:
        text = raw.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise ChatstyleError(
            f"Файл {path} не в кодировке UTF-8. Сохраните его как UTF-8 и повторите."
        ) from exc

    return text.splitlines()
