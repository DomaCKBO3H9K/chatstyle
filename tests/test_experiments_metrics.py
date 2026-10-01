import random

import pytest

from experiments.metrics import (
    accuracy,
    best_threshold,
    bootstrap_auc_ci,
    cross_validated_accuracy,
    roc_auc,
)


def brute_force_auc(labels: list[bool], scores: list[float]) -> float:
    wins = 0.0
    pairs = 0
    for label_a, score_a in zip(labels, scores, strict=True):
        for label_b, score_b in zip(labels, scores, strict=True):
            if label_a and not label_b:
                pairs += 1
                wins += 1.0 if score_a > score_b else 0.5 if score_a == score_b else 0.0
    return wins / pairs


# --- ROC AUC ---


def test_auc_perfect_reverse_and_chance() -> None:
    assert roc_auc([True, True, False, False], [0.9, 0.8, 0.2, 0.1]) == 1.0
    assert roc_auc([True, True, False, False], [0.1, 0.2, 0.8, 0.9]) == 0.0
    assert roc_auc([True, False, True, False], [0.5, 0.5, 0.5, 0.5]) == 0.5


def test_auc_hand_computed_mixed_case() -> None:
    # пары (положительный, отрицательный): 0.9>0.6, 0.9>0.1, 0.4<0.6, 0.4>0.1 -> 3 из 4
    assert roc_auc([True, True, False, False], [0.9, 0.4, 0.6, 0.1]) == pytest.approx(0.75)


def test_auc_ties_count_as_half() -> None:
    assert roc_auc([True, False], [1.0, 1.0]) == 0.5
    # положительные 0.7 и 0.5, отрицательные 0.5 и 0.2: 0.7>0.5, 0.7>0.2, 0.5=0.5, 0.5>0.2
    assert roc_auc([True, True, False, False], [0.7, 0.5, 0.5, 0.2]) == pytest.approx(3.5 / 4)


def test_auc_needs_both_classes() -> None:
    assert roc_auc([True, True], [0.1, 0.9]) is None
    assert roc_auc([False], [0.5]) is None
    assert roc_auc([], []) is None


def test_auc_matches_brute_force_on_random_data_with_ties() -> None:
    rng = random.Random(3)
    for _ in range(25):
        size = rng.randint(4, 40)
        labels = [rng.random() < 0.4 for _ in range(size)]
        if all(labels) or not any(labels):
            continue
        scores = [round(rng.random(), 1) for _ in range(size)]  # много совпадений
        assert roc_auc(labels, scores) == pytest.approx(brute_force_auc(labels, scores))


# --- точность и порог ---


def test_accuracy_uses_greater_or_equal_rule() -> None:
    labels = [True, True, False, False]
    scores = [0.9, 0.5, 0.5, 0.1]
    assert accuracy(labels, scores, 0.5) == 0.75  # 0.5 считается «один автор»
    assert accuracy(labels, scores, 0.6) == 0.75
    assert accuracy(labels, scores, 0.0) == 0.5


def test_best_threshold_separates_separable_classes() -> None:
    labels = [True, True, True, False, False, False]
    scores = [0.9, 0.8, 0.7, 0.3, 0.2, 0.1]
    threshold = best_threshold(labels, scores)
    assert 0.3 < threshold <= 0.7
    assert accuracy(labels, scores, threshold) == 1.0


def test_best_threshold_degenerate_cases() -> None:
    assert accuracy([True, True], [0.3, 0.7], best_threshold([True, True], [0.3, 0.7])) == 1.0
    assert accuracy([False, False], [0.3, 0.7], best_threshold([False, False], [0.3, 0.7])) == 1.0
    # при равной точности выбирается наименьший порог
    assert best_threshold([True, False], [0.5, 0.5]) == 0.5


def test_best_threshold_is_optimal_by_brute_force() -> None:
    rng = random.Random(5)
    labels = [rng.random() < 0.5 for _ in range(60)]
    scores = [rng.random() + (0.3 if label else 0.0) for label in labels]
    best = accuracy(labels, scores, best_threshold(labels, scores))
    brute = max(accuracy(labels, scores, t) for t in sorted(set(scores)) + [max(scores) + 1])
    assert best == pytest.approx(brute)


# --- точность с честным порогом ---


def test_cv_accuracy_on_separable_data() -> None:
    labels = [True] * 10 + [False] * 10
    scores = [0.8 + i * 0.01 for i in range(10)] + [0.1 + i * 0.01 for i in range(10)]
    assert cross_validated_accuracy(labels, scores, folds=5, seed=1) == 1.0


def test_cv_accuracy_is_not_optimistic_on_noise() -> None:
    rng = random.Random(11)
    labels = [rng.random() < 0.5 for _ in range(200)]
    scores = [rng.random() for _ in labels]  # оценка не связана с классом
    honest = cross_validated_accuracy(labels, scores, folds=5, seed=1)
    optimistic = accuracy(labels, scores, best_threshold(labels, scores))
    assert honest is not None
    assert honest < 0.65
    assert optimistic > honest


def test_cv_accuracy_needs_enough_examples_and_is_deterministic() -> None:
    assert cross_validated_accuracy([True, False, False], [0.9, 0.1, 0.2]) is None
    assert cross_validated_accuracy([True, True, True], [0.1, 0.2, 0.3]) is None
    labels = [i % 2 == 0 for i in range(30)]
    scores = [random.Random(i).random() for i in range(30)]
    first = cross_validated_accuracy(labels, scores, folds=4, seed=2)
    assert first == cross_validated_accuracy(labels, scores, folds=4, seed=2)


# --- бутстрэп ---


def test_bootstrap_interval_contains_auc_and_is_deterministic() -> None:
    rng = random.Random(8)
    groups = [f"a{i % 10}" for i in range(80)]
    labels = [i % 2 == 0 for i in range(80)]
    scores = [rng.random() + (0.5 if label else 0.0) for label in labels]
    auc = roc_auc(labels, scores)
    interval = bootstrap_auc_ci(labels, scores, groups, resamples=300, seed=4)
    assert auc is not None and interval is not None
    assert interval[0] <= auc <= interval[1]
    assert interval == bootstrap_auc_ci(labels, scores, groups, resamples=300, seed=4)


def test_bootstrap_of_perfect_separation_is_degenerate() -> None:
    groups = [f"a{i}" for i in range(10)] * 2
    labels = [True] * 10 + [False] * 10
    scores = [1.0] * 10 + [0.0] * 10
    assert bootstrap_auc_ci(labels, scores, groups, resamples=100, seed=1) == (1.0, 1.0)


def test_bootstrap_needs_several_groups() -> None:
    assert bootstrap_auc_ci([True, False], [1.0, 0.0], ["a", "a"], resamples=100) is None
