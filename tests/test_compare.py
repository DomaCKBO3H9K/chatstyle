import pytest
from chatstyle import _core


def test_returns_dict_with_same_keys_in_same_order() -> None:
    candidates = {"zeta": ["привет как дела"], "alpha": ["Good morning everyone"], "mid": ["xyz"]}
    result = _core.compare(["привет как жизнь"], candidates)
    assert isinstance(result, dict)
    assert list(result.keys()) == ["zeta", "alpha", "mid"]


def test_values_are_floats_in_unit_interval() -> None:
    candidates = {"a": ["привет"], "b": ["hello"]}
    result = _core.compare(["привет"], candidates)
    for value in result.values():
        assert isinstance(value, float)
        assert 0.0 <= value <= 1.0


def test_same_author_scores_higher() -> None:
    unknown = ["привет как жизнь"]
    candidates = {
        "same": ["привет как дела", "привет, что делаешь"],
        "other": ["Good morning everyone", "see you later"],
    }
    result = _core.compare(unknown, candidates)
    assert result["same"] > result["other"]


def test_case_insensitive() -> None:
    result = _core.compare(["ПРИВЕТ"], {"a": ["привет"]})
    assert result["a"] == pytest.approx(1.0)


def test_empty_candidates() -> None:
    assert _core.compare(["привет"], {}) == {}


def test_keyword_arguments() -> None:
    result = _core.compare(unknown=["привет"], candidates={"a": ["привет"]})
    assert result["a"] == pytest.approx(1.0)


def test_empty_unknown_gives_zero() -> None:
    result = _core.compare([], {"a": ["привет"]})
    assert list(result.keys()) == ["a"]
    assert result["a"] == pytest.approx(0.0)


def test_non_string_message_raises() -> None:
    with pytest.raises(TypeError):
        _core.compare([1], {"a": ["x"]})
