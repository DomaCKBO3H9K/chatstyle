from importlib import resources
from pathlib import Path

import pytest
from chatstyle import _core
from chatstyle.features import (
    FEATURE_LABELS,
    FILLER_WORD_PREFIX,
    FUNCTION_WORD_PREFIX,
    style_features,
)
from chatstyle.lexicon import filler_words, function_words, nonstandard_words, parse_word_list
from chatstyle.pipeline import profile_author

FIXTURES = Path(__file__).parent / "fixtures"
FIXED_KEYS = set(FEATURE_LABELS)

# --- словари ---


def test_parse_word_list_skips_comments_and_duplicates() -> None:
    text = "# комментарий\n\nНу\nну\n  Типа  \n#ещё\nкороче\n"
    assert parse_word_list(text) == ["ну", "типа", "короче"]


def test_parse_word_list_rejects_multiword_entries() -> None:
    with pytest.raises(ValueError, match="Строка 2"):
        parse_word_list("ну\nкак бы\n")


@pytest.mark.parametrize("loader", [function_words, filler_words])
def test_bundled_lexicons_are_clean(loader) -> None:  # noqa: ANN001
    words = loader()
    assert len(words) > 20
    assert len(words) == len(set(words))
    assert all(word == word.lower() and not any(c.isspace() for c in word) for word in words)


def test_bundled_lexicons_have_expected_words() -> None:
    assert {"и", "не", "в", "что", "из-за"} <= set(function_words())
    assert {"ну", "короче", "типа"} <= set(filler_words())


def test_lexicons_are_package_resources() -> None:
    root = resources.files("chatstyle").joinpath("resources")
    assert root.joinpath("function_words_ru.txt").is_file()
    assert root.joinpath("filler_words_ru.txt").is_file()


# --- признаки через ядро ---


def test_feature_key_set_is_complete_and_sorted() -> None:
    result = style_features(["Привет))"])
    assert FIXED_KEYS <= set(result)
    expected = (
        len(FIXED_KEYS) + len(function_words()) + len(filler_words()) + len(nonstandard_words())
    )
    assert len(result) == expected
    assert list(result) == sorted(result, key=lambda key: key.encode("utf-8"))


def test_empty_input_is_all_zeros_with_full_key_set() -> None:
    empty = style_features([])
    assert set(empty) == set(style_features(["Привет"]))
    assert set(empty.values()) == {0.0}


def test_known_values() -> None:
    result = style_features(["Привет)) ну как дела...", "Да ёлка и то"])
    assert result["p:paren2"] == pytest.approx(0.5)
    assert result["p:ellipsis"] == pytest.approx(0.5)
    assert result["f:capital_start"] == pytest.approx(1.0)
    assert result["f:yo_ratio"] == pytest.approx(1 / 3)
    assert result["r:avg_chars"] == pytest.approx(17.5)
    assert result["r:avg_words"] == pytest.approx(4.0)
    # слова: привет ну как дела да ёлка и то = 8; «ну» — паразит, «как» и «и», «то» — служебные
    assert result[FILLER_WORD_PREFIX + "ну"] == pytest.approx(1 / 8)
    assert result[FUNCTION_WORD_PREFIX + "и"] == pytest.approx(1 / 8)


def test_preprocessing_tokens_are_ignored() -> None:
    with_tokens = style_features(["<URL> ага", "<MENTION> привет"])
    plain = style_features(["ага", "привет"])
    assert with_tokens == plain
    assert with_tokens["f:latin_share"] == 0.0
    assert with_tokens["f:capital_start"] == 0.0


def test_core_binding_signature() -> None:
    result = _core.style_features(
        messages=["ну привет"],
        function_words=["и"],
        filler_words=["ну"],
        ignored_tokens=[],
    )
    assert result["fl:ну"] == pytest.approx(0.5)
    assert result["fw:и"] == 0.0


def test_style_differs_between_fixture_authors() -> None:
    def load(name: str) -> list[str]:
        return (FIXTURES / name).read_text(encoding="utf-8").splitlines()

    casual = style_features(load("same.txt"))
    formal = style_features(load("other.txt"))
    assert casual["p:paren2"] > formal["p:paren2"]
    assert casual["f:capital_start"] < formal["f:capital_start"]
    assert casual["p:end_dot"] < formal["p:end_dot"]
    assert casual[FILLER_WORD_PREFIX + "ну"] > formal[FILLER_WORD_PREFIX + "ну"]


# --- профиль автора ---


def test_profile_author_uses_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(FIXTURES)
    profile = profile_author("file:same.txt")
    assert profile.label == "file:same.txt"
    assert profile.stats.messages == 19
    assert profile.stats.words > 50
    assert set(profile.features) == set(style_features(["x"]))
