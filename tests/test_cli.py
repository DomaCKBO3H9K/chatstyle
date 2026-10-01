from pathlib import Path

import pytest
from chatstyle.cli import app
from typer.testing import CliRunner

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def invoke(args: list[str]) -> pytest.CaptureFixture:
    """Invoke the CLI with given arguments."""
    return runner.invoke(app, args, env={"COLUMNS": "200"})


@pytest.fixture
def fixtures_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Change working directory to the fixtures directory."""
    monkeypatch.chdir(FIXTURES)


def test_compare_success(fixtures_cwd: None) -> None:
    args = [
        "compare",
        "-u",
        "file:unknown.txt",
        "-c",
        "file:other.txt",
        "-c",
        "file:same.txt",
    ]
    result = invoke(args)
    assert result.exit_code == 0
    output = result.output
    assert "file:same.txt" in output
    assert "file:other.txt" in output
    assert "Неизвестный автор: file:unknown.txt" in output
    assert "Сходство" in output


def test_rows_sorted_by_similarity(fixtures_cwd: None) -> None:
    args = [
        "compare",
        "-u",
        "file:unknown.txt",
        "-c",
        "file:other.txt",
        "-c",
        "file:same.txt",
    ]
    result = invoke(args)
    output = result.output
    start = output.find("Сходство")
    assert start != -1
    idx_same = output.find("file:same.txt", start)
    idx_other = output.find("file:other.txt", start)
    assert idx_same < idx_other


def test_disclaimer_and_low_volume_warning(fixtures_cwd: None) -> None:
    args = [
        "compare",
        "-u",
        "file:unknown.txt",
        "-c",
        "file:other.txt",
        "-c",
        "file:same.txt",
    ]
    result = invoke(args)
    output = result.output.lower()
    assert "не доказательство авторства" in output
    assert "меньше 1000 слов" in output


def test_long_option_names(fixtures_cwd: None) -> None:
    args = [
        "compare",
        "--unknown",
        "file:unknown.txt",
        "--candidate",
        "file:same.txt",
    ]
    result = invoke(args)
    assert result.exit_code == 0


def test_missing_file(fixtures_cwd: None) -> None:
    args = ["compare", "-u", "file:nope_xyz.txt", "-c", "file:same.txt"]
    result = invoke(args)
    assert result.exit_code == 2
    assert "Ошибка:" in result.output


def test_not_implemented_source(fixtures_cwd: None) -> None:
    args = ["compare", "-u", "tg:@user", "-c", "file:same.txt"]
    result = invoke(args)
    assert result.exit_code == 2
    assert "не реализован" in result.output.lower()


def test_not_utf8_source(fixtures_cwd: None) -> None:
    args = ["compare", "-u", "file:not_utf8.txt", "-c", "file:same.txt"]
    result = invoke(args)
    assert result.exit_code == 2
    assert "UTF-8" in result.output


def test_missing_candidate_option(fixtures_cwd: None) -> None:
    args = ["compare", "-u", "file:unknown.txt"]
    result = invoke(args)
    assert result.exit_code == 2


def test_duplicate_candidate(fixtures_cwd: None) -> None:
    args = [
        "compare",
        "-u",
        "file:unknown.txt",
        "-c",
        "file:same.txt",
        "-c",
        "file:same.txt",
    ]
    result = invoke(args)
    assert result.exit_code == 2
    assert "дважды" in result.output.lower()


def test_version(fixtures_cwd: None) -> None:
    args = ["--version"]
    result = invoke(args)
    assert result.exit_code == 0
    output = result.output
    assert "chatstyle 0.1.0" in output
    assert "ядро 0.1.0" in output


def test_help(fixtures_cwd: None) -> None:
    result = invoke(["--help"])
    assert result.exit_code == 0
    assert "compare" in result.output

    result2 = invoke(["compare", "--help"])
    assert result2.exit_code == 0
    assert "--unknown" in result2.output


def test_no_args_shows_help(fixtures_cwd: None) -> None:
    result = invoke([])
    assert "compare" in result.output
