"""Переводы README совпадают по структуре с английским: ссылки, команды, таблицы, разделы."""

import re
import tomllib
from pathlib import Path

import pytest
import typer.main
from chatstyle.cli import app

REPO = Path(__file__).resolve().parent.parent
ENGLISH = "README.md"
TRANSLATIONS = ("README.ru.md", "README.es.md", "README.fr.md", "README.zh.md", "README.ar.md")
ALL = (ENGLISH, *TRANSLATIONS)
FENCE = re.compile(r"```(\w*)\n(.*?)```", flags=re.S)


def read(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8")


def headings(text: str, level: int) -> list[str]:
    return re.findall(rf"^{'#' * level} (.+)$", text, flags=re.M)


def slug(title: str) -> str:
    return re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")


def commands(text: str) -> list[str]:
    """Команды из блоков кода без пояснений и комментариев (они переведены)."""
    found = []
    for _, body in FENCE.findall(text):
        for line in body.replace("\\n", " ").splitlines():
            line = line.strip()
            if re.match(
                r"(chatstyle|python|pip|git|cd|sudo|powershell|\$env|dist\|cmake|ctest|pytest|ruff)",
                line,
            ):
                found.append(re.split(r"\s{2,}|\s#", line)[0].strip())
    return sorted(found)


def output_blocks(text: str) -> list[str]:
    return [body for lang, body in FENCE.findall(text) if lang == "" and ("┌" in body)]


def table_rows(text: str) -> int:
    return len(re.findall(r"^\|", text, flags=re.M))


def compare_options() -> set[str]:
    command = typer.main.get_command(app).commands["compare"]  # type: ignore[attr-defined]
    return {opt for param in command.params for opt in param.opts if opt.startswith("--")} - {
        "--help"
    }


@pytest.mark.parametrize("name", ALL)
def test_language_switcher_links_every_version(name: str) -> None:
    line = read(name).splitlines()[2]
    for target in ALL:
        assert f"({target})" in line or (target == name and "**" in line), f"{name}: нет {target}"
    assert line.count("**") == 2  # текущий язык выделен жирным, а не ссылкой


@pytest.mark.parametrize("name", ALL)
def test_relative_links_and_images_exist(name: str) -> None:
    targets = re.findall(r"\]\((?!https?://|#)([^)#]+)(?:#[^)]*)?\)", read(name))
    assert targets
    for target in targets:
        assert (REPO / target).exists(), f"{name}: битая ссылка {target}"


@pytest.mark.parametrize("name", ALL)
def test_internal_anchors_point_to_headings(name: str) -> None:
    text = read(name)
    available = {slug(title) for level in (2, 3) for title in headings(text, level)}
    for anchor in re.findall(r"\]\(#([^)]+)\)", text):
        assert anchor in available, f"{name}: нет раздела для якоря #{anchor}"


@pytest.mark.parametrize("name", TRANSLATIONS)
def test_translation_has_the_same_structure_as_the_english_one(name: str) -> None:
    english, text = read(ENGLISH), read(name)
    for level in (2, 3):
        assert len(headings(text, level)) == len(headings(english, level)), (
            f"{name}: заголовки {level}"
        )
    assert table_rows(text) == table_rows(english), f"{name}: строки таблиц"
    assert len(FENCE.findall(text)) == len(FENCE.findall(english)), f"{name}: блоки кода"
    assert len(re.findall(r"!\[", text)) == len(re.findall(r"!\[", english)), f"{name}: картинки"
    assert len(text) > 0.3 * len(english), f"{name}: перевод подозрительно короткий"


@pytest.mark.parametrize("name", [n for n in TRANSLATIONS if n != "README.ru.md"])
def test_translation_keeps_the_commands(name: str) -> None:
    # в русском README примеры чатов с русскими именами («Друзья»), остальные команды те же
    assert commands(read(name)) == commands(read(ENGLISH)), f"{name}: команды отличаются"


@pytest.mark.parametrize("name", TRANSLATIONS)
def test_translation_keeps_the_real_output(name: str) -> None:
    assert output_blocks(read(name)) == output_blocks(read(ENGLISH)), f"{name}: вывод отличается"


@pytest.mark.parametrize("name", ALL)
def test_every_compare_option_and_dependency_is_documented(name: str) -> None:
    text = read(name)
    for option in compare_options():
        assert option in text, f"{name}: параметр {option} не описан"
    project = tomllib.loads(read("pyproject.toml"))["project"]
    for dependency in project["dependencies"]:
        package = re.split(r"[<>=!~\[]", dependency)[0]
        assert f"`{package}`" in text, f"{name}: зависимость {package} не описана"
    for extra, packages in project["optional-dependencies"].items():
        assert f"`{extra}`" in text
        for package in packages:
            assert f"`{re.split(r'[<>=!~]', package)[0]}`" in text


@pytest.mark.parametrize("name", TRANSLATIONS)
def test_translation_keeps_the_disclaimer_markers(name: str) -> None:
    text = read(name)
    assert "> **" in text[:2500], f"{name}: нет выделенной оговорки в начале"
    assert "docs/demo_eval.py" in text
    assert "result.json" in text and "chatstyle.exe" in text
