import pytest
from chatstyle.preprocess import clean_message, preprocess


@pytest.mark.parametrize(
    "text, expected",
    [
        ("смотри https://example.com/a?b=1 круто", "смотри <URL> круто"),
        ("тут http://a.ru.", "тут <URL>."),
        ("(см. https://a.ru/x)", "(см. <URL>)"),
        ("www.example.com/page ага", "<URL> ага"),
    ],
)
def test_urls(text: str, expected: str) -> None:
    assert clean_message(text) == expected


@pytest.mark.parametrize("text", ["конец.Начало example.com", "почта user@mail.ru"])
def test_urls_not_matched(text: str) -> None:
    assert clean_message(text) == text


@pytest.mark.parametrize(
    "text, expected",
    [
        ("привет @ivan_petrov как дела", "привет <MENTION> как дела"),
        ("@ivan, привет", "<MENTION>, привет"),
    ],
)
def test_mentions(text: str, expected: str) -> None:
    assert clean_message(text) == expected


@pytest.mark.parametrize("text", ["@ab", "@привет", "почта user@mail.ru"])
def test_mentions_not_matched(text: str) -> None:
    assert clean_message(text) == text


def test_whitespace_is_collapsed() -> None:
    assert clean_message("  привет \n\n  мир\t") == "привет мир"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("и\u0306", "й"),
        ("е\u0308", "ё"),
    ],
)
def test_nfc_normalization(text: str, expected: str) -> None:
    assert clean_message(text) == expected


def test_invisible_characters_removed() -> None:
    assert clean_message("при\u200bвет") == "привет"


def test_zwj_is_kept() -> None:
    text = "\U0001f468\u200d\U0001f469\u200d\U0001f467"
    assert clean_message(text) == text


def test_lone_surrogate_replaced() -> None:
    assert clean_message("a\ud800b") == "a\ufffdb"


@pytest.mark.parametrize(
    "text",
    [
        "Привет, Ёлка!",
        "привет 😀",
        "))",
        "...",
        "😀",
    ],
)
def test_style_is_preserved(text: str) -> None:
    assert clean_message(text) == text


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "[Фото]",
        "[sticker]",
        "<Media omitted>",
        "https://a.ru",
        "@bob",
        "@bob https://a.ru",
    ],
)
def test_dropped(text: str) -> None:
    assert clean_message(text) == ""


def test_preprocess_drops_and_keeps_order() -> None:
    assert preprocess(["привет", "", "[Фото]", "https://a.ru", "как дела"]) == [
        "привет",
        "как дела",
    ]


def test_preprocess_empty_input() -> None:
    assert preprocess([]) == []


def test_preprocess_accepts_generator() -> None:
    assert preprocess(m for m in ["a b", "  "]) == ["a b"]


def test_preprocess_is_idempotent() -> None:
    x = ["Привет @ivan_petrov https://a.ru.", "))", "[Фото]", "  мир  "]
    assert preprocess(preprocess(x)) == preprocess(x)
