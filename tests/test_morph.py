import sys

import pytest

# Пропускаем тесты, если pymorphy3 недоступен в окружении CI.
pytest.importorskip("pymorphy3")

from chatstyle import morph
from chatstyle.errors import ChatstyleError


def test_known_words():
    assert morph.word_codes("мама иду красивый") == ["n", "v", "a"]


def test_oov_and_latin_and_hyphen():
    # слово вне словаря
    assert morph.word_codes("ваще") == ["x"]
    # латиница
    assert morph.word_codes("hello world") == ["l", "l"]
    # слово с дефисом считается одним словом → один код
    assert len(morph.word_codes("что-то")) == 1


def test_word_count_and_ignores_punct():
    assert len(morph.word_codes("Привет, как дела? Я иду домой)))")) == 6
    assert morph.word_codes("123 !!! ))") == []


def test_service_tokens_are_ignored():
    assert morph.word_codes("<URL>") == []
    # "смотри" – глагол, проверяем реальный код, оставляем комментарий при отклонении
    codes = morph.word_codes("смотри <URL> <MENTION>")
    assert codes == ["v"], f"Ожидался код глагола, получено {codes}"


def test_tag_and_views():
    tag = morph.tag_message("мама мыла раму")
    assert tag.count(" ") == 2  # ровно 3 кода, 2 пробела
    assert len(tag.split()) == 3

    assert morph.pos_view(["мама", "", "!!!", "иду"]) == ["n", "v"]
    assert morph.compact_view(["мама иду", "!!!"]) == ["nv"]


def test_all_codes_and_constants():
    # проверяем количество кодов
    assert len(morph.ALL_CODES) == 20
    # коды POS_CODES уникальны, однобуквенные и строчные
    pos_vals = list(morph.POS_CODES.values())
    assert len(set(pos_vals)) == len(pos_vals)
    for val in pos_vals:
        assert len(val) == 1 and val.islower()


def test_determinism_and_cache_reset():
    first = morph.tag_message("мама иду")
    second = morph.tag_message("мама иду")
    assert first == second
    # сброс кэша не ломает результат
    morph.reset_cache()
    assert morph.tag_message("мама иду") == first


def test_require_and_available():
    assert morph.available() is True
    # не должно бросать исключение
    morph.require()


def test_without_morphy(monkeypatch):
    # имитируем отсутствие pymorphy3
    monkeypatch.setitem(sys.modules, "pymorphy3", None)
    morph.reset_cache()
    assert morph.available() is False
    with pytest.raises(ChatstyleError) as exc:
        morph.require()
    assert "pip install chatstyle[morph]" in str(exc.value)

    with pytest.raises(ChatstyleError):
        morph.word_codes("мама")
    # восстанавливаем кэш для последующих тестов
    morph.reset_cache()
