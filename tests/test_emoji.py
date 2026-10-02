import re
from pathlib import Path

import pytest
from chatstyle.cli import app
from chatstyle.emoji import emoji_of, emoji_views
from chatstyle.gui.api import Api, compare_view_dict
from chatstyle.gui.model import CompareOutcome
from chatstyle.pipeline import CandidateResult, emoji_text, run_comparison
from chatstyle.report import write_report
from typer.testing import CliRunner

runner = CliRunner()
UNKNOWN = ["привет 😀", "как дела 😀😂", "ок 👍"]
LIKE = ["ха 😀😂", "да 😀", "ну ок"]
OTHER = ["нет", "ладно 👍🏽👍🏽"]


@pytest.fixture
def specs(tmp_path: Path) -> tuple[str, str, str]:
    def write(name: str, lines: list[str]) -> str:
        path = tmp_path / name
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return f"file:{path}"

    return write("unknown.txt", UNKNOWN), write("like.txt", LIKE), write("other.txt", OTHER)


def test_emoji_of_keeps_composite_emoji_whole() -> None:
    text = "привет 😀😀 👍🏽 ❤️ 👨‍👩‍👧"
    assert emoji_of(text) == ["😀", "😀", "👍🏽", "❤️", "👨‍👩‍👧"]


def test_emoji_of_without_emoji() -> None:
    assert emoji_of("просто текст") == []


def test_emoji_views_one_symbol_per_emoji() -> None:
    unknown, candidates = emoji_views(["ха 😀", "нет"], {"a": ["😀😂"], "b": ["ок"]})
    assert len(unknown) == 1
    assert len(unknown[0]) == 1
    assert candidates["b"] == []
    assert len(candidates["a"][0]) == 2
    assert candidates["a"][0][0] == unknown[0][0]
    assert ord(unknown[0][0]) >= 0xF0000


def test_emoji_views_deterministic() -> None:
    args = (["ха 😀", "нет"], {"a": ["😀😂"], "b": ["ок"]})
    assert emoji_views(*args) == emoji_views(*args)


def test_run_comparison_emoji(specs: tuple[str, str, str]) -> None:
    unknown, like, other = specs
    result = run_comparison(unknown, [like, other], emoji=True)
    assert result.emoji is True
    scores = {item.label: item.emoji_similarity for item in result.candidates}
    assert scores[like] is not None and scores[other] is not None
    assert 0.0 <= scores[other] < scores[like] <= 1.0

    plain = run_comparison(unknown, [like, other])
    assert plain.emoji is False
    assert all(item.emoji_similarity is None for item in plain.candidates)


def test_candidate_without_emoji_has_no_score(tmp_path: Path, specs: tuple[str, str, str]) -> None:
    unknown, like, _ = specs
    empty = tmp_path / "plain.txt"
    empty.write_text("нет\nда\n", encoding="utf-8")
    result = run_comparison(unknown, [f"file:{empty}", like], emoji=True)
    by_label = {item.label: item for item in result.candidates}
    assert by_label[f"file:{empty}"].emoji_similarity is None
    assert emoji_text(by_label[f"file:{empty}"]) == "—"


def test_emoji_text_format() -> None:
    shown = CandidateResult(label="x", words=1, messages=1, similarity=0.5, emoji_similarity=0.6489)
    hidden = CandidateResult(label="x", words=1, messages=1, similarity=0.5)
    assert emoji_text(shown) == "0.649"
    assert emoji_text(hidden) == "—"


def test_cli_emoji_column(specs: tuple[str, str, str]) -> None:
    unknown, like, other = specs
    args = ["compare", "-u", unknown, "-c", like, "-c", other]
    with_flag = runner.invoke(app, [*args, "--emoji"], env={"COLUMNS": "200"})
    assert with_flag.exit_code == 0
    assert "Эмодзи" in with_flag.output
    without = runner.invoke(app, args, env={"COLUMNS": "200"})
    assert without.exit_code == 0
    assert "Эмодзи" not in without.output


@pytest.mark.parametrize("suffix", ["md", "html"])
def test_reports_have_emoji_header(
    tmp_path: Path, specs: tuple[str, str, str], suffix: str
) -> None:
    unknown, like, other = specs
    with_emoji = tmp_path / f"with.{suffix}"
    write_report(with_emoji, run_comparison(unknown, [like, other], emoji=True))
    assert "Эмодзи (косинус)" in with_emoji.read_text(encoding="utf-8")

    without = tmp_path / f"without.{suffix}"
    write_report(without, run_comparison(unknown, [like, other]))
    assert "Эмодзи (косинус)" not in without.read_text(encoding="utf-8")


def test_gui_view_emoji(specs: tuple[str, str, str]) -> None:
    unknown, like, other = specs
    view = compare_view_dict(
        CompareOutcome(run_comparison(unknown, [like, other], emoji=True), None)
    )
    assert view["emoji"] is True
    assert all(re.fullmatch(r"\d\.\d{3}", item["emoji"]) for item in view["candidates"])

    plain = compare_view_dict(CompareOutcome(run_comparison(unknown, [like, other]), None))
    assert plain["emoji"] is False
    assert all(item["emoji"] == "—" for item in plain["candidates"])


def test_api_rejects_non_bool_emoji() -> None:
    api = Api(allowed_paths=["u.txt", "a.txt"])
    answer = api.start_compare(
        {"unknown": "file:u.txt", "candidates": ["file:a.txt"], "emoji": "yes"}
    )
    assert answer["ok"] is False
    assert {item["code"] for item in answer["errors"]} == {"bad_input"}
