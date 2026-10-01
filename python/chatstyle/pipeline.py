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


@dataclass(frozen=True)
class AuthorStats:
    """Статистика автора: количество слов и сообщений."""

    words: int
    messages: int


@dataclass(frozen=True)
class CandidateResult:
    """Результат для одного кандидата."""

    label: str
    words: int
    messages: int
    similarity: float


@dataclass(frozen=True)
class ComparisonResult:
    """Результат сравнения неизвестного автора с кандидатами."""

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
    scores = _core.compare(unknown_messages, candidate_messages)

    # Формирование результатов
    results: list[CandidateResult] = []
    for spec in candidate_specs:
        msgs = candidate_messages[spec]
        words = count_words(msgs)
        sim = scores[spec]
        results.append(
            CandidateResult(
                label=spec,
                words=words,
                messages=len(msgs),
                similarity=sim,
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
