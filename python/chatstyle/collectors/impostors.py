"""Загрузка папки с «посторонними» авторами для General Impostors."""

from pathlib import Path

from chatstyle.collectors.txt import read_txt
from chatstyle.errors import ChatstyleError
from chatstyle.preprocess import preprocess


def load_impostor_directory(directory: Path) -> dict[str, list[str]]:
    """Прочитать папку: каждый файл .txt (UTF-8, одно сообщение на строку) — один посторонний автор.

    Файлы идут по имени, подпапки и скрытые файлы пропускаются, сообщения проходят ту же
    предобработку, что и у остальных авторов. Файл, в котором после предобработки не осталось
    сообщений, пропускается. Ключ результата — имя файла.
    """
    if not directory.is_dir():
        raise ChatstyleError(f"Папка с посторонними текстами не найдена: {directory}")

    files = sorted(
        (path for path in directory.iterdir() if _is_impostor_file(path)),
        key=lambda path: (path.name.lower(), path.name),
    )
    if not files:
        raise ChatstyleError(f"В папке {directory} нет файлов .txt с посторонними текстами.")

    authors: dict[str, list[str]] = {}
    for path in files:
        messages = preprocess(read_txt(path))
        if messages:
            authors[path.name] = messages
    if not authors:
        raise ChatstyleError(
            f"В файлах папки {directory} не осталось сообщений после предобработки."
        )
    return authors


def _is_impostor_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".txt" and not path.name.startswith(".")
