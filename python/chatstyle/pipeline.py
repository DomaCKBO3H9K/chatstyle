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

    # Сбор и предобработка неизвестного автора
    unknown_raw = collect(unknown_spec, options)
    unknown_messages = preprocess(unknown_raw)
    if not unknown_messages:
        raise ChatstyleError(
            f"В источнике {unknown_spec} не осталось сообщений после предобработки."
        )

    # Сбор и предобработка кандидатов
    candidate_messages: dict[str, list[str]] = {}
    for spec in candidate_specs:
        raw = collect(spec, options)
        msgs = preprocess(raw)
        if not msgs:
            raise ChatstyleError(f"В источнике {spec} не осталось сообщений после предобработки.")
        candidate_messages[spec] = msgs

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
