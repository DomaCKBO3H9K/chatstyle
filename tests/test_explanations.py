from pathlib import Path

import pytest
from chatstyle import _core
from chatstyle.pipeline import DEFAULT_TOP_FEATURES, run_comparison

FIXTURES = Path(__file__).parent / "fixtures"


def test_compare_detailed_structure_and_order() -> None:
    candidates = {"zeta": ["привет как дела"], "alpha": ["hello world"]}
    result = _core.compare_detailed(["привет как дела"], candidates, 3)
    assert list(result) == ["zeta", "alpha"]
    zeta = result["zeta"]
    assert zeta["similarity"] == pytest.approx(1.0)
    assert len(zeta["features"]) == 3
    first = zeta["features"][0]
    assert set(first) == {"feature", "contribution", "unknown_count", "candidate_count"}
    contributions = [item["contribution"] for item in zeta["features"]]
    assert contributions == sorted(contributions, reverse=True)


def test_compare_detailed_matches_compare() -> None:
    unknown = ["ну привет)) как дела", "щас приду"]
    candidates = {"a": ["ну привет как жизнь))"], "b": ["Good morning"]}
    plain = _core.compare(unknown, candidates)
    detailed = _core.compare_detailed(unknown, candidates, 5)
    for name in candidates:
        assert detailed[name]["similarity"] == plain[name]


def test_features_are_readable() -> None:
    result = _core.compare_detailed(["да нет"], {"a": ["да нет"]}, 100)
    names = [item["feature"] for item in result["a"]["features"]]
    assert "^д" in names  # маркер начала сообщения показан как «^»
    assert "т$" in names  # маркер конца как «$»
    assert "а␣" in names  # пробел как «␣»
    assert all("\x02" not in name and "\x03" not in name and " " not in name for name in names)


def test_default_top_k_is_20_and_zero_gives_no_features() -> None:
    unknown = ["привет как дела у тебя сегодня"]
    default = _core.compare_detailed(unknown, {"a": unknown})
    assert len(default["a"]["features"]) == 20
    assert _core.compare_detailed(unknown, {"a": unknown}, 0)["a"]["features"] == []


def test_pipeline_exposes_top_features(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(FIXTURES)
    result = run_comparison("file:unknown.txt", ["file:other.txt", "file:same.txt"])
    best, worst = result.candidates
    assert best.label == "file:same.txt"
    assert len(best.top_features) == DEFAULT_TOP_FEATURES
    assert len(worst.top_features) == DEFAULT_TOP_FEATURES
    assert best.similarity > worst.similarity
    contributions = [item.contribution for item in best.top_features]
    assert contributions == sorted(contributions, reverse=True)
    assert all(item.unknown_count > 0 and item.candidate_count > 0 for item in best.top_features)
    assert sum(item.contribution for item in best.top_features) <= best.similarity + 1e-9


def test_pipeline_top_features_parameter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(FIXTURES)
    result = run_comparison("file:unknown.txt", ["file:same.txt"], top_features=5)
    assert len(result.candidates[0].top_features) == 5
    none = run_comparison("file:unknown.txt", ["file:same.txt"], top_features=0)
    assert none.candidates[0].top_features == ()
