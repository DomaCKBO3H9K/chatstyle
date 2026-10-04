"""Проверяет тег релиза и печатает описание версии из CHANGELOG.md.

    python packaging/release_notes.py v0.1.0

Завершается с ошибкой, если тег не совпадает с chatstyle.__version__ или в CHANGELOG.md нет
раздела этой версии. Если версия ниже 1.0, печатает в первой строке «prerelease», иначе «release».
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def package_version() -> str:
    text = (REPO / "python" / "chatstyle" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"', text, flags=re.M)
    if not match:
        raise SystemExit("не найден __version__")
    return match.group(1)


def changelog_section(version: str) -> str:
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    pattern = rf"^## {re.escape(version)}\s*\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, text, flags=re.M | re.S)
    if not match:
        raise SystemExit(f"в CHANGELOG.md нет раздела «## {version}»")
    return match.group(1).strip() + "\n"


def is_prerelease(version: str) -> bool:
    return int(version.split(".")[0]) < 1 or "-" in version


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit("использование: release_notes.py vX.Y.Z")
    tag = argv[1]
    version = package_version()
    if tag != f"v{version}":
        raise SystemExit(f"тег {tag} не совпадает с версией пакета v{version}")
    print("prerelease" if is_prerelease(version) else "release")
    print(changelog_section(version), end="")


if __name__ == "__main__":
    main(sys.argv)
