"""Собирает папку release/: готовый архив для Linux и exe окна для Windows.

    python packaging/make_release.py

В архив попадают только файлы, нужные для установки (ядро, пакет Python, описание, лицензия,
install.sh), и только отслеживаемые git: тестов, экспериментов и служебных файлов в нём нет.
exe окна берётся из dist/ (его собирает packaging/build_exe.ps1 -Target gui).
"""

import hashlib
import io
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RELEASE = REPO / "release"
ARCHIVE_NAME = "chatstyle-linux.tar.gz"
GUI_EXE = "chatstyle-gui.exe"
INSTALL_SCRIPT = REPO / "packaging" / "linux" / "install.sh"
ROOTS = ("CMakeLists.txt", "pyproject.toml", "LICENSE", "README.md", "README.ru.md")
TREES = ("core/include", "core/src", "python")


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, check=True, capture_output=True
    ).stdout.decode("utf-8")
    return [name for name in out.split("\0") if name]


def wanted(name: str) -> bool:
    return name in ROOTS or any(name.startswith(tree + "/") for tree in TREES)


def build_linux_archive(target: Path) -> int:
    names = sorted(name for name in tracked_files() if wanted(name))
    with tarfile.open(target, "w:gz") as archive:
        for name in names:
            info = archive.gettarinfo(str(REPO / name), arcname=f"chatstyle/{name}")
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            data = (REPO / name).read_bytes().replace(b"\r\n", b"\n")
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
        script = INSTALL_SCRIPT.read_bytes().replace(b"\r\n", b"\n")
        info = tarfile.TarInfo("chatstyle/install.sh")
        info.size = len(script)
        info.mode = 0o755
        archive.addfile(info, io.BytesIO(script))
    return len(names) + 1


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    RELEASE.mkdir(exist_ok=True)
    archive = RELEASE / ARCHIVE_NAME
    count = build_linux_archive(archive)
    print(f"{archive.name}: {count} файлов, {archive.stat().st_size // 1024} КБ")
    produced = [archive]
    exe = REPO / "dist" / GUI_EXE
    if exe.exists():
        shutil.copy2(exe, RELEASE / GUI_EXE)
        produced.append(RELEASE / GUI_EXE)
        print(f"{GUI_EXE}: {exe.stat().st_size // 1024 // 1024} МБ")
    else:
        print(f"{GUI_EXE} нет в dist/: соберите packaging\\build_exe.ps1 -Target gui")
    sums = "".join(f"{sha256(path)}  {path.name}\n" for path in produced)
    (RELEASE / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")


if __name__ == "__main__":
    main()
