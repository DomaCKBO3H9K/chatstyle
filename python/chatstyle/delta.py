"""Burrows Delta: тонкая обёртка над ядром со словарями из ресурсов."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from chatstyle import _core
from chatstyle.features import ALL_STYLE_GROUPS, style_groups_mask
from chatstyle.lexicon import conjunctions, filler_words, function_words, nonstandard_words
from chatstyle.preprocess import MENTION_TOKEN, URL_TOKEN

DEFAULT_CHUNK_WORDS = 200
DEFAULT_MIN_CHUNKS = 6
DEFAULT_TOP_WORDS = 100
DEFAULT_TOP_DIFFERENCES = 20


@dataclass(frozen=True)
class FeatureDifference:
    """Различие одного признака между неизвестным автором и кандидатом."""

    feature: str  # имя признака ядра: `fw:и`, `p:paren2`, `r:avg_chars` ...
    unknown_value: float
    candidate_value: float
    sigma: float  # разброс признака по кускам текста всех авторов сравнения
    z_difference: float  # (неизвестный - кандидат) / sigma


@dataclass(frozen=True)
class DeltaScore:
    """Burrows Delta для одного кандидата: чем меньше delta, тем ближе стили.

    Если available == False, текста слишком мало для оценки разброса признаков и delta
    не имеет смысла.
    """

    available: bool
    delta: float
    features_used: int
    differences: tuple[FeatureDifference, ...]


def burrows_delta(
    unknown: Sequence[str],
    candidates: Mapping[str, Sequence[str]],
    *,
    chunk_words: int = DEFAULT_CHUNK_WORDS,
    min_chunks: int = DEFAULT_MIN_CHUNKS,
    top_words: int = DEFAULT_TOP_WORDS,
    top_differences: int = DEFAULT_TOP_DIFFERENCES,
    groups: Sequence[str] = ALL_STYLE_GROUPS,
) -> dict[str, DeltaScore]:
    """Delta неизвестного автора с каждым кандидатом по предобработанным сообщениям.

    Разброс признаков оценивается по кускам текста всех авторов сравнения. Результат идёт
    в порядке кандидатов; у каждого `differences` содержит до top_differences признаков
    с наибольшим |z|.
    """
    raw = _core.burrows_delta(
        list(unknown),
        {name: list(texts) for name, texts in candidates.items()},
        function_words(),
        filler_words(),
        [URL_TOKEN, MENTION_TOKEN],
        chunk_words,
        min_chunks,
        top_words,
        top_differences,
        nonstandard_words(),
        conjunctions(),
        style_groups_mask(groups),
    )
    return {
        name: DeltaScore(
            available=report["available"],
            delta=report["delta"],
            features_used=report["features_used"],
            differences=tuple(FeatureDifference(**item) for item in report["differences"]),
        )
        for name, report in raw.items()
    }
