"""Качество методов в зависимости от объёма текста: срезы, порог надёжности, график.

    python -m experiments.volume DATASET --slices 250 500 1000 2000 5000 --jobs 4 \\
        --output-dir experiments/results

Каждый срез W — это оценка из evaluate.py с W словами у неизвестного автора и у кандидата.
По умолчанию во все срезы берётся один и тот же набор авторов (те, у кого хватает текста на
самый большой возможный срез): иначе на больших объёмах остались бы только самые активные
авторы, и рост качества частично был бы артефактом выбора. Результаты: volume.json,
volume.md и (если установлен matplotlib) volume.png.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from chatstyle.errors import ChatstyleError

from experiments.evaluate import METHODS, SYNTHETIC_WARNING, run_trials, summarize
from experiments.trials import MIN_AUTHORS, Dataset, build_trials, load_dataset

DEFAULT_SLICES = (250, 500, 1000, 2000, 5000)
DEFAULT_TARGET_AUC = 0.8
MIN_COVERAGE = 0.9  # метод считается пригодным на срезе, только если доступен в 90% испытаний
AUTHOR_SETS = ("common", "per-slice")


@dataclass(frozen=True)
class SliceResult:
    words: int
    authors: int
    trials: int
    metrics: dict[str, dict[str, object]]  # как у evaluate.summarize


@dataclass(frozen=True)
class VolumeReport:
    slices: tuple[SliceResult, ...]
    skipped: tuple[tuple[int, str], ...]  # (слов, причина)
    synthetic: bool
    author_set: str
    parameters: dict[str, object]


def plan_slices(
    directory: Path, slices: Sequence[int], author_set: str = "common"
) -> tuple[list[tuple[int, Dataset]], list[tuple[int, str]]]:
    """Наборы данных по срезам и список пропущенных срезов с причинами.

    Срез возможен, если на него набирается не меньше MIN_AUTHORS авторов. Авторы с большим
    требованием к тексту всегда входят в множество авторов меньшего среза, поэтому общий набор
    (`common`) — это авторы самого большого возможного среза.
    """
    if author_set not in AUTHOR_SETS:
        raise ChatstyleError(f"Набор авторов должен быть один из {AUTHOR_SETS}.")
    feasible: dict[int, Dataset] = {}
    skipped: list[tuple[int, str]] = []
    for words in sorted(set(slices)):
        try:
            feasible[words] = load_dataset(directory, words)
        except ChatstyleError:
            if not directory.is_dir():
                raise
            skipped.append((words, f"меньше {MIN_AUTHORS} авторов с текстом от {2 * words} слов"))
    if not feasible:
        raise ChatstyleError(
            f"Ни на одном срезе не набирается {MIN_AUTHORS} авторов: "
            f"{', '.join(f'{words}: {reason}' for words, reason in skipped)}."
        )
    if author_set == "common":
        base = set(feasible[max(feasible)].segments)
        feasible = {
            words: load_dataset(directory, words, authors=base) for words in sorted(feasible)
        }
    return sorted(feasible.items()), skipped


def run_volume(
    directory: Path,
    slices: Sequence[int] = DEFAULT_SLICES,
    *,
    author_set: str = "common",
    neg_per_pos: int = 1,
    impostors: int = 10,
    seed: int = 1,
    jobs: int = 1,
    bootstrap: int = 1000,
    folds: int = 5,
) -> VolumeReport:
    """Посчитать метрики на каждом возможном срезе."""
    plan, skipped = plan_slices(directory, slices, author_set)
    results: list[SliceResult] = []
    for words, dataset in plan:
        trials = build_trials(list(dataset.segments), neg_per_pos, impostors, seed)
        trial_results = run_trials(dataset.segments, trials, seed, jobs)
        results.append(
            SliceResult(
                words=words,
                authors=len(dataset.segments),
                trials=len(trials),
                metrics=summarize(trial_results, seed, bootstrap, folds),
            )
        )
    return VolumeReport(
        slices=tuple(results),
        skipped=tuple(skipped),
        synthetic=plan[0][1].synthetic,
        author_set=author_set,
        parameters={
            "slices": sorted(set(slices)),
            "neg_per_pos": neg_per_pos,
            "impostors": impostors,
            "seed": seed,
            "bootstrap": bootstrap,
            "folds": folds,
        },
    )


def _is_reliable(entry: dict[str, object], target_auc: float) -> bool:
    interval = entry["auc_ci95"]
    coverage = float(entry["coverage"])  # type: ignore[arg-type]
    return interval is not None and interval[0] >= target_auc and coverage >= MIN_COVERAGE  # type: ignore[index]


def min_reliable_words(
    report: VolumeReport, target_auc: float = DEFAULT_TARGET_AUC
) -> dict[str, int | None]:
    """Наименьший срез, с которого метод надёжен на этом и на всех бо́льших срезах.

    Надёжен — нижняя граница 95%-го ДИ для AUC не ниже target_auc и покрытие не ниже 90%.
    None: на проверенных срезах такого объёма не нашлось.
    """
    result: dict[str, int | None] = {}
    for method in METHODS:
        found: int | None = None
        for item in reversed(report.slices):
            if _is_reliable(item.metrics[method], target_auc):
                found = item.words
            else:
                break
        result[method] = found
    return result


def build_json(report: VolumeReport, target_auc: float = DEFAULT_TARGET_AUC) -> dict[str, object]:
    """Содержимое volume.json: параметры и метрики, без текстов и без строк испытаний."""
    return {
        "synthetic": report.synthetic,
        "warning": SYNTHETIC_WARNING if report.synthetic else None,
        "author_set": report.author_set,
        "parameters": report.parameters,
        "target_auc": target_auc,
        "min_reliable_words": min_reliable_words(report, target_auc),
        "skipped_slices": [{"words": w, "reason": reason} for w, reason in report.skipped],
        "slices": [
            {"words": s.words, "authors": s.authors, "trials": s.trials, "metrics": s.metrics}
            for s in report.slices
        ],
    }


def _num(value: object, digits: int = 3) -> str:
    return "—" if value is None else f"{float(value):.{digits}f}"  # type: ignore[arg-type]


def build_markdown(report: VolumeReport, target_auc: float = DEFAULT_TARGET_AUC) -> str:
    """Таблица срезов и вывод о пороге в Markdown."""
    lines = ["# Качество в зависимости от объёма текста", ""]
    if report.synthetic:
        lines += [f"> **{SYNTHETIC_WARNING}**", ""]
    author_note = "общий для всех срезов" if report.author_set == "common" else "свой на срез"
    lines += [
        "Объём — число слов у неизвестного автора и у кандидата (одинаково). "
        f"Набор авторов: {author_note}. "
        f"ДИ — 95%-й, бутстрэп по авторам. Пригодным метод считается при нижней границе ДИ для "
        f"AUC не ниже {target_auc} и покрытии не ниже {MIN_COVERAGE:.0%}.",
        "",
        "| Слов | Авторов | Испытаний | Метод | Покрытие | AUC | AUC, 95% ДИ | Точность (CV) |",
        "|---:|---:|---:|---|---:|---:|---|---:|",
    ]
    for item in report.slices:
        for entry in item.metrics.values():
            interval = entry["auc_ci95"]
            ci = "—" if interval is None else f"{interval[0]:.2f}–{interval[1]:.2f}"  # type: ignore[index]
            lines.append(
                f"| {item.words} | {item.authors} | {item.trials} | {entry['title']} "
                f"| {_num(entry['coverage'], 2)} | {_num(entry['auc'])} | {ci} "
                f"| {_num(entry['accuracy_cv'])} |"
            )
    if report.skipped:
        lines += ["", "Пропущенные срезы:", ""]
        lines += [f"- {words} слов: {reason}" for words, reason in report.skipped]

    lines += ["", f"## С какого объёма метод надёжен (AUC ≥ {target_auc})", ""]
    for method, words in min_reliable_words(report, target_auc).items():
        title = METHODS[method][0]
        verdict = f"с {words} слов" if words is not None else "на проверенных срезах не достигнуто"
        lines.append(f"- {title}: {verdict}")
    lines += [
        "",
        "Это ориентир для пересмотра порога предупреждения о малом объёме "
        "(`MIN_WORDS` в `chatstyle/pipeline.py`); решать по нему можно только на "
        "реальных данных.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(
    report: VolumeReport,
    output_dir: Path,
    target_auc: float = DEFAULT_TARGET_AUC,
    plot: bool = True,
) -> list[Path]:
    """Записать volume.json, volume.md и (если возможно) volume.png; вернуть пути."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    json_path = output_dir / "volume.json"
    json_path.write_text(
        json.dumps(build_json(report, target_auc), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    written.append(json_path)
    md_path = output_dir / "volume.md"
    md_path.write_text(build_markdown(report, target_auc), encoding="utf-8")
    written.append(md_path)
    if plot:
        try:
            from experiments.plot import save_plot
        except ImportError as exc:
            raise ChatstyleError(
                "matplotlib не установлен: pip install -e .[experiments] (или флаг --no-plot)."
            ) from exc

        png_path = output_dir / "volume.png"
        save_plot(report, png_path)
        written.append(png_path)
    return written


def _matplotlib_available() -> bool:
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        return False
    return True


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Качество методов в зависимости от объёма.")
    parser.add_argument("dataset", type=Path, help="папка: по файлу .txt на автора")
    parser.add_argument("--slices", type=int, nargs="+", default=list(DEFAULT_SLICES))
    parser.add_argument("--author-set", choices=AUTHOR_SETS, default="common")
    parser.add_argument("--neg-per-pos", type=int, default=1)
    parser.add_argument("--impostors", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--target-auc", type=float, default=DEFAULT_TARGET_AUC)
    parser.add_argument("--output-dir", type=Path, default=Path("experiments/results"))
    parser.add_argument("--no-plot", action="store_true", help="не строить volume.png")
    args = parser.parse_args(argv)
    numbers = [
        *args.slices,
        args.neg_per_pos,
        args.impostors,
        args.jobs,
        args.bootstrap,
        args.folds,
    ]
    if min(numbers) < 1:
        parser.error("числовые параметры должны быть не меньше 1")
    if not 0.0 < args.target_auc <= 1.0:
        parser.error("--target-auc должен быть в (0, 1]")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run_volume(
            args.dataset,
            args.slices,
            author_set=args.author_set,
            neg_per_pos=args.neg_per_pos,
            impostors=args.impostors,
            seed=args.seed,
            jobs=args.jobs,
            bootstrap=args.bootstrap,
            folds=args.folds,
        )
    except ChatstyleError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2

    if report.synthetic:
        print(SYNTHETIC_WARNING)
    plot = not args.no_plot
    if plot and not _matplotlib_available():
        print("matplotlib не установлен: график не построен (pip install -e .[experiments]).")
        plot = False
    for path in write_outputs(report, args.output_dir, args.target_auc, plot):
        print(f"Записано: {path}")
    print(build_markdown(report, args.target_auc))
    if report.synthetic:
        print(SYNTHETIC_WARNING)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
