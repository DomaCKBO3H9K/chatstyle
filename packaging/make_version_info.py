"""Создаёт файл ресурса версии для PyInstaller из chatstyle.__version__ (единый источник версии).

    python packaging/make_version_info.py build/version_info.txt

Свойства файла chatstyle.exe (название, описание, версия, автор, лицензия) берутся отсюда.
"""

import re
import sys
from pathlib import Path

from chatstyle import __version__

COMPANY = "chatstyle contributors"
DESCRIPTION = "chatstyle — верификация авторства русскоязычной переписки"
COPYRIGHT = "MIT License. © 2026 chatstyle contributors"
RUSSIAN = 0x0419  # язык ресурса; кодовая страница 1200 (UTF-16)


def version_tuple(version: str) -> tuple[int, int, int, int]:
    """«1.2.3» -> (1, 2, 3, 0); ошибка, если версия не вида N.N.N."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if match is None:
        raise ValueError(f"Версия должна иметь вид N.N.N, получено {version!r}")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch, 0


def render(version: str = __version__) -> str:
    """Текст файла в формате, который понимает PyInstaller (--version-file)."""
    numbers = version_tuple(version)
    fields = [
        ("CompanyName", COMPANY),
        ("FileDescription", DESCRIPTION),
        ("FileVersion", version),
        ("InternalName", "chatstyle"),
        ("LegalCopyright", COPYRIGHT),
        ("OriginalFilename", "chatstyle.exe"),
        ("ProductName", "chatstyle"),
        ("ProductVersion", version),
    ]
    structs = ",\n          ".join(f"StringStruct({k!r}, {v!r})" for k, v in fields)
    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numbers},
    prodvers={numbers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '{RUSSIAN:04x}04b0',
        [{structs}])
    ]),
    VarFileInfo([VarStruct('Translation', [{RUSSIAN}, 1200])])
  ]
)
"""


def main(target: Path) -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(), encoding="utf-8")
    print(f"Ресурс версии записан: {target} (версия {__version__})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Использование: python packaging/make_version_info.py ФАЙЛ")
    main(Path(sys.argv[1]))
