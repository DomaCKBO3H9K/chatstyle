"""Смесь методов: равновесная сумма z-оценок четырёх сигналов стиля.

Сигналы: языковая модель символов, пословные n-граммы, «каркас» служебных слов и Delta.
Веса равные намеренно: на реальных чатах подобранные веса не оказались лучше равных, а
равные нечем подгонять. Объём текста у кандидатов выравнивается (случайные сообщения до
`DEFAULT_CAP_WORDS` слов, но не меньше самого короткого кандидата): иначе самый большой
кандидат выигрывает просто размером словаря.
"""

from __future__ import annotations

import hashlib
import random
import re
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence

from chatstyle import _core
from chatstyle.timeline import Messages
from chatstyle.wordgrams import words_of

DEFAULT_CAP_WORDS = 2500
SKELETON_WORDS = 300  # сколько самых частых слов (по всем авторам сравнения) остаются «каркасом»
MASKED_WORDS = 150  # столько самых частых слов остаются в тексте для замаскированной модели
_TOKEN = re.compile(r"[^\W\d_]+|\d+|[^\w\s]|\s", re.UNICODE)
_BLANK = chr(0xF0000)  # любое слово вне «каркаса»
_FIRST_CODE = 0xF0001


def _words(message: str) -> int:
    return len(words_of(message))


def cap_messages(messages: Sequence[str], cap_words: int, seed: str) -> Messages:
    """Случайные сообщения до `cap_words` слов; порядок и моменты времени сохраняются.

    Выбор детерминирован (зависит только от `seed`), поэтому результат повторяем.
    """
    times = getattr(messages, "times", None)
    order = list(range(len(messages)))
    random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)).shuffle(order)
    taken: list[int] = []
    total = 0
    for index in order:
        if total >= cap_words:
            break
        taken.append(index)
        total += _words(messages[index])
    taken.sort()
    return Messages(
        [messages[i] for i in taken],
        [times[i] for i in taken] if times is not None else None,
    )


def balanced_candidates(
    candidates: Mapping[str, Sequence[str]], cap_words: int = DEFAULT_CAP_WORDS
) -> dict[str, Messages]:
    """Кандидаты одного размера: не больше `max(cap_words, самый короткий кандидат)` слов."""
    sizes = {label: sum(_words(m) for m in messages) for label, messages in candidates.items()}
    limit = max(cap_words, min(sizes.values(), default=0))
    return {label: cap_messages(messages, limit, label) for label, messages in candidates.items()}


def skeleton_cosine(
    unknown: Sequence[str],
    candidates: Mapping[str, Sequence[str]],
    keep_words: int = SKELETON_WORDS,
) -> dict[str, float]:
    """Косинус по n-граммам «каркаса»: частые слова остаются, остальные заменены пустышкой.

    Так сравнивается то, как автор строит фразу служебными словами, а не о чём он пишет.
    Слова заменяются символами, дальше считает ядро (n-граммы 1-4).
    """
    counts: Counter[str] = Counter()
    for messages in (unknown, *candidates.values()):
        for message in messages:
            counts.update(words_of(message))
    codes = {
        word: chr(_FIRST_CODE + i) for i, (word, _) in enumerate(counts.most_common(keep_words))
    }

    def encode(messages: Sequence[str]) -> list[str]:
        views = ("".join(codes.get(w, _BLANK) for w in words_of(m)) for m in messages)
        return [view for view in views if view]

    unknown_view = encode(unknown)
    views = {label: encode(messages) for label, messages in candidates.items()}
    views = {label: view for label, view in views.items() if view}
    if not unknown_view or not views:
        return {}
    reports = _core.compare_detailed(unknown_view, views, 0)
    return {label: report["similarity"] for label, report in reports.items()}


def mask_rare_words(messages: Sequence[str], keep: set[str]) -> list[str]:
    """Text distortion: слова вне `keep` — звёздочки той же длины, цифры — «#», знаки остаются.

    Остаётся то, как автор строит текст (частые слова, знаки, длины слов, регистр потерян), а
    тема и имена исчезают.
    """
    masked: list[str] = []
    for message in messages:
        parts: list[str] = []
        for token in _TOKEN.findall(message):
            if token.isalpha():
                lower = token.lower()
                parts.append(lower if lower in keep else "*" * len(token))
            elif token.isdigit():
                parts.append("#" * len(token))
            else:
                parts.append(token)
        text = "".join(parts).strip()
        if text:
            masked.append(text)
    return masked


def masked_charlm(
    unknown: Sequence[str],
    candidates: Mapping[str, Sequence[str]],
    keep_words: int = MASKED_WORDS,
    order: int = 6,
) -> dict[str, float]:
    """Выигрыш языковой модели символов (бит/символ) при замаскированных редких словах."""
    counts: Counter[str] = Counter()
    for messages in (unknown, *candidates.values()):
        for message in messages:
            counts.update(words_of(message))
    keep = {word for word, _ in counts.most_common(keep_words)}
    unknown_view = mask_rare_words(unknown, keep)
    views = {label: mask_rare_words(messages, keep) for label, messages in candidates.items()}
    reports = _core.charlm_compare(unknown_view, views, order, True)
    return {label: report["llr"] for label, report in reports.items() if report["available"]}


def z_scores(scores: Mapping[str, float]) -> dict[str, float]:
    """z-оценки значений среди кандидатов (нулевой разброс даёт нули)."""
    values = list(scores.values())
    mean = statistics.fmean(values)
    spread = statistics.pstdev(values)
    return {label: (value - mean) / spread if spread else 0.0 for label, value in scores.items()}


def mix(signals: Sequence[Mapping[str, float]], labels: Sequence[str]) -> dict[str, float]:
    """Среднее z-оценок по сигналам, доступным у ВСЕХ кандидатов; нужно хотя бы два сигнала.

    Больше — ближе. Значение относительно набора кандидатов этого сравнения и в разных запусках
    несравнимо. При двух кандидатах это доля «голосов» методов, по сути: +1 — все методы за,
    -1 — все против.
    """
    complete = [z_scores(signal) for signal in signals if set(signal) >= set(labels)]
    if len(complete) < 2 or len(labels) < 2:
        return {}
    return {label: statistics.fmean(z[label] for z in complete) for label in labels}
