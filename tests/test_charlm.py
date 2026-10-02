import re
from pathlib import Path

import pytest
from chatstyle.cli import app
from chatstyle.gui.api import Api, compare_view_dict
from chatstyle.gui.model import CompareOutcome
from chatstyle.pipeline import CandidateResult, charlm_text, run_comparison
from chatstyle.report import write_report
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture(autouse=True)
def _chdir(monkeypatch):
    monkeypatch.chdir(Path(__file__).parent / "fixtures")


def test_cli_charlm_column():
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
            "--charlm",
        ],
        env={"COLUMNS": "200"},
    )
    assert result.exit_code == 0
    assert "Яз. модель" in result.output

    result_no = runner.invoke(
        app,
        ["compare", "-u", "file:unknown.txt", "-c", "file:same.txt", "-c", "file:other.txt"],
        env={"COLUMNS": "200"},
    )
    assert result_no.exit_code == 0
    assert "Яз. модель" not in result_no.output


def test_run_comparison_charlm():
    result = run_comparison("file:unknown.txt", ["file:same.txt", "file:other.txt"], charlm=True)
    assert result.charlm is True
    same = next(c for c in result.candidates if c.label == "file:same.txt")
    other = next(c for c in result.candidates if c.label == "file:other.txt")
    assert same.charlm_llr > 0
    assert other.charlm_llr < 0

    result_no = run_comparison(
        "file:unknown.txt", ["file:same.txt", "file:other.txt"], charlm=False
    )
    assert result_no.charlm is False
    for c in result_no.candidates:
        assert c.charlm_llr is None


def test_charlm_text_format():
    assert (
        charlm_text(
            CandidateResult(label="x", words=1, messages=1, similarity=0.5, charlm_llr=1.23456)
        )
        == "+1.235"
    )
    assert (
        charlm_text(
            CandidateResult(label="x", words=1, messages=1, similarity=0.5, charlm_llr=-0.5)
        )
        == "-0.500"
    )
    assert (
        charlm_text(
            CandidateResult(label="x", words=1, messages=1, similarity=0.5, charlm_llr=None)
        )
        == "—"
    )


def test_single_candidate_has_no_score():
    result = run_comparison("file:unknown.txt", ["file:same.txt"], charlm=True)
    assert result.candidates[0].charlm_llr is None
    assert charlm_text(result.candidates[0]) == "—"


def test_reports_have_charlm_header(tmp_path):
    result = run_comparison("file:unknown.txt", ["file:same.txt", "file:other.txt"], charlm=True)
    md_path = tmp_path / "r.md"
    html_path = tmp_path / "r.html"
    write_report(md_path, result)
    write_report(html_path, result)
    assert "Языковая модель (бит/символ)" in md_path.read_text(encoding="utf-8")
    assert "Языковая модель (бит/символ)" in html_path.read_text(encoding="utf-8")

    result_no = run_comparison(
        "file:unknown.txt", ["file:same.txt", "file:other.txt"], charlm=False
    )
    md_path_no = tmp_path / "r_no.md"
    html_path_no = tmp_path / "r_no.html"
    write_report(md_path_no, result_no)
    write_report(html_path_no, result_no)
    assert "Языковая модель (бит/символ)" not in md_path_no.read_text(encoding="utf-8")
    assert "Языковая модель (бит/символ)" not in html_path_no.read_text(encoding="utf-8")


def test_gui_view_charlm():
    result = run_comparison("file:unknown.txt", ["file:same.txt", "file:other.txt"], charlm=True)
    view = compare_view_dict(CompareOutcome(result, None))
    assert view["charlm"] is True
    for c in view["candidates"]:
        assert re.fullmatch(r"[+-]\d\.\d{3}", c["charlm"])

    result_no = run_comparison(
        "file:unknown.txt", ["file:same.txt", "file:other.txt"], charlm=False
    )
    view_no = compare_view_dict(CompareOutcome(result_no, None))
    assert view_no["charlm"] is False
    for c in view_no["candidates"]:
        assert c["charlm"] == "—"


def test_api_form_rejects_non_bool_charlm():
    api = Api(allowed_paths=["u.txt", "a.txt"])
    outcome = api.start_compare(
        {"unknown": "file:u.txt", "candidates": ["file:a.txt"], "charlm": "yes"}
    )
    assert outcome["ok"] is False
    assert {item["code"] for item in outcome["errors"]} == {"bad_input"}
