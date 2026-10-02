"""Абляция групп стилевых признаков для Burrows Delta.

    python -m experiments.ablation ДАТАСЕТ --words 1000 --impostors 10 --jobs 4 --output out.json

Сравнивает качество Burrows Delta при разных группах стилевых признаков на одном датасете.
Варианты: "none" (ничего), по одной группе ("punctuation", "orthography", "words",
"sentences") и "all".
Итоговая оценка Impostors и косинус от групп не зависят, поэтому сравниваем только Delta.

СИНТЕТИЧЕСКИЕ ДАННЫЕ: числа с такого датасета нельзя публиковать как результат качества.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from chatstyle.errors import ChatstyleError
from chatstyle.features import ALL_STYLE_GROUPS

from experiments.evaluate import (
    SYNTHETIC_WARNING,
    build_trials,
    load_dataset,
    run_trials,
    summarize,
)

VARIANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("none", ()),
    ("punctuation", ("punctuation",)),
    ("orthography", ("orthography",)),
    ("words", ("words",)),
    ("sentences", ("sentences",)),
    ("all", ALL_STYLE_GROUPS),
)


def run_ablation(
    dataset_dir: Path,
    words: int = 1000,
    neg_per_pos: int = 1,
    impostors: int = 10,
    seed: int = 1,
    jobs: int = 1,
    bootstrap: int = 200,
    folds: int = 5,
) -> tuple[list[dict], bool]:
    """Запустить абляцию для датасета.

    Возвращает список словарей с метриками для каждого варианта и признак synthetic.
    """
    dataset = load_dataset(dataset_dir, words)
    trials = build_trials(list(dataset.segments), neg_per_pos, impostors, seed)

    rows: list[dict] = []
    for name, groups in VARIANTS:
        results = run_trials(dataset.segments, trials, seed, jobs, groups)
        summary = summarize(results, seed, bootstrap, folds)
        delta_metrics = summary["delta"]
        rows.append(
            {
                "variant": name,
                "groups": list(groups),
                "trials": delta_metrics["trials"],
                "coverage": delta_metrics["coverage"],
                "auc": delta_metrics["auc"],
                "auc_ci95": delta_metrics["auc_ci95"],
            }
        )

    return rows, dataset.synthetic


def format_table(rows: list[dict]) -> str:
    """Сформировать текстовую таблицу метрик."""
    header = f"{'Вариант':<18}{'Испытаний':>10}{'Покрытие':>10}{'AUC':>8}{'AUC 95% ДИ':>16}"
    lines = [header]
    for row in rows:
        auc = "—" if row["auc"] is None else f"{row['auc']:.3f}"
        ci = "—"
        if row["auc_ci95"] is not None:
            ci = f"[{row['auc_ci95'][0]:.2f}; {row['auc_ci95'][1]:.2f}]"
        lines.append(
            f"{row['variant']:<18}{row['trials']:>10}{row['coverage']:>10.2f}{auc:>8}{ci:>16}"
        )
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Абляция групп стилевых признаков для Burrows Delta."
    )
    parser.add_argument("dataset", type=Path, help="папка: датасет по файлам на автора")
    parser.add_argument("--words", type=int, default=1000, help="слов в каждом из двух кусков")
    parser.add_argument("--neg-per-pos", type=int, default=1, help="отрицательных на положительное")
    parser.add_argument(
        "--impostors", type=int, default=10, help="посторонних авторов на испытание"
    )
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=1, help="число процессов")
    parser.add_argument("--bootstrap", type=int, default=200, help="число бутстрэп-выборок")
    parser.add_argument("--folds", type=int, default=5, help="фолдов для точности с порогом")
    parser.add_argument("--output", type=Path, default=None, help="записать результаты в JSON")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        rows, synthetic = run_ablation(
            args.dataset,
            args.words,
            args.neg_per_pos,
            args.impostors,
            args.seed,
            args.jobs,
            args.bootstrap,
            args.folds,
        )
    except ChatstyleError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2

    if synthetic:
        print(SYNTHETIC_WARNING)
    print(format_table(rows))
    if synthetic:
        print(SYNTHETIC_WARNING)

    if args.output is not None:
        report = {
            "parameters": {
                "words": args.words,
                "neg_per_pos": args.neg_per_pos,
                "impostors": args.impostors,
                "seed": args.seed,
                "bootstrap": args.bootstrap,
                "folds": args.folds,
            },
            "synthetic": synthetic,
            "rows": rows,
        }
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"Результаты сохранены: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
