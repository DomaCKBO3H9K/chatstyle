import json
from pathlib import Path

import pytest
from chatstyle.errors import ChatstyleError
from synthetic import other, write_lines

from experiments import volume
from experiments.make_synthetic import make_dataset
from experiments.volume import (
    DEFAULT_SLICES,
    SliceResult,
    VolumeReport,
    build_json,
    build_markdown,
    min_reliable_words,
    plan_slices,
    run_volume,
    write_outputs,
)

# --- выбор срезов и авторов ---

# ≈11 слов в строке: 200 строк ≈ 2200 слов, 100 ≈ 1100, 50 ≈ 550
LINE_COUNTS = [200, 200, 200, 200, 200, 100, 100, 50]


@pytest.fixture
def uneven_dir(tmp_path: Path) -> Path:
    for index, lines in enumerate(LINE_COUNTS):
        write_lines(tmp_path / f"a{index}.txt", other(index, 30 + index, lines))
    return tmp_path


def test_common_author_set_is_the_set_of_the_largest_slice(uneven_dir: Path) -> None:
    plan, skipped = plan_slices(uneven_dir, [200, 400, 800, 1600], "common")
    assert [words for words, _ in plan] == [200, 400, 800]
    sets = [set(dataset.segments) for _, dataset in plan]
    assert sets[0] == sets[1] == sets[2] == {f"a{i}" for i in range(5)}
    assert [words for words, _ in skipped] == [1600]
    assert "меньше 5 авторов" in skipped[0][1]


def test_per_slice_author_sets_shrink_with_volume(uneven_dir: Path) -> None:
    plan, _ = plan_slices(uneven_dir, [200, 400, 800], "per-slice")
    assert [len(dataset.segments) for _, dataset in plan] == [8, 7, 5]
    assert set(plan[2][1].segments) <= set(plan[1][1].segments) <= set(plan[0][1].segments)


def test_slices_are_sorted_and_deduplicated(uneven_dir: Path) -> None:
    plan, _ = plan_slices(uneven_dir, [800, 200, 200], "common")
    assert [words for words, _ in plan] == [200, 800]


def test_no_feasible_slice_is_an_error(uneven_dir: Path) -> None:
    with pytest.raises(ChatstyleError) as exc_info:
        plan_slices(uneven_dir, [5000, 9000])
    assert "Ни на одном срезе" in str(exc_info.value)


def test_unknown_author_set_and_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(ChatstyleError):
        plan_slices(tmp_path, [100], "bogus")
    with pytest.raises(ChatstyleError) as exc_info:
        plan_slices(tmp_path / "нет", [100])
    assert "не найдена" in str(exc_info.value)


# --- правило порога ---


def entry(title: str, ci_low: float | None, coverage: float = 1.0, auc: float = 0.9) -> dict:
    return {
        "title": title,
        "trials": 20 if coverage else 0,
        "coverage": coverage,
        "auc": auc if coverage else None,
        "auc_ci95": None if ci_low is None else [ci_low, 1.0],
        "accuracy_cv": 0.8 if coverage else None,
        "accuracy_best_threshold_optimistic": 0.85,
        "accuracy_at_0.5": None,
    }


def manual_report(
    rows: list[tuple[int, dict, dict, dict]], synthetic: bool = False
) -> VolumeReport:
    slices = tuple(
        SliceResult(
            words=words,
            authors=12,
            trials=24,
            metrics={"cosine": cosine, "delta": delta, "impostors": impostors},
        )
        for words, cosine, delta, impostors in rows
    )
    return VolumeReport(
        slices=slices,
        skipped=((5000, "меньше 5 авторов с текстом от 10000 слов"),),
        synthetic=synthetic,
        author_set="common",
        parameters={"seed": 1},
    )


@pytest.fixture
def report() -> VolumeReport:
    return manual_report(
        [
            (250, entry("Косинус", 0.50), entry("Delta", None, 0.0), entry("Imp", None, 0.0)),
            (500, entry("Косинус", 0.82), entry("Delta", 0.85), entry("Imp", 0.60, 0.5)),
            (1000, entry("Косинус", 0.90), entry("Delta", 0.70), entry("Imp", 0.95, 0.5)),
        ]
    )


def test_min_reliable_words_default_target(report: VolumeReport) -> None:
    result = min_reliable_words(report)
    assert result["cosine"] == 500  # нижняя граница ДИ >= 0.8 на 500 и на всех больших
    assert result["delta"] is None  # на самом большом срезе нижняя граница 0.70
    assert result["impostors"] is None  # покрытие 0.5 < 0.9


def test_min_reliable_words_depends_on_target(report: VolumeReport) -> None:
    assert min_reliable_words(report, target_auc=0.6)["cosine"] == 500
    assert min_reliable_words(report, target_auc=0.6)["delta"] == 500
    assert min_reliable_words(report, target_auc=0.45)["cosine"] == 250
    assert min_reliable_words(report, target_auc=0.95)["cosine"] is None


def test_reliability_must_hold_on_all_larger_slices() -> None:
    wobbly = manual_report(
        [
            (250, entry("К", 0.9), entry("D", None, 0.0), entry("I", None, 0.0)),
            (500, entry("К", 0.5), entry("D", None, 0.0), entry("I", None, 0.0)),
            (1000, entry("К", 0.9), entry("D", None, 0.0), entry("I", None, 0.0)),
        ]
    )
    assert min_reliable_words(wobbly)["cosine"] == 1000  # 250 надёжен, но 500 провалился


# --- таблица и JSON ---


