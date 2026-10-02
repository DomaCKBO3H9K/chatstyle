"""Модуль пайплайна сравнения авторства.

Содержит функции для подсчёта слов и запуска сравнения тремя методами: косинусное сходство
n-грамм, Burrows Delta и General Impostors. Не использует typer, rich, print.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from chatstyle import _core
from chatstyle.collectors import CollectOptions, collect
from chatstyle.delta import (
    DEFAULT_CHUNK_WORDS,
    DEFAULT_MIN_CHUNKS,
    DEFAULT_TOP_DIFFERENCES,
    DeltaScore,
    burrows_delta,
)
from chatstyle.emoji import emoji_views
from chatstyle.errors import ChatstyleError
from chatstyle.features import ALL_STYLE_GROUPS, FUNCTION_WORD_PREFIX, style_features
from chatstyle.impostors import (
    DEFAULT_CHUNK_WORDS as IMPOSTORS_CHUNK_WORDS,
)
from chatstyle.impostors import (
    DEFAULT_MIN_CHUNKS as IMPOSTORS_MIN_CHUNKS,
)
from chatstyle.impostors import (
    DEFAULT_MIN_IMPOSTORS,
    DEFAULT_SEED,
    ImpostorsScore,
    general_impostors,
)
from chatstyle.preprocess import MENTION_TOKEN, URL_TOKEN, preprocess
from chatstyle.wordgrams import word_views

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
    similarity: float  # косинус TF-IDF символьных n-грамм, 0..1
    top_features: tuple[SharedFeature, ...] = ()
    delta: DeltaScore | None = None  # None: метод не запускался
    impostors_score: ImpostorsScore | None = None  # None: метод не запускался
    morph_similarity: float | None = None  # косинус по n-граммам частей речи; None: не считался
    charlm_llr: float | None = None  # языковая модель символов, бит/символ; None: нет оценки
    wordgram_similarity: float | None = None  # пословные n-граммы; None: не считался
    emoji_similarity: float | None = None  # n-граммы эмодзи; None: не считался

    @property
    def final_score(self) -> float | None:
        """Итоговая оценка — оценка General Impostors; None, если она недоступна."""
        score = self.impostors_score
        return score.score if score is not None and score.available else None


METHOD_COSINE = "cosine"
METHOD_DELTA = "delta"
METHOD_IMPOSTORS = "impostors"
METHOD_NAMES: dict[str, str] = {
    METHOD_COSINE: "косинус",
    METHOD_DELTA: "Delta",
    METHOD_IMPOSTORS: "Impostors",
}


@dataclass(frozen=True)
class ComparisonResult:
    """Результат сравнения неизвестного автора с кандидатами."""

    unknown_label: str
    unknown: AuthorStats
    candidates: tuple[CandidateResult, ...]
    seed: int = DEFAULT_SEED
    impostor_count: int = 0  # сколько посторонних авторов дала папка --impostors
    ranked_by: str = METHOD_COSINE  # по какому методу отсортированы кандидаты
    morph: bool = False  # считалось ли сходство по частям речи
    charlm: bool = False  # считалась ли языковая модель символов
    wordgrams: bool = False  # считались ли пословные n-граммы
    emoji: bool = False  # считалось ли сходство по эмодзи

    def best_by_method(self) -> dict[str, tuple[str, ...]]:
        """Лучшие кандидаты по каждому методу, доступному ВСЕМ кандидатам.

        При равенстве лучших несколько подписей. Метод, недоступный хотя бы одному кандидату,
        не включается: сравнивать лучшего среди части кандидатов было бы нечестно.
        """
        best: dict[str, tuple[str, ...]] = {}
        rows = self.candidates
        if not rows:
            return best
        top_cosine = max(row.similarity for row in rows)
        best[METHOD_COSINE] = tuple(row.label for row in rows if row.similarity == top_cosine)
        deltas = [row.delta.delta for row in rows if row.delta is not None and row.delta.available]
        if len(deltas) == len(rows):
            lowest = min(deltas)
            best[METHOD_DELTA] = tuple(
                row.label for row in rows if row.delta is not None and row.delta.delta == lowest
            )
        scores = [row.final_score for row in rows if row.final_score is not None]
        if len(scores) == len(rows):
            highest = max(scores)
            best[METHOD_IMPOSTORS] = tuple(row.label for row in rows if row.final_score == highest)
        return best

    def methods_agree(self) -> bool | None:
        """Совпадают ли лучшие кандидаты методов; None, если методов меньше двух."""
        best = list(self.best_by_method().values())
        if len(best) < 2:
            return None
        return bool(set.intersection(*(set(labels) for labels in best)))


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


NOT_AVAILABLE = "—"


def delta_text(candidate: CandidateResult) -> str:
    """Delta кандидата для таблицы или прочерк."""
    delta = candidate.delta
    return f"{delta.delta:.2f}" if delta is not None and delta.available else NOT_AVAILABLE


def morph_text(candidate: CandidateResult) -> str:
    """Сходство по частям речи для таблицы или прочерк."""
    value = candidate.morph_similarity
    return f"{value:.3f}" if value is not None else NOT_AVAILABLE


def emoji_text(candidate: CandidateResult) -> str:
    """Сходство по эмодзи для таблицы или прочерк."""
    value = candidate.emoji_similarity
    return f"{value:.3f}" if value is not None else NOT_AVAILABLE


def wordgram_text(candidate: CandidateResult) -> str:
    """Сходство по пословным n-граммам для таблицы или прочерк."""
    value = candidate.wordgram_similarity
    return f"{value:.3f}" if value is not None else NOT_AVAILABLE


def charlm_text(candidate: CandidateResult) -> str:
    """Выигрыш языковой модели кандидата над остальными (бит на символ, со знаком) или прочерк."""
    value = candidate.charlm_llr
    return f"{value:+.3f}" if value is not None else NOT_AVAILABLE


def final_score_text(candidate: CandidateResult) -> str:
    """Итоговая оценка кандидата для таблицы или прочерк."""
    score = candidate.final_score
    return f"{score:.2f}" if score is not None else NOT_AVAILABLE


def ranking_text(result: ComparisonResult) -> str:
    """По какому методу отсортированы кандидаты."""
    if result.ranked_by == METHOD_IMPOSTORS:
        return "Порядок: по итоговой оценке (General Impostors)."
    return "Порядок: по косинусному сходству (итоговая оценка недоступна)."


def best_methods_text(result: ComparisonResult) -> str | None:
    """Лучшие кандидаты по методам и согласие методов; None, если метод всего один."""
    best = result.best_by_method()
    if len(best) < 2:
        return None
    parts = [f"{METHOD_NAMES[method]} — {', '.join(labels)}" for method, labels in best.items()]
    verdict = "методы согласны" if result.methods_agree() else "методы расходятся"
    return f"Лучший по методам: {'; '.join(parts)} ({verdict})."


def unavailable_facts(result: ComparisonResult) -> list[dict[str, object]]:
    """Почему Delta и Impostors недоступны, в виде кодов с параметрами (для перевода в окне).

    Кандидаты с одной и той же причиной объединяются в один словарь; порядок: Delta, затем
    Impostors с нехваткой посторонних (по числу посторонних), затем Impostors с нехваткой текста.
    """
    facts: list[dict[str, object]] = []
    short_delta = [
        row.label for row in result.candidates if row.delta is not None and not row.delta.available
    ]
    if short_delta:
        facts.append(
            {
                "code": "delta_short",
                "labels": short_delta,
                "min_chunks": DEFAULT_MIN_CHUNKS,
                "chunk_words": DEFAULT_CHUNK_WORDS,
            }
        )

    few_impostors: dict[int, list[str]] = {}
    short_text: list[str] = []
    for row in result.candidates:
        score = row.impostors_score
        if score is None or score.available:
            continue
        if score.impostors < DEFAULT_MIN_IMPOSTORS:
            few_impostors.setdefault(score.impostors, []).append(row.label)
        else:
            short_text.append(row.label)
    for count, labels in few_impostors.items():
        facts.append(
            {
                "code": "impostors_few",
                "labels": labels,
                "count": count,
                "need": DEFAULT_MIN_IMPOSTORS,
            }
        )
    if short_text:
        facts.append(
            {
                "code": "impostors_short",
                "labels": short_text,
                "min_chunks": IMPOSTORS_MIN_CHUNKS,
                "chunk_words": IMPOSTORS_CHUNK_WORDS,
            }
        )
    return facts


def unavailable_notes(result: ComparisonResult) -> list[str]:
    """Почему Delta и Impostors недоступны (пустой список, если доступны всем кандидатам)."""
    notes: list[str] = []
    for fact in unavailable_facts(result):
        labels = ", ".join(fact["labels"])  # type: ignore[arg-type]
        if fact["code"] == "delta_short":
            notes.append(
                f"Burrows Delta недоступна ({labels}): слишком мало текста для "
                f"оценки разброса признаков (нужно не меньше {fact['min_chunks']} кусков по "
                f"{fact['chunk_words']} слов на всё сравнение)."
            )
        elif fact["code"] == "impostors_few":
            notes.append(
                f"General Impostors недоступен ({labels}): посторонних авторов {fact['count']} "
                f"из {fact['need']}; добавьте папку с чужими текстами: --impostors DIR."
            )
        else:
            notes.append(
                f"General Impostors недоступен ({labels}): слишком мало текста "
                f"(нужно не меньше {fact['min_chunks']} кусков по {fact['chunk_words']} слов "
                "у неизвестного автора и у кандидата)."
            )
    return notes


def _load_messages(spec: str, options: CollectOptions | None) -> list[str]:
    """Собрать и предобработать сообщения источника; пустой результат — ошибка."""
    messages = preprocess(collect(spec, options))
    if not messages:
        raise ChatstyleError(f"В источнике {spec} не осталось сообщений после предобработки.")
    return messages


def _morph_similarities(
    unknown_messages: Sequence[str], candidate_messages: Mapping[str, Sequence[str]]
) -> dict[str, float]:
    """Косинус по n-граммам частей речи (1-4): слова заменяются кодами, дальше считает ядро.

    У кого нет ни одного слова (нечего размечать), оценки нет: такого кандидата в словаре нет.
    """
    from chatstyle import morph

    morph.require()
    unknown_view = morph.compact_view(unknown_messages)
    views = {label: morph.compact_view(messages) for label, messages in candidate_messages.items()}
    views = {label: view for label, view in views.items() if view}
    if not unknown_view or not views:
        return {}
    reports = _core.compare_detailed(unknown_view, views, 0)
    return {label: report["similarity"] for label, report in reports.items()}


def _wordgram_similarities(
    unknown_messages: Sequence[str], candidate_messages: Mapping[str, Sequence[str]]
) -> dict[str, float]:
    """Косинус по пословным n-граммам 1-4: слова заменяются символами, дальше считает ядро.

    У кого нет ни одного слова, оценки нет: такого кандидата в словаре нет.
    """
    unknown_view, views = word_views(unknown_messages, candidate_messages)
    views = {label: view for label, view in views.items() if view}
    if not unknown_view or not views:
        return {}
    reports = _core.compare_detailed(unknown_view, views, 0)
    return {label: report["similarity"] for label, report in reports.items()}


def _emoji_similarities(
    unknown_messages: Sequence[str], candidate_messages: Mapping[str, Sequence[str]]
) -> dict[str, float]:
    """Косинус по n-граммам эмодзи 1-4: эмодзи заменяются символами, дальше считает ядро.

    У кого нет ни одного эмодзи, оценки нет: такого кандидата в словаре нет.
    """
    unknown_view, views = emoji_views(unknown_messages, candidate_messages)
    views = {label: view for label, view in views.items() if view}
    if not unknown_view or not views:
        return {}
    reports = _core.compare_detailed(unknown_view, views, 0)
    return {label: report["similarity"] for label, report in reports.items()}


def _charlm_scores(
    unknown_messages: Sequence[str], candidate_messages: Mapping[str, Sequence[str]]
) -> dict[str, float]:
    """Выигрыш модели символов кандидата над моделью остальных, бит на символ (ядро).

    Больше нуля: текст неизвестного автора предсказывается моделью кандидата лучше, чем моделью
    остальных. Нужны минимум два непустых кандидата; у остальных оценки нет.
    """
    reports = _core.charlm_compare(list(unknown_messages), dict(candidate_messages))
    return {label: report["llr"] for label, report in reports.items() if report["available"]}


def compare_messages(
    unknown_messages: Sequence[str],
    candidate_messages: Mapping[str, Sequence[str]],
    *,
    impostors: Mapping[str, Sequence[str]] | None = None,
    seed: int = DEFAULT_SEED,
    top_features: int = DEFAULT_TOP_FEATURES,
    top_differences: int = DEFAULT_TOP_DIFFERENCES,
    style_groups: Sequence[str] = ALL_STYLE_GROUPS,
    morph: bool = False,
    charlm: bool = False,
    wordgrams: bool = False,
    emoji: bool = False,
) -> tuple[tuple[CandidateResult, ...], str]:
    """Три метода по готовым предобработанным сообщениям: косинус, Burrows Delta, Impostors.

    Общая часть `run_comparison` и оценки качества (experiments/): оба считают одним и тем же
    кодом. Возвращает кандидатов в порядке ранжирования и название метода, по которому они
    отсортированы (по итоговой оценке, если она есть у всех, иначе по косинусу).
    """
    reports = _core.compare_detailed(list(unknown_messages), dict(candidate_messages), top_features)
    deltas = burrows_delta(
        unknown_messages,
        candidate_messages,
        top_differences=top_differences,
        groups=style_groups,
    )
    impostor_scores = general_impostors(unknown_messages, candidate_messages, impostors, seed=seed)
    morph_scores = _morph_similarities(unknown_messages, candidate_messages) if morph else {}
    charlm_scores = _charlm_scores(unknown_messages, candidate_messages) if charlm else {}
    wordgram_scores = (
        _wordgram_similarities(unknown_messages, candidate_messages) if wordgrams else {}
    )
    emoji_scores = _emoji_similarities(unknown_messages, candidate_messages) if emoji else {}

    results: list[CandidateResult] = []
    for label, messages in candidate_messages.items():
        report = reports[label]
        results.append(
            CandidateResult(
                label=label,
                words=count_words(messages),
                messages=len(messages),
                similarity=report["similarity"],
                top_features=tuple(SharedFeature(**item) for item in report["features"]),
                delta=deltas[label],
                impostors_score=impostor_scores[label],
                morph_similarity=morph_scores.get(label),
                charlm_llr=charlm_scores.get(label),
                wordgram_similarity=wordgram_scores.get(label),
                emoji_similarity=emoji_scores.get(label),
            )
        )

    # Сортировка стабильная: при равенстве остаётся порядок ввода
    ranked_by = METHOD_COSINE
    if all(row.final_score is not None for row in results):
        ranked_by = METHOD_IMPOSTORS
        results.sort(key=lambda r: (-(r.final_score or 0.0), -r.similarity))
    else:
        results.sort(key=lambda r: -r.similarity)
    return tuple(results), ranked_by


def run_comparison(
    unknown_spec: str,
    candidate_specs: Sequence[str],
    options: CollectOptions | None = None,
    top_features: int = DEFAULT_TOP_FEATURES,
    impostors: Mapping[str, Sequence[str]] | None = None,
    seed: int = DEFAULT_SEED,
    style_groups: Sequence[str] = ALL_STYLE_GROUPS,
    morph: bool = False,
    charlm: bool = False,
    wordgrams: bool = False,
    emoji: bool = False,
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
    impostors : Mapping[str, Sequence[str]] | None
        Посторонние авторы (предобработанные сообщения) для General Impostors; остальные
        кандидаты участвуют в нём автоматически.
    seed : int
        Seed General Impostors: один и тот же seed даёт один и тот же результат.

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

    results, ranked_by = compare_messages(
        unknown_messages,
        candidate_messages,
        impostors=impostors,
        seed=seed,
        top_features=top_features,
        style_groups=style_groups,
        morph=morph,
        charlm=charlm,
        wordgrams=wordgrams,
        emoji=emoji,
    )

    unknown_words = count_words(unknown_messages)
    unknown_stats = AuthorStats(
        words=unknown_words,
        messages=len(unknown_messages),
    )

    return ComparisonResult(
        unknown_label=unknown_spec,
        unknown=unknown_stats,
        candidates=results,
        seed=seed,
        impostor_count=len(impostors or {}),
        ranked_by=ranked_by,
        morph=morph,
        charlm=charlm,
        wordgrams=wordgrams,
        emoji=emoji,
    )


@dataclass(frozen=True)
class AuthorProfile:
    """Профиль стиля одного автора."""

    label: str
    stats: AuthorStats
    features: dict[str, float]
    morph_features: dict[str, float] | None = None  # m:<код части речи>; None: не считались


def morph_profile(messages: Sequence[str]) -> dict[str, float]:
    """Доли частей речи среди слов автора (`m:n` — существительные, `m:x` — слов нет в словаре).

    Слова заменяются кодами, частоты кодов считает то же ядро, что и частоты служебных слов.
    """
    from chatstyle import morph

    morph.require()
    shares = _core.style_features(
        morph.pos_view(messages), list(morph.ALL_CODES), [], [], [], [], 0
    )
    return {
        f"m:{key[len(FUNCTION_WORD_PREFIX) :]}": value
        for key, value in shares.items()
        if key.startswith(FUNCTION_WORD_PREFIX)
    }


def profile_author(
    spec: str, options: CollectOptions | None = None, morph: bool = False
) -> AuthorProfile:
    """Собрать сообщения автора и посчитать его стилевые признаки (и части речи, если morph)."""
    messages = _load_messages(spec, options)
    return AuthorProfile(
        label=spec,
        stats=AuthorStats(words=count_words(messages), messages=len(messages)),
        features=style_features(messages),
        morph_features=morph_profile(messages) if morph else None,
    )
