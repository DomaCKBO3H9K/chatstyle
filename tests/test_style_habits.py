"""Тесты для стилевых признаков, словарей, groups, pipeline и CLI."""

import math
import random
from pathlib import Path

import pytest
from chatstyle import delta, errors, features, lexicon, pipeline
from chatstyle.cli import app
from test_delta import casual_messages, formal_messages
from typer.testing import CliRunner

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def invoke(args: list[str], env: dict[str, str] | None = None) -> pytest.CaptureFixture:
    """Запустить CLI с заданными аргументами."""
    return runner.invoke(app, args, env=env or {"COLUMNS": "200"})


@pytest.fixture
def fixtures_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Сменить рабочую папку на fixtures."""
    monkeypatch.chdir(FIXTURES)


def test_nonstandard_words() -> None:
    """Словарь nonstandard_words: чистота, объём, ключевые слова, наличие файла."""
    from importlib import resources

    words = lexicon.nonstandard_words()
    assert len(words) >= 60
    assert len(words) == len(set(words))
    assert all(w == w.lower() and not any(c.isspace() for c in w) for w in words)
    assert "щас" in words
    assert "ваще" in words
    assert "чо" in words
    assert resources.files("chatstyle").joinpath("resources", "nonstandard_ru.txt").is_file()


def test_conjunctions() -> None:
    """Словарь conjunctions: чистота, объём, ключевые слова, наличие файла."""
    from importlib import resources

    words = lexicon.conjunctions()
    assert len(words) >= 15
    assert len(words) == len(set(words))
    assert all(w == w.lower() and not any(c.isspace() for c in w) for w in words)
    assert "что" in words
    assert "но" in words
    assert "если" in words
    assert "когда" in words
    assert resources.files("chatstyle").joinpath("resources", "conjunctions_ru.txt").is_file()


def test_style_group_bits_and_mask() -> None:
    """STYLE_GROUP_BITS, ALL_STYLE_GROUPS, style_groups_mask."""
    assert features.STYLE_GROUP_BITS == {
        "punctuation": 1,
        "orthography": 2,
        "words": 4,
        "sentences": 8,
    }
    assert features.ALL_STYLE_GROUPS == ("punctuation", "orthography", "words", "sentences")
    assert features.style_groups_mask(("punctuation", "words")) == 5
    assert features.style_groups_mask(()) == 0
    with pytest.raises(errors.ChatstyleError, match="Неизвестная группа"):
        features.style_groups_mask(("foo",))


def test_parse_style_groups() -> None:
    """parse_style_groups: все варианты ввода и ошибки."""
    assert features.parse_style_groups("all") == features.ALL_STYLE_GROUPS
    assert features.parse_style_groups("") == features.ALL_STYLE_GROUPS
    assert features.parse_style_groups("  ALL ") == features.ALL_STYLE_GROUPS
    assert features.parse_style_groups("none") == ()
    assert features.parse_style_groups("words, punctuation") == ("punctuation", "words")
    with pytest.raises(errors.ChatstyleError):
        features.parse_style_groups("foo")
    with pytest.raises(errors.ChatstyleError):
        features.parse_style_groups("words,foo")


def test_key_sets_by_groups() -> None:
    """Наборы ключей по группам признаков."""
    base = set(features.style_features(["Привет))"], groups=()))
    fw = lexicon.function_words()
    fl = lexicon.filler_words()
    assert len(base) == 15 + len(fw) + len(fl)

    punct = set(features.style_features(["Привет))"], groups=("punctuation",))) - base
    assert punct == {
        "p:comma_per_word",
        "p:comma_before_conj",
        "p:no_space_after_comma",
        "p:space_before_punct",
        "p:dash",
        "p:guillemets",
        "p:end_none",
    }

    ortho = set(features.style_features(["Привет))"], groups=("orthography",))) - base
    expected_ortho = {
        "f:caps_words",
        "f:capital_after_dot",
        "o:repeat_letters",
        "o:tsya_share",
        "o:mixed_script",
        "o:double_space",
        "o:nonstandard",
    }
    expected_ortho |= {"ms:" + w for w in lexicon.nonstandard_words()}
    assert ortho == expected_ortho

    words = set(features.style_features(["Привет))"], groups=("words",))) - base
    assert words == {"w:mattr", "w:avg_word_len", "w:long_words", "w:short_words"}

    sent = set(features.style_features(["Привет))"], groups=("sentences",))) - base
    assert sent == {
        "s:avg_sentence_words",
        "s:per_message",
        "s:short_share",
        "s:long_share",
        "s:multi_share",
    }

    base15 = {k for k in base if not k.startswith("fw:") and not k.startswith("fl:")}
    all_groups_keys = set(features.style_features(["Привет))"]))
    expected_labels = base15 | punct | ortho | words | sent
    expected_labels = {k for k in expected_labels if not k.startswith("ms:")}
    assert set(features.FEATURE_LABELS) == expected_labels
    assert set(features.FEATURE_LABELS) <= set(all_groups_keys)


def test_feature_sections() -> None:
    """Разделы профиля и метки признаков."""
    assert set(features.FEATURE_SECTIONS) == {
        "punctuation",
        "writing",
        "words",
        "sentences",
        "message",
    }
    assert features.feature_section("p:comma_per_word") == "punctuation"
    assert features.feature_section("f:capital_start") == "writing"
    assert features.feature_section("o:repeat_letters") == "writing"
    assert features.feature_section("w:mattr") == "words"
    assert features.feature_section("s:per_message") == "sentences"
    assert features.feature_section("r:avg_chars") == "message"
    for key in features.FEATURE_LABELS:
        section = features.feature_section(key)
        assert section in features.FEATURE_SECTIONS
    labels = list(features.FEATURE_LABELS.values())
    assert all(label.strip() for label in labels)
    assert len(labels) == len(set(labels))


def test_describe_feature() -> None:
    """describe_feature: ms:, известный, неизвестный."""
    assert features.describe_feature("ms:щас") == "нестандартное написание «щас»"
    assert (
        features.describe_feature("o:repeat_letters") == features.FEATURE_LABELS["o:repeat_letters"]
    )
    assert features.describe_feature("неизвестный") == "неизвестный"


def test_word_list_lines() -> None:
    """word_list_lines: третья строка с нестандартными словами."""
    f = features.style_features(["щас приду", "ваще норм"])
    lines = features.word_list_lines(f, 5)
    assert len(lines) == 3
    assert lines[2].startswith("Частые нестандартные написания: ")
    assert "щас" in lines[2]
    assert "ваще" in lines[2]

    f2 = features.style_features(["привет мир"])
    lines2 = features.word_list_lines(f2, 5)
    assert lines2[2] == "Частые нестандартные написания: нет"


def test_live_text_values() -> None:
    """Проверка конкретных значений на живом тексте."""
    f = features.style_features(
        [
            "Привет, как дела? Я думаю, что всё ок",
            "Щас приду, но не ждите",
        ]
    )
    assert f["p:comma_before_conj"] == 1.0
    assert f["ms:щас"] > 0
    assert f["p:comma_per_word"] > 0
    assert f["s:per_message"] > 1.0
    for value in f.values():
        assert isinstance(value, float)
        assert math.isfinite(value)


def test_style_habits_visible() -> None:
    """Привычки двух авторов очевидно различаются."""
    rng = random.Random(42)

    a_messages = []
    for _ in range(60):
        words = [
            rng.choice(["приветттт", "как", "дела", "ваще", "норм", "щас"])
            for _ in range(rng.randint(4, 8))
        ]
        msg = " ".join(words)
        if rng.random() < 0.3:
            msg = msg.replace(" ", "  ", 1)
        if rng.random() < 0.4:
            msg += "))"
        a_messages.append(msg)

    b_messages = []
    formal_phrases = [
        "Здравствуйте, как у вас дела? Надеюсь, что всё хорошо.",
        "Я думаю, что мы должны обсудить этот вопрос.",
        "Когда вы сможете при Coming? Нам нужно поговорить.",
        "Пожалуйста, ответьте на моё письмо.",
        "Это очень важно, не правда ли?",
    ]
    for _ in range(60):
        b_messages.append(rng.choice(formal_phrases))

    f_a = features.style_features(a_messages)
    f_b = features.style_features(b_messages)

    assert f_a["o:repeat_letters"] > f_b["o:repeat_letters"]
    assert f_a["o:double_space"] > f_b["o:double_space"]
    assert f_a["o:nonstandard"] > f_b["o:nonstandard"]
    assert f_b["p:comma_per_word"] > f_a["p:comma_per_word"]
    assert f_b["s:per_message"] > f_a["s:per_message"]
    assert f_b["f:capital_start"] > f_a["f:capital_start"]


def test_delta_with_groups() -> None:
    """Burrows Delta с группами и без: features_used различается."""
    unknown = casual_messages(1)
    candidates = {"casual": casual_messages(2), "formal": formal_messages(3)}
    r_all = delta.burrows_delta(unknown, candidates, chunk_words=20, min_chunks=2)
    r_none = delta.burrows_delta(unknown, candidates, chunk_words=20, min_chunks=2, groups=())
    assert r_all["casual"].available
    assert r_none["casual"].available
    assert r_all["casual"].features_used > r_none["casual"].features_used

    with pytest.raises(errors.ChatstyleError):
        delta.burrows_delta(unknown, candidates, chunk_words=20, min_chunks=2, groups=("foo",))


def test_pipeline_compare_messages() -> None:
    """pipeline.compare_messages: пустые группы дают меньше признаков."""
    unknown = casual_messages(1, count=600)
    candidates = {
        "casual": casual_messages(2, count=600),
        "formal": formal_messages(3, count=600),
    }
    default_rows, _ = pipeline.compare_messages(unknown, candidates)
    empty_rows, _ = pipeline.compare_messages(unknown, candidates, style_groups=())
    default_delta = {row.label: row.delta for row in default_rows}["casual"]
    empty_delta = {row.label: row.delta for row in empty_rows}["casual"]
    assert default_delta is not None and empty_delta is not None
    assert default_delta.available and empty_delta.available
    assert default_delta.features_used > empty_delta.features_used


def test_cli_compare_style_groups(fixtures_cwd: None) -> None:
    """CLI compare с разными --style-groups."""
    base_args = [
        "compare",
        "-u",
        "file:unknown.txt",
        "-c",
        "file:same.txt",
        "-c",
        "file:other.txt",
    ]

    result = invoke([*base_args, "--style-groups", "none"])
    assert result.exit_code == 0

    result = invoke([*base_args, "--style-groups", "words,punctuation"])
    assert result.exit_code == 0

    result = invoke([*base_args, "--style-groups", "foo"])
    assert result.exit_code == 2
    assert "Неизвестная группа" in result.output


def test_cli_features_sections(fixtures_cwd: None) -> None:
    """CLI features: заголовки разделов и строка с нестандартными словами."""
    result = invoke(["features", "file:same.txt"])
    assert result.exit_code == 0
    output = result.output
    for header in [
        "Пунктуация",
        "Регистр и орфография",
        "Слова",
        "Предложения",
        "Сообщения",
    ]:
        assert header in output
    assert "Частые нестандартные написания:" in output
