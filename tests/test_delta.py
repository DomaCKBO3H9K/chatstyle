import random
from pathlib import Path

import pytest
from chatstyle import _core
from chatstyle.delta import DeltaScore, FeatureDifference, burrows_delta
from chatstyle.features import FEATURE_LABELS

FIXTURES = Path(__file__).parent / "fixtures"

CASUAL = ["ну", "типа", "короче", "блин", "я", "и", "не", "щас"]
FORMAL = ["что", "для", "при", "также", "однако", "это", "в", "поэтому"]


def casual_messages(seed: int, count: int = 60) -> list[str]:
    rng = random.Random(seed)
    messages = []
    for _ in range(count):
        text = " ".join(rng.choice(CASUAL) for _ in range(rng.randint(8, 14)))
        messages.append(text + ("))" if rng.random() < 0.6 else ""))
    return messages


def formal_messages(seed: int, count: int = 60) -> list[str]:
    rng = random.Random(seed)
    messages = []
    for _ in range(count):
        words = [rng.choice(FORMAL) for _ in range(rng.randint(8, 14))]
        words[0] = words[0].capitalize()
        messages.append(" ".join(words) + ".")
    return messages


def test_hand_computed_example_through_wrapper() -> None:
    # меняется только r:avg_chars: значения по кускам 2,2,2,4,4,4,2,3,3
    candidates = {"A": ["aaaa"] * 3, "B": ["aa", "aaa", "aaa"]}
    # группы привычек выключены: иначе разброс дают и другие признаки
    result = burrows_delta(["aa"] * 3, candidates, chunk_words=1, groups=())
    assert list(result) == ["A", "B"]
    assert result["A"].available
    assert result["A"].delta == pytest.approx(2.155263624321299)
    assert result["B"].delta == pytest.approx(0.7184212081070994)
    assert result["A"].features_used == 1
    (difference,) = result["A"].differences
    assert difference == FeatureDifference(
        feature="r:avg_chars",
        unknown_value=2.0,
        candidate_value=4.0,
        sigma=pytest.approx(0.927960727138337),
        z_difference=pytest.approx(-2.155263624321299),
    )


def test_core_binding_accepts_keyword_arguments() -> None:
    result = _core.burrows_delta(
        unknown=["aa"] * 3,
        candidates={"A": ["aaaa"] * 3},
        function_words=[],
        filler_words=[],
        ignored_tokens=[],
        chunk_words=1,
        min_chunks=2,
    )
    assert result["A"]["available"] is True
    assert set(result["A"]["differences"][0]) == {
        "feature",
        "unknown_value",
        "candidate_value",
        "sigma",
        "z_difference",
    }


def test_same_style_is_closer_than_different_style() -> None:
    candidates = {"casual": casual_messages(2), "formal": formal_messages(3)}
    result = burrows_delta(casual_messages(1), candidates, chunk_words=50)
    assert all(score.available for score in result.values())
    assert result["casual"].delta < result["formal"].delta
    assert result["formal"].delta > 2 * result["casual"].delta


def test_differences_are_sorted_limited_and_named() -> None:
    result = burrows_delta(
        casual_messages(1), {"formal": formal_messages(3)}, chunk_words=50, top_differences=5
    )
    differences = result["formal"].differences
    assert len(differences) == 5
    values = [abs(item.z_difference) for item in differences]
    assert values == sorted(values, reverse=True)
    # самое заметное различие стилей — в признаках стиля
    assert differences[0].feature in FEATURE_LABELS or differences[0].feature[:3] in {"fw:", "fl:"}
    assert result["formal"].features_used > 5


def test_unavailable_on_small_fixtures(monkeypatch: pytest.MonkeyPatch) -> None:
    def load(name: str) -> list[str]:
        return (FIXTURES / name).read_text(encoding="utf-8").splitlines()

    result = burrows_delta(
        load("unknown.txt"), {"same": load("same.txt"), "other": load("other.txt")}
    )
    assert set(result) == {"same", "other"}
    for score in result.values():
        assert score == DeltaScore(available=False, delta=0.0, features_used=0, differences=())


def test_empty_candidates_and_invalid_chunk_size() -> None:
    assert burrows_delta(["aa"], {}) == {}
    with pytest.raises(ValueError):
        burrows_delta(["aa"], {"A": ["bb"]}, chunk_words=0)


def test_result_is_deterministic() -> None:
    candidates = {"casual": casual_messages(2), "formal": formal_messages(3)}
    first = burrows_delta(casual_messages(1), candidates, chunk_words=50)
    second = burrows_delta(casual_messages(1), candidates, chunk_words=50)
    assert first == second
