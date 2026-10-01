"""Модуль пайплайна сравнения авторства.

Содержит функции для подсчёта слов и запуска сравнения.
Не использует typer, rich, print.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from chatstyle import _core
from chatstyle.collectors import CollectOptions, collect
from chatstyle.errors import ChatstyleError
from chatstyle.features import style_features
from chatstyle.preprocess import MENTION_TOKEN, URL_TOKEN, preprocess

MIN_WORDS: int = 1000
# Сколько общих n-грамм хранится на кандидата: отчёт скрывает тривиальные и берёт из них 20
DEFAULT_TOP_FEATURES: int = 100
DISCLAIMER: str = "Результат — статистическая оценка сходства стиля, а не доказательство авторства."


@dataclass(frozen=True)
class AuthorStats:
    """Статистика автора: количество слов и сообщений."""

    words: int
    messages: int


@dataclass(frozen=True)
class SharedFeature:
    """Общая n-грамма, давшая вклад в сходство."""

    feature: str  # читаемый вид: пробел «␣», начало сообщения «^», конец «$»
    contribution: float  # вклад в косинус; сумма вкладов по всем общим n-граммам = сходство
    unknown_count: float
    candidate_count: float


@dataclass(frozen=True)
class CandidateResult:
    """Результат для одного кандидата."""

    label: str
    words: int
    messages: int
    similarity: float
    top_features: tuple[SharedFeature, ...] = ()


@dataclass(frozen=True)
class ComparisonResult:
    """Результат сравнения неизвестного автора с кандидатами."""

    unknown_label: str
    unknown: AuthorStats
    candidates: tuple[CandidateResult, ...]


def count_words(messages: Sequence[str]) -> int:
    """Суммарное число слов во всех сообщениях.

    Слово — совпадение ``re.findall(r"\\w+", текст)`` после удаления
    из текста подстрок URL_TOKEN и MENTION_TOKEN.
    """
    total = 0
    for msg in messages:
        # Удаляем токены, которые не должны считаться словами
        cleaned = msg.replace(URL_TOKEN, "").replace(MENTION_TOKEN, "")
        words = re.findall(r"\w+", cleaned)
        total += len(words)
    return total


def low_volume_sides(result: ComparisonResult) -> list[tuple[str | None, int]]:
    """Стороны с объёмом меньше MIN_WORDS: (подпись кандидата или None для неизвестного, слов)."""
    sides: list[tuple[str | None, int]] = []
    if result.unknown.words < MIN_WORDS:
        sides.append((None, result.unknown.words))
    for candidate in result.candidates:
        if candidate.words < MIN_WORDS:
            sides.append((candidate.label, candidate.words))
    return sides


def low_volume_warning(result: ComparisonResult) -> str | None:
    """Предупреждение о малом объёме текста у любой из сторон или None, если текста хватает."""
    sides = low_volume_sides(result)
    if not sides:
        return None
    parts = [
        f"{'неизвестный автор' if label is None else label} — {words}" for label, words in sides
    ]
    return (
        f"Внимание: мало текста (меньше {MIN_WORDS} слов): "
        + "; ".join(parts)
        + ". Оценка может быть ненадёжной."
    )


def _load_messages(spec: str, options: CollectOptions | None) -> list[str]:
    """Собрать и предобработать сообщения источника; пустой результат — ошибка."""
    messages = preprocess(collect(spec, options))
    if not messages:
        raise ChatstyleError(f"В источнике {spec} не осталось сообщений после предобработки.")
    return messages


def run_comparison(
    unknown_spec: str,
    candidate_specs: Sequence[str],
    options: CollectOptions | None = None,
    top_features: int = DEFAULT_TOP_FEATURES,
) -> ComparisonResult:
    """Запустить полный цикл сравнения.

    Параметры
    ---------
    unknown_spec : str
        Спецификация источника неизвестного автора.
    candidate_specs : Sequence[str]
        Спецификации источников кандидатов.
    options : CollectOptions | None
        Параметры сбора (лимит, обновление кэша, уведомления) для источников tg:.
    top_features : int
        Сколько общих n-грамм с наибольшим вкладом сохранить для каждого кандидата.

    Возвращает
    ----------
    ComparisonResult
        Результат сравнения.

    Исключения
    ----------
    ChatstyleError
        Если нет кандидатов, есть повторы, или источник пуст.
    """
    if not candidate_specs:
        raise ChatstyleError("Укажите хотя бы одного кандидата.")

    seen: set[str] = set()
    for spec in candidate_specs:
        if spec in seen:
            raise ChatstyleError(f"Кандидат указан дважды: {spec}")
        seen.add(spec)

    unknown_messages = _load_messages(unknown_spec, options)
    candidate_messages = {spec: _load_messages(spec, options) for spec in candidate_specs}

    # Вычисление сходства через ядро
    reports = _core.compare_detailed(unknown_messages, candidate_messages, top_features)

    # Формирование результатов
    results: list[CandidateResult] = []
    for spec in candidate_specs:
        msgs = candidate_messages[spec]
        words = count_words(msgs)
        report = reports[spec]
        results.append(
            CandidateResult(
                label=spec,
                words=words,
                messages=len(msgs),
                similarity=report["similarity"],
                top_features=tuple(SharedFeature(**item) for item in report["features"]),
            )
        )

    # Сортировка по убыванию similarity (стабильная)
    results.sort(key=lambda r: -r.similarity)

    unknown_words = count_words(unknown_messages)
    unknown_stats = AuthorStats(
        words=unknown_words,
        messages=len(unknown_messages),
    )

    return ComparisonResult(
        unknown_label=unknown_spec,
        unknown=unknown_stats,
        candidates=tuple(results),
    )


@dataclass(frozen=True)
class AuthorProfile:
    """Профиль стиля одного автора."""

    label: str
    stats: AuthorStats
    features: dict[str, float]


def profile_author(spec: str, options: CollectOptions | None = None) -> AuthorProfile:
    """Собрать сообщения автора и посчитать его стилевые признаки."""
    messages = _load_messages(spec, options)
    return AuthorProfile(
        label=spec,
        stats=AuthorStats(words=count_words(messages), messages=len(messages)),
        features=style_features(messages),
    )
