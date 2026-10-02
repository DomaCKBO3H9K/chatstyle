import re
from pathlib import Path

import pytest
from chatstyle.cli import app
from chatstyle.gui.api import Api, compare_view_dict
from chatstyle.gui.model import CompareOutcome
from chatstyle.pipeline import CandidateResult, run_comparison, wordgram_text
from chatstyle.report import write_report
from chatstyle.wordgrams import FIRST_CODE, RARE_CODE, word_views, words_of
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture(autouse=True)
def _chdir(tmp_path, monkeypatch):
    monkeypatch.chdir(Path(__file__).parent / "fixtures")


def test_words_of():
    assert words_of("Привет, МИР! well-known 42") == ["привет", "мир", "well-known"]


def test_word_views_rare_and_common():
    u, c = word_views(
        ["кот сидит дома", "ну вообще"],
        {"a": ["кот спит дома"], "b": ["ночь река"]},
    )
    # первое сообщение: общие слова первым и третьим символом, «сидит» — RARE_CODE
    assert len(u[0]) == 3
    assert u[0][0] != RARE_CODE and ord(u[0][0]) >= FIRST_CODE
    assert u[0][1] == RARE_CODE
    assert u[0][2] != RARE_CODE and ord(u[0][2]) >= FIRST_CODE
    # unknown second message: two RARE_CODE
    assert len(u[1]) == 2
    assert u[1][0] == RARE_CODE and u[1][1] == RARE_CODE
    # b has one message of two RARE_CODE
    assert len(c["b"][0]) == 2
    assert c["b"][0][0] == RARE_CODE and c["b"][0][1] == RARE_CODE
    # same word gives same symbol across authors
    assert u[0][0] == c["a"][0][0]


def test_word_views_skips_messages_without_words():
    u, c = word_views(["123", "привет"], {"a": ["привет"]})
    assert len(u) == 1


def test_word_views_deterministic():
    args = (["кот сидит дома", "ну вообще"], {"a": ["кот спит дома"], "b": ["ночь река"]})
    assert word_views(*args) == word_views(*args)


def test_cli_wordgrams_column():
    result = runner.invoke(
        app,
        [
            "compare",
            "-u",
            "file:unknown.txt",
            "-c",
            "file:same.txt",
            "-c",
            "file:other.txt",
            "--wordgrams",
        ],
        env={"COLUMNS": "200"},
    )
    assert result.exit_code == 0
    assert "Слова" in result.output

    result_no = runner.invoke(
        app,
        ["compare", "-u", "file:unknown.txt", "-c", "file:same.txt", "-c", "file:other.txt"],
        env={"COLUMNS": "200"},
    )
    assert result_no.exit_code == 0
    assert "Слова" not in result_no.output


def test_run_comparison_wordgrams():
    result = run_comparison(
        "file:unknown.txt",
        ["file:same.txt", "file:other.txt"],
        wordgrams=True,
    )
    assert result.wordgrams is True
    sims = {c.label: c.wordgram_similarity for c in result.candidates}
    assert sims["file:same.txt"] > sims["file:other.txt"]
    assert 0 <= sims["file:same.txt"] <= 1
    assert 0 <= sims["file:other.txt"] <= 1

    result_no = run_comparison(
        "file:unknown.txt",
        ["file:same.txt", "file:other.txt"],
        wordgrams=False,
    )
    assert result_no.wordgrams is False
    assert all(c.wordgram_similarity is None for c in result_no.candidates)


def test_wordgram_text_format():
    r = CandidateResult(label="x", words=1, messages=1, similarity=0.5, wordgram_similarity=0.6489)
    assert wordgram_text(r) == "0.649"
    r_none = CandidateResult(
        label="x", words=1, messages=1, similarity=0.5, wordgram_similarity=None
    )
    assert wordgram_text(r_none) == "—"


@pytest.mark.parametrize("suffix", ["md", "html"])
def test_reports_have_wordgrams_header(tmp_path, suffix):
    result = run_comparison(
        "file:unknown.txt",
        ["file:same.txt", "file:other.txt"],
        wordgrams=True,
    )
    path = tmp_path / f"r.{suffix}"
    write_report(path, result)
    text = path.read_text(encoding="utf-8")
    assert "Слова (косинус)" in text

    result_no = run_comparison(
        "file:unknown.txt",
        ["file:same.txt", "file:other.txt"],
        wordgrams=False,
    )
    path_no = tmp_path / f"r_no.{suffix}"
    write_report(path_no, result_no)
    text_no = path_no.read_text(encoding="utf-8")
    assert "Слова (косинус)" not in text_no


def test_gui_view_wordgrams():
    result = run_comparison(
        "file:unknown.txt",
        ["file:same.txt", "file:other.txt"],
        wordgrams=True,
    )
    view = compare_view_dict(CompareOutcome(result, None))
    assert view["wordgrams"] is True
    for cand in view["candidates"]:
        assert re.fullmatch(r"\d\.\d{3}", cand["wordgrams"])

    result_no = run_comparison(
        "file:unknown.txt",
        ["file:same.txt", "file:other.txt"],
        wordgrams=False,
    )
    view_no = compare_view_dict(CompareOutcome(result_no, None))
    assert view_no["wordgrams"] is False
    for cand in view_no["candidates"]:
        assert cand["wordgrams"] == "—"


def test_api_rejects_non_bool_wordgrams():
    api = Api(allowed_paths=["u.txt", "a.txt"])
    resp = api.start_compare(
        {"unknown": "file:u.txt", "candidates": ["file:a.txt"], "wordgrams": "yes"}
    )
    assert resp["ok"] is False
    assert {e["code"] for e in resp["errors"]} == {"bad_input"}
