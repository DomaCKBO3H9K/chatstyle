import sys
from pathlib import Path

import pytest
from chatstyle.cli import app
from chatstyle.morph import reset_cache
from chatstyle.pipeline import run_comparison
from chatstyle.report import write_report
from typer.testing import CliRunner

pytest.importorskip("pymorphy3")

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()
COMPARE = ["compare", "-u", "file:unknown.txt", "-c", "file:same.txt", "-c", "file:other.txt"]


def invoke(args: list[str]):
    return runner.invoke(app, args, env={"COLUMNS": "200"})


@pytest.fixture(autouse=True)
def fixtures_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(FIXTURES)


def test_compare_morph_adds_column() -> None:
    result = invoke([*COMPARE, "--morph"])
    assert result.exit_code == 0
    assert "Части речи" in result.output


def test_compare_without_morph_has_no_column() -> None:
    result = invoke(COMPARE)
    assert result.exit_code == 0
    assert "Части речи" not in result.output


def test_features_morph_prints_shares() -> None:
    result = invoke(["features", "file:same.txt", "--morph"])
    assert result.exit_code == 0
    assert "Части речи:" in result.output
    assert "Части речи:" not in invoke(["features", "file:same.txt"]).output


def test_missing_dependency_exit_code_and_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "pymorphy3", None)
    reset_cache()
    try:
        for args in ([*COMPARE, "--morph"], ["features", "file:same.txt", "--morph"]):
            result = invoke(args)
            assert result.exit_code == 2
            assert "pip install chatstyle[morph]" in result.output
    finally:
        reset_cache()


@pytest.mark.parametrize("suffix", ["md", "html"])
def test_report_has_morph_header_only_with_morph(tmp_path: Path, suffix: str) -> None:
    specs = ["file:same.txt", "file:other.txt"]
    with_morph = tmp_path / f"with.{suffix}"
    write_report(with_morph, run_comparison("file:unknown.txt", specs, morph=True))
    assert "Части речи (косинус)" in with_morph.read_text(encoding="utf-8")

    without = tmp_path / f"without.{suffix}"
    write_report(without, run_comparison("file:unknown.txt", specs))
    assert "Части речи (косинус)" not in without.read_text(encoding="utf-8")