def test_markdown_and_json_contents(report: VolumeReport) -> None:
    text = build_markdown(report, target_auc=0.8)
    assert "# Качество в зависимости от объёма текста" in text
    assert "| 500 | 12 | 24 | Косинус | 1.00 | 0.900 | 0.82–1.00 | 0.800 |" in text
    assert "| 250 | 12 | 24 | Delta | 0.00 | — | — | — |" in text
    assert "- Косинус: с 500 слов" in text
    assert "- Delta (минус): на проверенных срезах не достигнуто" in text
    assert "Пропущенные срезы" in text and "5000 слов" in text
    assert "СИНТЕТИЧЕСКИЕ" not in text

    data = build_json(report)
    assert data["synthetic"] is False and data["warning"] is None
    assert data["min_reliable_words"] == {"cosine": 500, "delta": None, "impostors": None}
    assert data["skipped_slices"] == [
        {"words": 5000, "reason": "меньше 5 авторов с текстом от 10000 слов"}
    ]
    assert [s["words"] for s in data["slices"]] == [250, 500, 1000]  # type: ignore[union-attr]


def test_synthetic_reports_carry_the_warning(report: VolumeReport) -> None:
    synthetic = manual_report([(250, entry("К", 0.9), entry("D", 0.9), entry("I", 0.9))], True)
    assert "СИНТЕТИЧЕСКИЕ ДАННЫЕ" in build_markdown(synthetic)
    assert "СИНТЕТИЧЕСКИЕ ДАННЫЕ" in str(build_json(synthetic)["warning"])


# --- запись файлов и график ---


def test_write_outputs_without_plot(report: VolumeReport, tmp_path: Path) -> None:
    written = write_outputs(report, tmp_path / "out", plot=False)
    assert sorted(path.name for path in written) == ["volume.json", "volume.md"]
    data = json.loads((tmp_path / "out" / "volume.json").read_text(encoding="utf-8"))
    assert data["target_auc"] == 0.8


def test_plot_file_is_a_png(report: VolumeReport, tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    written = write_outputs(report, tmp_path, plot=True)
    png = tmp_path / "volume.png"
    assert png in written
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert png.stat().st_size > 10_000


def texts_of(figure) -> list[str]:  # noqa: ANN001
    return [text.get_text() for text in figure.texts]


def test_plot_watermark_only_for_synthetic_data(report: VolumeReport) -> None:
    pytest.importorskip("matplotlib")
    from experiments.plot import WATERMARK, build_figure

    assert WATERMARK not in texts_of(build_figure(report))
    synthetic = manual_report(
        [(250, entry("К", 0.9), entry("D", 0.9), entry("I", 0.9))], synthetic=True
    )
    figure = build_figure(synthetic)
    assert WATERMARK in texts_of(figure)
    assert any("синтетика" in text for text in texts_of(figure))


def test_plot_skips_unavailable_methods_and_mentions_them(report: VolumeReport) -> None:
    pytest.importorskip("matplotlib")
    from experiments.plot import build_figure

    figure = build_figure(report)
    left = figure.axes[0]
    _, labels = left.get_legend_handles_labels()
    assert labels == ["Косинус", "Delta (минус)", "Impostors (итог)"]
    note = next(text for text in texts_of(figure) if text.startswith("Нет точки"))
    assert "Delta (минус): 250" in note and "Impostors (итог): 250" in note

    only_cosine = manual_report(
        [(250, entry("К", 0.9), entry("D", None, 0.0), entry("I", None, 0.0))]
    )
    _, only_labels = build_figure(only_cosine).axes[0].get_legend_handles_labels()
    assert only_labels == ["Косинус"]


# --- сквозные запуски ---


def test_run_volume_end_to_end_on_synthetic(tmp_path: Path) -> None:
    make_dataset(tmp_path / "data", authors=6, messages=300, seed=1, blend=0.5)
    kwargs = {"slices": [150, 300], "bootstrap": 30, "folds": 3}
    one = run_volume(tmp_path / "data", jobs=1, **kwargs)  # type: ignore[arg-type]
    two = run_volume(tmp_path / "data", jobs=2, **kwargs)  # type: ignore[arg-type]
    assert one.synthetic is True
    assert [s.words for s in one.slices] == [150, 300]
    assert all(s.authors == 6 and s.trials == 12 for s in one.slices)
    assert set(one.slices[0].metrics) == {"cosine", "delta", "impostors"}
    assert build_json(one) == build_json(two)  # результат не зависит от числа процессов


def test_main_writes_files_and_warns(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_dataset(tmp_path / "data", authors=6, messages=300, seed=1, blend=0.5)
    out = tmp_path / "out"
    code = volume.main(
        [str(tmp_path / "data"), "--slices", "150", "300", "--bootstrap", "30", "--folds", "3"]
        + ["--output-dir", str(out), "--no-plot"]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert printed.count("СИНТЕТИЧЕСКИЕ ДАННЫЕ") >= 2
    assert (out / "volume.json").exists() and (out / "volume.md").exists()
    assert not (out / "volume.png").exists()


def test_main_without_synthetic_marker_has_no_warning(
    uneven_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = volume.main(
        [str(uneven_dir), "--slices", "200", "--bootstrap", "30", "--folds", "3"]
        + ["--output-dir", str(tmp_path / "out"), "--no-plot"]
    )
    assert code == 0
    assert "СИНТЕТИЧЕСКИЕ" not in capsys.readouterr().out


def test_main_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert volume.main([str(tmp_path / "нет")]) == 2
    assert "Ошибка:" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        volume.main([str(tmp_path), "--slices", "0"])
    with pytest.raises(SystemExit):
        volume.main([str(tmp_path), "--target-auc", "1.5"])


def test_default_slices_match_the_plan() -> None:
    assert DEFAULT_SLICES == (250, 500, 1000, 2000, 5000)
