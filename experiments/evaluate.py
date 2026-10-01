"""Оценка качества методов chatstyle на датасете «по файлу на автора».

    python -m experiments.evaluate DATASET --words 1000 --impostors 10 --seed 1 --jobs 4 \\
        --output results.json

Каждое испытание — пара «неизвестный текст / кандидат» плюс посторонние авторы; пара считается
настоящей конвейерной функцией `compare_messages`, той же, что использует CLI. Для каждого
метода (косинус, Delta, итоговая оценка Impostors) считаются ROC AUC с доверительным интервалом,
точность с порогом, подобранным не на тех же данных, и покрытие (доля испытаний, где метод
доступен). В результатах нет текстов: только анонимные id авторов и числа.
"""

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path

from chatstyle.errors import ChatstyleError
from chatstyle.pipeline import compare_messages

from experiments.metrics import (
    accuracy,
    best_threshold,
    bootstrap_auc_ci,
    cross_validated_accuracy,
    roc_auc,
)
from experiments.trials import Segments, Trial, build_trials, load_dataset

SYNTHETIC_WARNING = (
    "СИНТЕТИЧЕСКИЕ ДАННЫЕ: этот прогон нужен только для отладки скрипта; числа нельзя "
    "использовать как результат качества (README, отчёты)."
)

_SEGMENTS: Segments = {}


@dataclass(frozen=True)
class TrialResult:
    index: int
    same: bool
    unknown_author: str
    candidate_author: str
    cosine: float
    delta: float | None  # None: метод недоступен
    impostors: float | None  # итоговая оценка General Impostors, None: недоступна


# Метод -> (название, функция, превращающая результат в оценку «больше — вероятнее один автор»)
METHODS: dict[str, tuple[str, Callable[[TrialResult], float | None]]] = {
    "cosine": ("Косинус", lambda r: r.cosine),
    "delta": ("Delta (минус)", lambda r: None if r.delta is None else -r.delta),
    "impostors": ("Impostors (итог)", lambda r: r.impostors),
}


def _init_worker(segments: Segments) -> None:
    global _SEGMENTS
    _SEGMENTS = segments


def score_trial(trial: Trial, seed: int) -> TrialResult:
    """Посчитать три метода для одного испытания; seed Impostors зависит от номера испытания."""
    unknown = _SEGMENTS[trial.unknown_author][0]
    candidate = _SEGMENTS[trial.candidate_author][1]
    impostors = {name: _SEGMENTS[name][1] for name in trial.impostor_authors}
    candidates, _ = compare_messages(
        unknown,
        {"candidate": candidate},
        impostors=impostors,
        seed=seed + trial.index,
        top_features=0,
        top_differences=0,
    )
    row = candidates[0]
    return TrialResult(
        index=trial.index,
        same=trial.same,
        unknown_author=trial.unknown_author,
        candidate_author=trial.candidate_author,
        cosine=row.similarity,
        delta=row.delta.delta if row.delta is not None and row.delta.available else None,
        impostors=row.final_score,
    )


def run_trials(
    segments: Segments, trials: Sequence[Trial], seed: int, jobs: int = 1
) -> list[TrialResult]:
    """Посчитать все испытания; результат в порядке испытаний и не зависит от jobs."""
    worker = partial(score_trial, seed=seed)
    if jobs <= 1:
        _init_worker(segments)
        return [worker(trial) for trial in trials]
    with ProcessPoolExecutor(
        max_workers=jobs, initializer=_init_worker, initargs=(segments,)
    ) as executor:
        return list(executor.map(worker, trials))


def summarize(
    results: Sequence[TrialResult], seed: int = 1, resamples: int = 1000, folds: int = 5
) -> dict[str, dict[str, object]]:
    """Метрики каждого метода по испытаниям, где он доступен."""
    summary: dict[str, dict[str, object]] = {}
    for key, (title, extract) in METHODS.items():
        rows = [(r.same, extract(r), r.unknown_author) for r in results]
        usable = [(same, score, group) for same, score, group in rows if score is not None]
        labels = [same for same, _, _ in usable]
        scores = [float(score) for _, score, _ in usable if score is not None]
        groups = [group for _, _, group in usable]
        auc = roc_auc(labels, scores)
        interval = bootstrap_auc_ci(labels, scores, groups, resamples=resamples, seed=seed)
        optimistic = (
            accuracy(labels, scores, best_threshold(labels, scores))
            if scores and auc is not None
            else None
        )
        summary[key] = {
            "title": title,
            "trials": len(usable),
            "coverage": len(usable) / len(results) if results else 0.0,
            "auc": auc,
            "auc_ci95": list(interval) if interval else None,
            "accuracy_cv": cross_validated_accuracy(labels, scores, folds=folds, seed=seed),
            "accuracy_best_threshold_optimistic": optimistic,
            "accuracy_at_0.5": accuracy(labels, scores, 0.5)
            if key == "impostors" and scores
            else None,
        }
    return summary


