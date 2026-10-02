"""Тесты для experiments/ablation.py."""

import json
from pathlib import Path

import pytest
from chatstyle.features import ALL_STYLE_GROUPS

from experiments.ablation import VARIANTS, format_table, main, run_ablation
from experiments.make_synthetic import make_dataset


def _make_dataset(
    tmp_path: Path, authors: int = 6, messages: int = 300, blend: float = 0.5
) -> Path:
    directory = tmp_path / "data"
    make_dataset(directory, authors=authors, messages=messages, seed=3, blend=blend, habits=True)
    return directory


def test_variants_order_and_groups():
    names = [name for name, _ in VARIANTS]
    assert names == ["none", "punctuation", "orthography", "words", "sentences", "all"]
    groups_by_name = dict(VARIANTS)
    assert groups_by_name["none"] == ()
    assert groups_by_name["all"] == ALL_STYLE_GROUPS


def test_run_ablation_returns_six_rows_and_synthetic(tmp_path: Path):
    dataset_dir = _make_dataset(tmp_path)
    rows, synthetic = run_ablation(
        dataset_dir,
        words=700,
        impostors=3,
        bootstrap=20,
        folds=2,
    )
    assert synthetic is True
    assert len(rows) == 6
    for row in rows:
        assert set(row.keys()) == {
            "variant",
            "groups",
            "trials",
            "coverage",
            "auc",
            "auc_ci95",
        }
    by_name = {row["variant"]: row for row in rows}
    assert by_name["all"]["trials"] > 0
    assert by_name["none"]["trials"] > 0


def test_run_ablation_reproducible(tmp_path: Path):
    dataset_dir = _make_dataset(tmp_path)
    first = run_ablation(
        dataset_dir,
        words=700,
        impostors=3,
        bootstrap=20,
        folds=2,
    )
    second = run_ablation(
        dataset_dir,
        words=700,
        impostors=3,
        bootstrap=20,
        folds=2,
    )
    assert first == second


def test_groups_change_delta_auc(tmp_path: Path):
    dataset_dir = _make_dataset(tmp_path, authors=12, messages=500, blend=0.8)
    rows, _ = run_ablation(
        dataset_dir,
        words=700,
        impostors=3,
        bootstrap=20,
        folds=2,
    )
    by_name = {row["variant"]: row for row in rows}
    auc_all = by_name["all"]["auc"]
    auc_none = by_name["none"]["auc"]
    assert auc_all is not None
    assert auc_none is not None
    assert auc_all != auc_none


def test_format_table_contains_variants_and_none_marker(tmp_path: Path):
    dataset_dir = _make_dataset(tmp_path)
    rows, _ = run_ablation(
        dataset_dir,
        words=700,
        impostors=3,
        bootstrap=20,
        folds=2,
    )
    table = format_table(rows)
    for name, _ in VARIANTS:
        assert name in table
    assert "AUC" in table
    # None выводится как «—»
    none_row = next(row for row in rows if row["variant"] == "none")
    if none_row["auc"] is None:
        assert "—" in table


def test_main_writes_json_and_returns_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    dataset_dir = _make_dataset(tmp_path)
    json_path = tmp_path / "out.json"
    rc = main(
        [
            str(dataset_dir),
            "--words",
            "700",
            "--impostors",
            "3",
            "--bootstrap",
            "20",
            "--folds",
            "2",
            "--output",
            str(json_path),
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    for name, _ in VARIANTS:
        assert name in captured.out
    assert json_path.exists()
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["synthetic"] is True
    assert len(report["rows"]) == 6


def test_main_missing_dataset_returns_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    missing = tmp_path / "nonexistent"
    rc = main([str(missing)])
    assert rc == 2
    captured = capsys.readouterr()
    assert "Ошибка:" in captured.err
