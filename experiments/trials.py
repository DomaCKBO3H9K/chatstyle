"""Датасет и построение испытаний «один автор / разные авторы».

Датасет — папка с файлами `.txt` (UTF-8, одно сообщение на строку, в хронологическом порядке),
по файлу на автора; имя файла без расширения — анонимный id автора. Тексты в репозиторий не
попадают (папка `data/` в .gitignore).
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from chatstyle.collectors.txt import read_txt
from chatstyle.errors import ChatstyleError
from chatstyle.pipeline import count_words
from chatstyle.preprocess import preprocess

MIN_AUTHORS = 5  # пара авторов и не меньше трёх посторонних для General Impostors
SYNTHETIC_MARKER = "SYNTHETIC"

Segments = dict[str, tuple[list[str], list[str]]]


@dataclass(frozen=True)
class Dataset:
    segments: Segments  # автор -> (кусок «неизвестного», кусок «кандидата»), не пересекаются
    skipped: tuple[str, ...]  # авторы, у которых текста меньше двух кусков
    synthetic: bool  # данные созданы make_synthetic.py: числа нельзя публиковать как результат


@dataclass(frozen=True)
class Trial:
    index: int
    same: bool
    unknown_author: str  # чей кусок A считается неизвестным
    candidate_author: str  # чей кусок B выступает кандидатом
    impostor_authors: tuple[str, ...]  # чьи куски B служат посторонними


def split_segments(messages: Sequence[str], words: int) -> tuple[list[str], list[str]] | None:
    """Два подряд идущих непересекающихся куска сообщений по не меньше `words` слов каждый.

    Возвращает None, если текста не хватает на оба куска.
    """
    ends: list[int] = []
    start = 0
    for _ in range(2):
        total = 0
        position = start
        while position < len(messages) and total < words:
            total += count_words([messages[position]])
            position += 1
        if total < words:
            return None
        ends.append(position)
        start = position
    return list(messages[: ends[0]]), list(messages[ends[0] : ends[1]])


def load_dataset(directory: Path, words: int) -> Dataset:
    """Прочитать датасет и нарезать каждого автора на два куска по `words` слов."""
    if not directory.is_dir():
        raise ChatstyleError(f"Папка датасета не найдена: {directory}")
    files = sorted(
        (p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".txt"),
        key=lambda path: path.name,
    )
    if not files:
        raise ChatstyleError(f"В папке {directory} нет файлов .txt (по файлу на автора).")

    segments: Segments = {}
    skipped: list[str] = []
    for path in files:
        parts = split_segments(preprocess(read_txt(path)), words)
        if parts is None:
            skipped.append(path.stem)
        else:
            segments[path.stem] = parts
    if len(segments) < MIN_AUTHORS:
        raise ChatstyleError(
            f"Нужно не меньше {MIN_AUTHORS} авторов с текстом от {2 * words} слов, найдено "
            f"{len(segments)} (пропущено из-за малого текста: {len(skipped)})."
        )
    return Dataset(
        segments=segments,
        skipped=tuple(skipped),
        synthetic=(directory / SYNTHETIC_MARKER).exists(),
    )


def build_trials(
    authors: Sequence[str], neg_per_pos: int = 1, impostor_count: int = 10, seed: int = 1
) -> list[Trial]:
    """Испытания: на каждого автора одно положительное и `neg_per_pos` отрицательных.

    Положительное: кусок A автора i против куска B того же автора. Отрицательное: A автора i
    против B другого автора j. Посторонние: B-куски авторов, среди которых нет ни i, ни j.
    Результат определяется только списком авторов и seed.
    """
    names = sorted(authors)
    if len(names) < MIN_AUTHORS:
        raise ChatstyleError(f"Для испытаний нужно не меньше {MIN_AUTHORS} авторов.")
    rng = random.Random(seed)
    trials: list[Trial] = []

    def add(same: bool, unknown: str, candidate: str) -> None:
        pool = [name for name in names if name not in (unknown, candidate)]
        chosen = rng.sample(pool, min(impostor_count, len(pool)))
        trials.append(Trial(len(trials), same, unknown, candidate, tuple(sorted(chosen))))

    for author in names:
        add(True, author, author)
        others = [name for name in names if name != author]
        for other in rng.sample(others, min(neg_per_pos, len(others))):
            add(False, author, other)
    return trials
