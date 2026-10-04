"""Документация не должна расходиться с кодом: флаги, примеры вывода, обязательные разделы."""

import re
import runpy
from pathlib import Path

import pytest
import typer.main
from chatstyle.cli import app
from chatstyle.pipeline import DISCLAIMER
from typer.testing import CliRunner

REPO = Path(__file__).resolve().parent.parent
README = (REPO / "README.ru.md").read_text(encoding="utf-8")
EXAMPLE_REPORT = REPO / "docs" / "example_report.md"

runner = CliRunner()


def command_options(name: str) -> set[str]:
    command = typer.main.get_command(app).commands[name]  # type: ignore[attr-defined]
    return {opt for param in command.params for opt in param.opts if opt.startswith("--")}


def code_blocks(language: str | None = None) -> list[str]:
    pattern = r"```(\w*)\n(.*?)```"
    return [
        body
        for lang, body in re.findall(pattern, README, flags=re.S)
        if language is None or lang == language
    ]


def chatstyle_commands() -> list[tuple[str, str]]:
    """Команды chatstyle из bash-блоков README (с продолжениями строк через обратную косую)."""
    commands = []
    for block in code_blocks("bash"):
        text = block.replace("\\\n", " ")
        for line in text.splitlines():
            match = re.match(r"\s*chatstyle\s+(compare|features|login)\b(.*)", line)
            if match:
                commands.append((match.group(1), match.group(2)))
    return commands


# --- структура ---


@pytest.mark.parametrize(
    "heading",
    ["Установка", "Источники данных", "Пример отчёта", "Оценка качества", "Ограничения"]
    + ["Этика и приватность", "Статус и известные пробелы", "Литература", "Лицензия"],
)
def test_required_sections_exist(heading: str) -> None:
    assert re.search(rf"^## {re.escape(heading)}$", README, flags=re.M)


def test_readme_states_the_probabilistic_nature_up_front() -> None:
    head = README[:1500]
    assert "статистическая оценка сходства стиля, а не доказательство авторства" in head


def test_relative_links_point_to_existing_files() -> None:
    targets = re.findall(r"\]\((?!https?://|#)([^)#]+)(?:#[^)]*)?\)", README)
    assert targets, "в README нет ссылок на файлы репозитория"
    for target in targets:
        assert (REPO / target).exists(), f"битая ссылка в README: {target}"


def test_no_quality_numbers_without_real_data() -> None:
    assert not re.search(r"AUC\s*[=≈:]?\s*0[.,]\d", README)
    assert "Результатов пока нет" in README


# --- флаги и команды ---


def test_flags_in_examples_exist_in_the_cli() -> None:
    commands = chatstyle_commands()
    assert {name for name, _ in commands} >= {"compare", "features", "login"}
    for name, arguments in commands:
        known = command_options(name) | {"--help"}
        for flag in re.findall(r"--[\w-]+", arguments):
            assert flag in known, f"в README `chatstyle {name} {flag}`, а такого флага нет"


def test_compare_options_are_documented() -> None:
    for option in command_options("compare") - {"--help"}:
        assert option in README, f"параметр {option} не описан в README"


def test_options_table_mentions_only_real_flags() -> None:
    table = README.split("| Параметр `compare` |", 1)[1].split("###", 1)[0]
    known = command_options("compare") | {"--help"}
    for flag in re.findall(r"`[^`]*?(--[\w-]+)", table):
        assert flag in known


# --- примеры вывода совпадают с настоящим ---


def readme_output_block(first_line_start: str) -> list[str]:
    for block in code_blocks(""):
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if lines and lines[0].startswith(first_line_start):
            return lines
    raise AssertionError(f"в README нет блока вывода, начинающегося с {first_line_start!r}")


def test_quick_start_output_matches_the_real_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO)
    result = runner.invoke(
        app,
        ["compare", "-u", "file:tests/fixtures/unknown.txt"]
        + ["-c", "file:tests/fixtures/same.txt", "-c", "file:tests/fixtures/other.txt"],
        env={"COLUMNS": "130"},
    )
    assert result.exit_code == 0
    actual = [line.rstrip() for line in result.output.splitlines()]
    for line in readme_output_block("Неизвестный автор: file:tests/fixtures/unknown.txt"):
        assert line in actual, f"строки нет в реальном выводе: {line}"