def _fmt(value: object, digits: int = 3) -> str:
    return "—" if value is None else f"{float(value):.{digits}f}"  # type: ignore[arg-type]


def format_summary(summary: dict[str, dict[str, object]]) -> str:
    """Таблица метрик в виде текста."""
    header = (
        f"{'Метод':<18}{'Испытаний':>10}{'Покрытие':>10}{'AUC':>8}"
        f"{'AUC 95% ДИ':>16}{'Точность (CV)':>15}{'Лучший порог*':>15}{'При 0.5':>9}"
    )
    lines = [header]
    for entry in summary.values():
        interval = entry["auc_ci95"]
        ci = "—" if interval is None else f"[{interval[0]:.2f}; {interval[1]:.2f}]"  # type: ignore[index]
        lines.append(
            f"{entry['title']!s:<18}{entry['trials']!s:>10}{_fmt(entry['coverage'], 2):>10}"
            f"{_fmt(entry['auc']):>8}{ci:>16}{_fmt(entry['accuracy_cv']):>15}"
            f"{_fmt(entry['accuracy_best_threshold_optimistic']):>15}"
            f"{_fmt(entry['accuracy_at_0.5']):>9}"
        )
    lines.append(
        "* оптимистично: порог подобран на тех же данных; честная точность — в «Точность (CV)»"
    )
    return "\n".join(lines)


def build_report(
    args: argparse.Namespace,
    authors: int,
    skipped: int,
    synthetic: bool,
    results: Sequence[TrialResult],
    summary: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "parameters": {
            "words": args.words,
            "neg_per_pos": args.neg_per_pos,
            "impostors": args.impostors,
            "seed": args.seed,
            "bootstrap": args.bootstrap,
            "folds": args.folds,
        },
        "dataset": {"authors": authors, "skipped_authors": skipped, "synthetic": synthetic},
        "trials_total": len(results),
        "trials_same": sum(1 for r in results if r.same),
        "metrics": summary,
        "trials": [asdict(r) for r in results],
    }


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Оценка качества chatstyle на датасете авторов.")
    parser.add_argument("dataset", type=Path, help="папка: по файлу .txt на автора")
    parser.add_argument("--words", type=int, default=1000, help="слов в каждом из двух кусков")
    parser.add_argument("--neg-per-pos", type=int, default=1, help="отрицательных на положительное")
    parser.add_argument(
        "--impostors", type=int, default=10, help="посторонних авторов на испытание"
    )
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=1, help="число процессов")
    parser.add_argument("--bootstrap", type=int, default=1000, help="число бутстрэп-выборок")
    parser.add_argument("--folds", type=int, default=5, help="фолдов для точности с порогом")
    parser.add_argument("--output", type=Path, default=None, help="записать результаты в JSON")
    args = parser.parse_args(argv)
    if min(args.words, args.neg_per_pos, args.impostors, args.jobs, args.bootstrap, args.folds) < 1:
        parser.error("числовые параметры должны быть не меньше 1")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        dataset = load_dataset(args.dataset, args.words)
    except ChatstyleError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2

    if dataset.synthetic:
        print(SYNTHETIC_WARNING)
    trials = build_trials(list(dataset.segments), args.neg_per_pos, args.impostors, args.seed)
    print(
        f"Авторов: {len(dataset.segments)} "
        f"(пропущено из-за малого текста: {len(dataset.skipped)}); "
        f"испытаний: {len(trials)}; слов в куске: {args.words}"
    )
    results = run_trials(dataset.segments, trials, args.seed, args.jobs)
    summary = summarize(results, args.seed, args.bootstrap, args.folds)
    print(format_summary(summary))
    if dataset.synthetic:
        print(SYNTHETIC_WARNING)

    if args.output is not None:
        report = build_report(
            args, len(dataset.segments), len(dataset.skipped), dataset.synthetic, results, summary
        )
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"Результаты сохранены: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
