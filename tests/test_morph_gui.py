import re
from pathlib import Path

import pytest
from chatstyle import morph
from chatstyle.gui.api import Api, compare_view_dict, profile_view_dict
from chatstyle.gui.model import CompareOutcome
from chatstyle.pipeline import profile_author, run_comparison

pytest.importorskip("pymorphy3")

FIXTURES = Path(__file__).parent / "fixtures"
SPECS = ["file:same.txt", "file:other.txt"]


@pytest.fixture(autouse=True)
def fixtures_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(FIXTURES)


def test_morph_available_reports_installation() -> None:
    assert Api().morph_available() is morph.available() is True


def test_compare_view_with_and_without_morph() -> None:
    with_morph = compare_view_dict(
        CompareOutcome(run_comparison("file:unknown.txt", SPECS, morph=True), None)
    )
    assert with_morph["morph"] is True
    for candidate in with_morph["candidates"]:
        assert re.fullmatch(r"\d\.\d{3}", candidate["morph"])

    without = compare_view_dict(CompareOutcome(run_comparison("file:unknown.txt", SPECS), None))
    assert without["morph"] is False
    assert all(candidate["morph"] == "—" for candidate in without["candidates"])


def test_profile_view_morph_sorted_or_none() -> None:
    shares = profile_view_dict(profile_author("file:same.txt", morph=True))["morph"]
    assert shares
    values = [float(item["value"]) for item in shares]
    assert values == sorted(values, reverse=True)
    assert all(set(item) == {"code", "value"} for item in shares)

    assert profile_view_dict(profile_author("file:same.txt"))["morph"] is None


def test_non_bool_morph_is_bad_input() -> None:
    api = Api(allowed_paths=["u.txt", "a.txt"])
    form = {"unknown": "file:u.txt", "candidates": ["file:a.txt"], "morph": "yes"}
    answer = api.start_compare(form)
    assert answer["ok"] is False
    assert {item["code"] for item in answer["errors"]} == {"bad_input"}

    answer = api.start_profile("file:same.txt", "yes")  # type: ignore[arg-type]
    assert answer["ok"] is False
    assert answer["errors"][0]["code"] == "bad_input"
