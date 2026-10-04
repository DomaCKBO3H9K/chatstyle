"""Вымышленные переписки docs/demo/: одинаковая структура на всех языках, экспорт, распознавание."""

import importlib.util
import sys
from pathlib import Path

import pytest
from chatstyle.collectors.tg_export import read_tg_export

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
LANGUAGES = ("ru", "en", "es", "fr", "zh", "ar")
CHATS = ("trip", "work")


def load(name: str):  # noqa: ANN201
    spec = importlib.util.spec_from_file_location(name, DOCS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


demo_eval = load("demo_eval")
make_demo_export = load("make_demo_export")


def rows(chat: str, lang: str) -> list[tuple[str, str]]:
    path = DOCS / "demo" / f"{chat}.{lang}.txt"
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            name, text = line.split("\t")  # ровно одна табуляция: имя и реплика
            result.append((name, text))
    return result


@pytest.mark.parametrize("chat", CHATS)
def test_every_language_has_the_same_structure(chat: str) -> None:
    base = rows(chat, "ru")
    for lang in LANGUAGES:
        translated = rows(chat, lang)
        assert len(translated) == len(base), f"{chat}.{lang}: другое число реплик"
        order_ru: list[str] = []
        order_lang: list[str] = []
        for (name_ru, _), (name, text) in zip(base, translated, strict=True):
            assert text.strip(), f"{chat}.{lang}: пустая реплика"
            order_ru.append(name_ru)
            order_lang.append(name)
        # один и тот же говорящий в каждой строке: имена соответствуют друг другу один к одному
        pairs = set(zip(order_ru, order_lang, strict=True))
        assert len(pairs) == 4
        assert len({a for a, _ in pairs}) == len({b for _, b in pairs}) == 4


def test_the_same_people_take_part_in_both_chats() -> None:
    for lang in LANGUAGES:
        assert {n for n, _ in rows("trip", lang)} == {n for n, _ in rows("work", lang)}


@pytest.mark.parametrize("lang", LANGUAGES)
def test_export_is_readable_and_keeps_the_messages(lang: str, tmp_path: Path) -> None:
    for chat in CHATS:
        path = tmp_path / f"{chat}.json"
        import json

        path.write_text(
            json.dumps(make_demo_export.build_export(chat, lang), ensure_ascii=False),
            encoding="utf-8",
        )
        order = make_demo_export.people_of(lang)
        expected = [text for name, text in rows(chat, lang) if name == order[0]]
        assert list(read_tg_export(path, "user1")) == expected


@pytest.mark.parametrize("lang", LANGUAGES)
def test_authors_are_recognized_across_the_two_chats(lang: str, tmp_path: Path) -> None:
    hits, total = demo_eval.evaluate(lang, tmp_path, lexical=False)
    assert total == 8
    assert hits >= 7, f"{lang}: верно {hits} из {total}"
