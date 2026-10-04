"""Архив для Linux: только нужные файлы, install.sh исполняемый, лишнего нет."""

import importlib.util
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "make_release", REPO / "packaging" / "make_release.py"
)
assert spec and spec.loader
make_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_release)


def test_linux_archive_contains_only_what_is_needed(tmp_path: Path) -> None:
    target = tmp_path / "chatstyle-linux.tar.gz"
    make_release.build_linux_archive(target)
    with tarfile.open(target) as archive:
        members = {member.name: member for member in archive.getmembers()}
    names = set(members)
    assert {"chatstyle/CMakeLists.txt", "chatstyle/pyproject.toml", "chatstyle/README.md"} <= names
    assert "chatstyle/python/chatstyle/cli.py" in names
    assert "chatstyle/core/src/bindings.cpp" in names
    assert members["chatstyle/install.sh"].mode & 0o111
    forbidden = ("tests/", "experiments/", "packaging/", "docs/", ".github/", "build/", "dist/")
    assert not [n for n in names if any(f"chatstyle/{part}" in n for part in forbidden)]
    assert not [n for n in names if n.endswith((".pyc", ".gitkeep", ".session", ".env"))]
    assert not [n for n in names if "core/tests" in n]


def test_install_script_has_unix_line_endings() -> None:
    script = (REPO / "packaging" / "linux" / "install.sh").read_bytes()
    assert script.startswith(b"#!/usr/bin/env bash") and b"\r" not in script