@pytest.fixture(scope="module")
def generated_example(tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = tmp_path_factory.mktemp("example_data")
    runpy.run_path(str(REPO / "docs" / "make_example_data.py"), run_name="docs_example")["main"](
        target
    )
    return target


def test_example_report_is_reproducible(
    generated_example: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(generated_example)
    result = runner.invoke(
        app,
        ["compare", "-u", "file:unknown.txt", "-c", "file:candidate_same.txt"]
        + ["-c", "file:candidate_other.txt", "--impostors", "impostors"]
        + ["--report", "report.md"],
        env={"COLUMNS": "130"},
    )
    assert result.exit_code == 0

    def body(text: str) -> list[str]:
        return [line for line in text.splitlines() if not line.startswith("Дата:")]

    generated = body((generated_example / "report.md").read_text(encoding="utf-8"))
    committed = body(EXAMPLE_REPORT.read_text(encoding="utf-8"))
    assert committed[2:] == generated  # первые две строки — баннер примера

    actual = [line.rstrip() for line in result.output.splitlines()]
    for line in readme_output_block("┌──────────────────────────┬"):
        assert line in actual, f"строки нет в реальном выводе: {line}"


def test_example_report_is_clearly_marked_as_fictional() -> None:
    text = EXAMPLE_REPORT.read_text(encoding="utf-8")
    assert text.startswith("> **Пример на вымышленных (синтетических) данных.**")
    assert DISCLAIMER in text


# --- английский README.md: те же команды и ссылки, что в русском ---

README_EN = (REPO / "README.md").read_text(encoding="utf-8")


def bash_blocks(text: str) -> list[str]:
    return [
        body for lang, body in re.findall(r"```(\w*)\n(.*?)```", text, flags=re.S) if lang == "bash"
    ]


def test_english_readme_links_to_the_russian_one_and_back() -> None:
    assert "(README.ru.md)" in README_EN[:400]
    assert "(README.md)" in README[:400]


def test_english_readme_relative_links_point_to_existing_files() -> None:
    targets = re.findall(r"\]\((?!https?://|#)([^)#]+)(?:#[^)]*)?\)", README_EN)
    assert targets
    for target in targets:
        assert (REPO / target).exists(), f"битая ссылка в README.md: {target}"


def test_english_readme_internal_anchors_exist() -> None:
    headings = {
        re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")
        for title in re.findall(r"^#{2,3} (.+)$", README_EN, flags=re.M)
    }
    for anchor in re.findall(r"\]\(#([^)]+)\)", README_EN):
        assert anchor in headings, f"в README.md нет раздела для якоря #{anchor}"


def test_english_readme_has_the_same_bash_commands_as_the_russian_one() -> None:
    def chatstyle_lines(text: str) -> list[str]:
        lines = []
        for block in bash_blocks(text):
            for line in block.replace("\\n", " ").splitlines():
                if re.match(r"\s*chatstyle\s+(compare|features|login)\b", line):
                    lines.append(line.split()[1])
        return lines

    assert sorted(set(chatstyle_lines(README_EN))) == sorted(set(chatstyle_lines(README)))


def test_english_readme_documents_every_compare_option() -> None:
    for option in command_options("compare") - {"--help"}:
        assert option in README_EN, f"параметр {option} не описан в README.md"
    table = README_EN.split("| `compare` option |", 1)[1].split("###", 1)[0]
    known = command_options("compare") | {"--help"}
    for flag in re.findall(r"`[^`]*?(--[\w-]+)", table):
        assert flag in known


def test_english_readme_states_the_probabilistic_nature_and_has_requirements() -> None:
    assert "not proof of authorship" in README_EN[:1500]
    assert re.search(r"^## Requirements$", README_EN, flags=re.M)
    assert "There are no results yet" in README_EN


def test_requirements_section_matches_pyproject() -> None:
    import tomllib

    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    section = README_EN.split("## Requirements", 1)[1].split("## Installation", 1)[0]
    for dependency in project["dependencies"]:
        name = re.split(r"[<>=!~\[]", dependency)[0]
        assert f"`{name}`" in section, f"зависимость {name} не описана в Requirements"
    for extra, packages in project["optional-dependencies"].items():
        assert f"| `{extra}` |" in section
        for package in packages:
            assert f"`{re.split(r'[<>=!~]', package)[0]}`" in section
