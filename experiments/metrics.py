"""Метрики качества верификации без внешних зависимостей: ROC AUC, пороги, бутстрэп."""

import random
from bisect import bisect_left
from collections.abc import Sequence


def roc_auc(labels: Sequence[bool], scores: Sequence[float]) -> float | None:
    """ROC AUC (вероятность, что случайная положительная пара получит оценку выше отрицательной).

    Считается через ранги Манна-Уитни, совпавшие оценки получают средний ранг (вклад 0.5).
    Возвращает None, если нет положительных или нет отрицательных примеров.
    """
    positives = sum(1 for label in labels if label)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return None
    order = sorted(range(len(scores)), key=lambda index: scores[index])
    ranks = [0.0] * len(scores)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and scores[order[end + 1]] == scores[order[start]]:
            end += 1
        average_rank = (start + end) / 2 + 1
        for position in range(start, end + 1):
            ranks[order[position]] = average_rank
        start = end + 1
    positive_rank_sum = sum(rank for rank, label in zip(ranks, labels, strict=True) if label)
    return (positive_rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def accuracy(labels: Sequence[bool], scores: Sequence[float], threshold: float) -> float:
    """Доля верных ответов при правиле «пара от одного автора, если оценка >= порога»."""
    correct = sum(
        1 for label, score in zip(labels, scores, strict=True) if (score >= threshold) == label
    )
    return correct / len(labels)


def best_threshold(labels: Sequence[bool], scores: Sequence[float]) -> float:
    """Порог с наибольшей точностью (при равенстве — наименьший)."""
    positive_scores = sorted(score for label, score in zip(labels, scores, strict=True) if label)
    negative_scores = sorted(
        score for label, score in zip(labels, scores, strict=True) if not label
    )
    unique = sorted(set(scores))
    candidates = [unique[0]]
    candidates += [(left + right) / 2 for left, right in zip(unique, unique[1:], strict=False)]
    candidates.append(unique[-1] + 1.0)  # «все пары от разных авторов»
    best_value = -1.0
    best = candidates[0]
    for threshold in candidates:
        true_positives = len(positive_scores) - bisect_left(positive_scores, threshold)
        true_negatives = bisect_left(negative_scores, threshold)
        value = (true_positives + true_negatives) / len(labels)
        if value > best_value:
            best_value = value
            best = threshold
    return best


def cross_validated_accuracy(
    labels: Sequence[bool], scores: Sequence[float], folds: int = 5, seed: int = 1
) -> float | None:
    """Точность, где порог каждой части подбирается на остальных частях (без подглядывания).

    Фолды стратифицированы по классам. Возвращает None, если примеров слишком мало
    (меньше двух в каком-либо классе).
    """
    positives = [index for index, label in enumerate(labels) if label]
    negatives = [index for index, label in enumerate(labels) if not label]
    fold_count = min(folds, len(positives), len(negatives))
    if fold_count < 2:
        return None
    rng = random.Random(seed)
    rng.shuffle(positives)
    rng.shuffle(negatives)
    fold_of = {}
    for group in (positives, negatives):
        for position, index in enumerate(group):
            fold_of[index] = position % fold_count
    correct = 0
    for fold in range(fold_count):
        train = [index for index in range(len(labels)) if fold_of[index] != fold]
        test = [index for index in range(len(labels)) if fold_of[index] == fold]
        threshold = best_threshold([labels[i] for i in train], [scores[i] for i in train])
        correct += sum(1 for i in test if (scores[i] >= threshold) == labels[i])
    return correct / len(labels)


def bootstrap_auc_ci(
    labels: Sequence[bool],
    scores: Sequence[float],
    groups: Sequence[str],
    resamples: int = 1000,
    seed: int = 1,
    level: float = 0.95,
) -> tuple[float, float] | None:
    """Доверительный интервал AUC бутстрэпом по группам (авторам неизвестного текста).

    Пересэмплируются группы целиком вместе со всеми их испытаниями: так учитывается, что
    испытания одного автора зависимы. Возвращает None, если интервал не удалось оценить.
    """
    members: dict[str, list[int]] = {}
    for index, group in enumerate(groups):
        members.setdefault(group, []).append(index)
    names = sorted(members)
    if len(names) < 2:
        return None
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(resamples):
        chosen = [index for name in rng.choices(names, k=len(names)) for index in members[name]]
        value = roc_auc([labels[i] for i in chosen], [scores[i] for i in chosen])
        if value is not None:
            values.append(value)
    if len(values) < max(20, resamples // 2):
        return None
    values.sort()
    low = values[int((1 - level) / 2 * (len(values) - 1))]
    high = values[int((1 + level) / 2 * (len(values) - 1))]
    return low, high
