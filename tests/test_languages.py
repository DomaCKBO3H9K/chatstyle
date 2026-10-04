"""Поддержка не русских языков: слова, регистр, признаки и распознавание авторов на синтетике."""

import random
from pathlib import Path

import pytest
from chatstyle import _core
from chatstyle.pipeline import count_words, profile_author, run_comparison
from chatstyle.wordgrams import words_of

# (свои слова автора A, слова автора B, окончание сообщений A и B)
SPACED = {
    "английский": (
        ["well", "like", "actually", "just", "so", "yeah", "gonna", "kinda"],
        ["therefore", "however", "moreover", "indeed", "thus", "hence", "whereas", "albeit"],
    ),
    "французский": (
        ["bah", "ouais", "genre", "quoi", "franchement", "carrément", "voilà", "ptdr"],
        ["cependant", "toutefois", "ainsi", "donc", "pourtant", "néanmoins", "également", "à"],
    ),
    "немецкий": (
        ["na", "halt", "eben", "mal", "ja", "doch", "ganz", "schon"],
        ["jedoch", "daher", "somit", "außerdem", "dennoch", "folglich", "überdies", "ferner"],
    ),
    "испанский": (
        ["pues", "bueno", "vale", "oye", "tío", "claro", "venga", "ostras"],
        ["además", "aún", "también", "según", "después", "común", "así", "mientras"],
    ),
    "греческий": (
        ["λοιπόν", "δηλαδή", "εντάξει", "ναι", "όχι", "ίσως", "μάλλον", "βέβαια"],
        ["ωστόσο", "επομένως", "επιπλέον", "συνεπώς", "όμως", "ούτε", "εντούτοις", "άρα"],
    ),
    "арабский": (
        ["يعني", "طيب", "والله", "بس", "خلاص", "ايوه", "يلا", "معليش"],
        ["لذلك", "ومع", "ذلك", "بالإضافة", "وبالتالي", "علاوة", "ولكن", "بينما"],
    ),
    "польский": (
        ["no", "wiesz", "czaisz", "tak", "ogólnie", "serio", "dobra", "ej"],
        ["jednakże", "dlatego", "ponadto", "natomiast", "zatem", "mimo", "więc", "żeby"],
    ),
}
# языки без пробелов: наборы знаков
UNSPACED = {
    "китайский": ("我你他好吗呢啊哈嘛啦", "因此然而所以但是虽然尽管既然"),
    "японский": ("あいうえおかきくけこ", "アイウエオカキクケコ"),
}


def spaced_lines(words: list[str], seed: int, ending: str, count: int = 70) -> list[str]:
    rng = random.Random(seed)
    return [
        " ".join(rng.choice(words) for _ in range(rng.randint(8, 14))) + ending
        for _ in range(count)
    ]


def unspaced_lines(chars: str, seed: int, ending: str, count: int = 70) -> list[str]:
    rng = random.Random(seed)
    return [
        "".join(rng.choice(chars) for _ in range(rng.randint(8, 14))) + ending for _ in range(count)
    ]


def write(path: Path, lines: list[str]) -> str:
    path.write_text("\n".join(lines), encoding="utf-8")
    return f"file:{path}"


def test_words_of_keeps_accents_hyphens_and_splits_ideographs() -> None:
    assert words_of("Été à Paris, что-то") == ["été", "à", "paris", "что-то"]
    assert words_of("我喜欢猫") == ["我", "喜", "欢", "猫"]
    assert words_of("ありがとう ございます hello-world") == [
        *"ありがとう",
        *"ございます",
        "hello-world",
    ]
    assert words_of("hello мир 中文") == ["hello", "мир", "中", "文"]
    assert words_of("") == []


def test_count_words_treats_each_ideograph_as_a_word() -> None:
    assert count_words(["Été à Paris"]) == 3
    assert count_words(["我喜欢猫"]) == 4
    assert count_words(["ありがとう ございます"]) == 10
    assert count_words(["hello мир 中文 42"]) == 5  # hello, мир, 中, 文, 42
    assert count_words(["<URL> раз <MENTION>"]) == 1


@pytest.mark.parametrize(
    ("upper", "lower"),
    [
        ("ÉTÉ ÜBER ÑANDÚ ŁÓDŹ", "été über ñandú łódź"),
        ("ΣΟΦΙΑ ΩΜΕΓΑ", "σοφια ωμεγα"),
        ("ԱՐՄԵՆԻԱ", "արմենիա"),
        ("ГРУЗІЯ ҐАНОК", "грузія ґанок"),
        ("ǄEMO", "ǆemo"),
    ],
)
def test_case_folding_for_n_grams_in_many_alphabets(upper: str, lower: str) -> None:
    report = _core.compare_detailed([upper], {"x": [lower]}, 0)
    assert report["x"]["similarity"] == pytest.approx(1.0)


def test_profile_of_accented_and_greek_text(tmp_path: Path) -> None:
    french = write(tmp_path / "fr.txt", ["Le café est déjà prêt", "Où est l'été ?"] * 10)
    greek = write(tmp_path / "el.txt", ["Ελληνικά κείμενα εδώ", "Και πάλι ελληνικά"] * 10)
    mixed = write(tmp_path / "ru.txt", ["привет hello мир", "как дела hello"] * 10)
    assert profile_author(french).features["f:latin_share"] == pytest.approx(1.0)
    assert profile_author(greek).features["f:latin_share"] == pytest.approx(0.0)
    assert 0.0 < profile_author(mixed).features["f:latin_share"] < 1.0
    # слова с диакритикой не рвутся: средняя длина сообщения в словах — 5 и 4
    assert profile_author(french).features["r:avg_words"] == pytest.approx(4.5)


@pytest.mark.parametrize("lexical", [False, True])
@pytest.mark.parametrize("language", sorted(SPACED))
def test_authors_are_recognized_in_spaced_languages(
    tmp_path: Path, language: str, lexical: bool
) -> None:
    words_a, words_b = SPACED[language]
    unknown = write(tmp_path / "u.txt", spaced_lines(words_a, 1, "!!"))
    same = write(tmp_path / "s.txt", spaced_lines(words_a, 2, "!!"))
    other = write(tmp_path / "o.txt", spaced_lines(words_b, 3, "."))
    result = run_comparison(unknown, [other, same], lexical=lexical)
    assert result.candidates[0].label == same, language
    assert result.candidates[0].similarity > result.candidates[1].similarity


@pytest.mark.parametrize("lexical", [False, True])
@pytest.mark.parametrize("language", sorted(UNSPACED))
def test_authors_are_recognized_without_spaces(
    tmp_path: Path, language: str, lexical: bool
) -> None:
    chars_a, chars_b = UNSPACED[language]
    unknown = write(tmp_path / "u.txt", unspaced_lines(chars_a, 1, "。"))
    same = write(tmp_path / "s.txt", unspaced_lines(chars_a, 2, "。"))
    other = write(tmp_path / "o.txt", unspaced_lines(chars_b, 3, "！"))
    result = run_comparison(unknown, [other, same], lexical=lexical)
    assert result.candidates[0].label == same, language
    assert result.candidates[0].similarity > result.candidates[1].similarity


def test_volume_warning_counts_ideographs_as_words(tmp_path: Path) -> None:
    short = write(tmp_path / "short.txt", unspaced_lines(UNSPACED["китайский"][0], 1, "。", 20))
    longer = write(tmp_path / "long.txt", unspaced_lines(UNSPACED["китайский"][0], 2, "。", 200))
    result = run_comparison(short, [longer, short])
    assert result.unknown.words > 150  # иероглифы считаются по одному, а не «одно слово на строку»
