import random
from pathlib import Path

import pytest
from chatstyle import _core
from chatstyle.collectors.impostors import load_impostor_directory
from chatstyle.errors import ChatstyleError
from chatstyle.impostors import DEFAULT_SEED, ImpostorsScore, general_impostors

CASUAL = ["ну", "типа", "короче", "блин", "я", "и", "не", "щас"]
FORMAL = ["что", "для", "при", "также", "однако", "это", "в", "поэтому"]
OTHERS = [
    ["да", "нет", "может", "сегодня", "завтра", "потом"],
    ["работа", "проект", "срок", "отчёт", "задача", "встреча"],
    ["кот", "дом", "лес", "река", "поле", "город"],
    ["книга", "фильм", "музыка", "игра", "спорт", "кино"],
]


def messages(words: list[str], seed: int, ending: str = "", count: int = 60) -> list[str]:
    rng = random.Random(seed)
    return [
        " ".join(rng.choice(words) for _ in range(rng.randint(8, 14))) + ending
        for _ in range(count)
    ]


def impostor_authors() -> dict[str, list[str]]:
    return {f"o{index}.txt": messages(words, index) for index, words in enumerate(OTHERS)}


def run(**kwargs: object) -> dict[str, ImpostorsScore]:
    candidates = {"casual": messages(CASUAL, 2, "))"), "formal": messages(FORMAL, 3, ".")}
    return general_impostors(
        messages(CASUAL, 1, "))"), candidates, impostor_authors(), chunk_words=100, **kwargs
    )


# --- обёртка и привязка ---


def test_same_style_wins_and_different_style_loses() -> None:
    result = run()
    assert list(result) == ["casual", "formal"]
    assert result["casual"].available
    assert result["casual"].score > 0.9
    assert result["formal"].score < 0.2
    assert result["casual"].impostors == 5
    assert result["casual"].iterations == 100


def test_same_seed_gives_same_result_and_default_seed_is_used() -> None:
    assert run(seed=5) == run(seed=5)
    assert run() == run(seed=DEFAULT_SEED)


def test_unavailable_without_enough_impostors() -> None:
    candidates = {"casual": messages(CASUAL, 2), "formal": messages(FORMAL, 3)}
    result = general_impostors(messages(CASUAL, 1), candidates, chunk_words=100)
    for score in result.values():
        assert score == ImpostorsScore(available=False, score=0.0, impostors=1, iterations=0)


def test_min_impostors_is_configurable() -> None:
    candidates = {"casual": messages(CASUAL, 2), "formal": messages(FORMAL, 3)}
    result = general_impostors(
        messages(CASUAL, 1), candidates, chunk_words=100, min_impostors=1, iterations=20
    )
    assert all(score.available for score in result.values())


def test_invalid_parameters_raise_value_error() -> None:
    with pytest.raises(ValueError):
        run(iterations=0)
    with pytest.raises(ValueError):
        run(feature_fraction=0.0)
    with pytest.raises(ValueError):
        run(feature_fraction=1.01)
    with pytest.raises(ValueError):
        general_impostors(["aa"], {"A": ["bb"]}, chunk_words=0)


def test_no_candidates() -> None:
    assert general_impostors(messages(CASUAL, 1), {}, impostor_authors()) == {}


def test_core_binding_accepts_keyword_arguments() -> None:
    result = _core.general_impostors(
        unknown=messages(CASUAL, 1),
        candidates={"c": messages(CASUAL, 2)},
        impostors=list(impostor_authors().values()),
        ignored_tokens=[],
        iterations=10,
        chunk_words=100,
        seed=3,
    )
    assert set(result["c"]) == {"available", "score", "impostors", "iterations"}
    assert result["c"]["iterations"] == 10


# --- загрузчик папки ---


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_directory_is_loaded_sorted_and_preprocessed(tmp_path: Path) -> None:
    write(tmp_path / "b.txt", "привет @ivan_petrov\n\n[Фото]\nкак дела https://a.ru")
    write(tmp_path / "A.txt", "ну ладно")
    write(tmp_path / "C.TXT", "Ага")
    authors = load_impostor_directory(tmp_path)
    assert list(authors) == ["A.txt", "b.txt", "C.TXT"]
    assert authors["b.txt"] == ["привет <MENTION>", "как дела <URL>"]


def test_directory_skips_other_files_subdirs_and_empty_authors(tmp_path: Path) -> None:
    write(tmp_path / "good.txt", "привет")
    write(tmp_path / "notes.md", "не текст")
    write(tmp_path / ".hidden.txt", "скрытый")
    write(tmp_path / "only_media.txt", "[Фото]\nhttps://a.ru")
    (tmp_path / "sub").mkdir()
    write(tmp_path / "sub" / "inner.txt", "вложенный")
    (tmp_path / "dir.txt").mkdir()
    assert list(load_impostor_directory(tmp_path)) == ["good.txt"]


def test_directory_errors(tmp_path: Path) -> None:
    with pytest.raises(ChatstyleError) as exc_info:
        load_impostor_directory(tmp_path / "nope")
    assert "не найдена" in str(exc_info.value)

    with pytest.raises(ChatstyleError) as exc_info:
        load_impostor_directory(tmp_path)
    assert "нет файлов .txt" in str(exc_info.value)

    write(tmp_path / "media.txt", "[Фото]")
    with pytest.raises(ChatstyleError) as exc_info:
        load_impostor_directory(tmp_path)
    assert "не осталось сообщений" in str(exc_info.value)

    (tmp_path / "media.txt").write_bytes("привет".encode("cp1251"))
    with pytest.raises(ChatstyleError) as exc_info:
        load_impostor_directory(tmp_path)
    assert "UTF-8" in str(exc_info.value)


def test_directory_authors_work_as_impostors(tmp_path: Path) -> None:
    for index, words in enumerate(OTHERS):
        write(tmp_path / f"o{index}.txt", "\n".join(messages(words, index)))
    authors = load_impostor_directory(tmp_path)
    result = general_impostors(
        messages(CASUAL, 1), {"casual": messages(CASUAL, 2)}, authors, chunk_words=100
    )
    assert result["casual"].available
    assert result["casual"].impostors == 4
