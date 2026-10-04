"""Описание релиза берётся из CHANGELOG.md и совпадает с версией пакета."""

import importlib.util
from pathlib import Path

import pytest
from chatstyle import __version__

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "release_notes", REPO / "packaging" / "release_notes.py"
)
assert spec and spec.loader
release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_notes)


def test_package_version_matches_the_module() -> None:
    assert release_notes.package_version() == __version__


def test_changelog_has_a_section_for_the_current_version() -> None:
    assert release_notes.changelog_section(__version__).strip()


def test_missing_section_is_an_error() -> None:
    with pytest.raises(SystemExit):
        release_notes.changelog_section("99.0.0")


def test_wrong_tag_is_rejected() -> None:
    with pytest.raises(SystemExit):
        release_notes.main(["release_notes.py", "v99.0.0"])


def test_prerelease_below_one() -> None:
    assert release_notes.is_prerelease("0.1.0")
    assert release_notes.is_prerelease("1.0.0-rc1")
    assert not release_notes.is_prerelease("1.0.0")
