from pathlib import Path

from chatstyle.cli import app
from chatstyle.collectors.impostors import load_impostor_directory
from chatstyle.delta import DeltaScore
from chatstyle.impostors import ImpostorsScore
from chatstyle.pipeline import (
    METHOD_COSINE,
    METHOD_DELTA,
    METHOD_ENSEMBLE,
    METHOD_IMPOSTORS,
    AuthorStats,
    CandidateResult,
    ComparisonResult,
    best_methods_text,
    delta_text,
    final_score_text,
    ranking_text,
    run_comparison,
    unavailable_notes,
)
from synthetic import write_lines, write_workspace
from typer.testing import CliRunner

runner = CliRunner()


def spec(path: Path) -> str:
    return f"file:{path}"


def invoke(args: list[str]):  # noqa: ANN201
    return runner.invoke(app, args, env={"COLUMNS": "220"})


# --- конвейер ---


def test_all_three_methods_with_impostors(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    result = run_comparison(
        spec(files["unknown"]),
        [spec(files["other"]), spec(files["same"])],
        impostors=load_impostor_directory(files["impostors"]),
    )
    same, other = result.candidates
    assert same.label == spec(files["same"])  # сортировка по смеси методов
    assert result.ranked_by == METHOD_ENSEMBLE
    assert result.impostor_count == 4
    assert result.seed == 1
    assert same.final_score is not None and same.final_score > 0.9
    assert other.final_score is not None and other.final_score < 0.2
    assert same.delta is not None and other.delta is not None
    assert same.delta.available and same.delta.delta < other.delta.delta
    assert same.similarity > other.similarity
    assert unavailable_notes(result) == []
    assert result.best_by_method() == {
        METHOD_COSINE: (same.label,),
        METHOD_DELTA: (same.label,),
        METHOD_IMPOSTORS: (same.label,),
        METHOD_ENSEMBLE: (same.label,),
    }
    assert result.methods_agree() is True


def test_without_impostors_only_cosine_and_delta(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    result = run_comparison(spec(files["unknown"]), [spec(files["other"]), spec(files["same"])])
    assert result.ranked_by == METHOD_ENSEMBLE
    assert result.impostor_count == 0
    for candidate in result.candidates:
        assert candidate.final_score is None
        assert candidate.impostors_score is not None
        assert candidate.impostors_score.impostors == 1  # остальной кандидат
        assert candidate.delta is not None and candidate.delta.available
    (note,) = unavailable_notes(result)
    assert "посторонних авторов 1 из 3" in note
    assert "--impostors DIR" in note
    assert set(result.best_by_method()) == {METHOD_COSINE, METHOD_DELTA, METHOD_ENSEMBLE}


def test_seed_affects_only_impostors(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    impostors = load_impostor_directory(files["impostors"])
    candidates = [spec(files["same"]), spec(files["other"])]
    first = run_comparison(spec(files["unknown"]), candidates, impostors=impostors, seed=1)
    again = run_comparison(spec(files["unknown"]), candidates, impostors=impostors, seed=1)
    second = run_comparison(spec(files["unknown"]), candidates, impostors=impostors, seed=2)
    assert first == again
    assert second.seed == 2
    for one, two in zip(first.candidates, second.candidates, strict=True):
        assert one.similarity == two.similarity
        assert one.delta == two.delta


def test_partial_availability_ranks_by_cosine_without_the_mix(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    tiny = write_lines(tmp_path / "tiny.txt", ["ну привет))", "щас приду"])
    result = run_comparison(
        spec(files["unknown"]),
        [spec(tiny), spec(files["same"])],
        impostors=load_impostor_directory(files["impostors"]),
        ensemble=False,
    )
    by_label = {row.label: row for row in result.candidates}
    assert by_label[spec(files["same"])].final_score is not None
    assert by_label[spec(tiny)].final_score is None
    assert result.ranked_by == METHOD_COSINE
    assert METHOD_IMPOSTORS not in result.best_by_method()  # не у всех кандидатов
    assert any("слишком мало текста" in note for note in unavailable_notes(result))


# --- текстовые помощники ---


def candidate(
    label: str,
    similarity: float,
    delta: float | None = None,
    score: float | None = None,
) -> CandidateResult:
    return CandidateResult(
        label=label,
        words=2000,
        messages=100,
        similarity=similarity,
        delta=None if delta is None else DeltaScore(True, delta, 20, ()),
        impostors_score=None if score is None else ImpostorsScore(True, score, 5, 100),
    )


def comparison(*rows: CandidateResult, ranked_by: str = METHOD_COSINE) -> ComparisonResult:
    return ComparisonResult(
        unknown_label="u", unknown=AuthorStats(2000, 100), candidates=rows, ranked_by=ranked_by
    )


def test_formatters() -> None:
    full = candidate("a", 0.5, delta=0.1234, score=0.874)
    assert delta_text(full) == "0.12"
    assert final_score_text(full) == "0.87"
    bare = candidate("b", 0.3)
    assert delta_text(bare) == "—"
    assert final_score_text(bare) == "—"
    missing = CandidateResult(
        "c",
        1,
        1,
        0.1,
        delta=DeltaScore(False, 0.0, 0, ()),
        impostors_score=ImpostorsScore(False, 0.0, 1, 0),
    )
    assert delta_text(missing) == "—"
    assert final_score_text(missing) == "—"


def test_ranking_text() -> None:
    assert "по итоговой оценке" in ranking_text(comparison(ranked_by=METHOD_IMPOSTORS))
    assert "по косинусному сходству" in ranking_text(comparison())


def test_agreement_and_disagreement_text() -> None:
    agree = comparison(candidate("a", 0.6, 0.1, 0.9), candidate("b", 0.3, 0.5, 0.1))
    assert best_methods_text(agree) == (
        "Лучший по методам: косинус — a; Delta — a; Impostors — a (методы согласны)."
    )
    disagree = comparison(candidate("a", 0.6, 0.5, 0.2), candidate("b", 0.3, 0.1, 0.8))
    assert disagree.methods_agree() is False
    assert best_methods_text(disagree) == (
        "Лучший по методам: косинус — a; Delta — b; Impostors — b (методы расходятся)."
    )


def test_single_method_has_no_agreement_line() -> None:
    only_cosine = comparison(candidate("a", 0.6), candidate("b", 0.3))
    assert only_cosine.methods_agree() is None
    assert best_methods_text(only_cosine) is None


def test_ties_keep_all_best_candidates() -> None:
    tied = comparison(candidate("a", 0.5, 0.2, 0.7), candidate("b", 0.5, 0.2, 0.7))
    assert tied.best_by_method()[METHOD_COSINE] == ("a", "b")
    assert tied.methods_agree() is True


# --- CLI ---


def test_cli_full_table_and_summary(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    result = invoke(
        [
            "compare",
            "-u",
            spec(files["unknown"]),
            "-c",
            spec(files["other"]),
            "-c",
            spec(files["same"]),
            "--impostors",
            str(files["impostors"]),
        ]
    )
    assert result.exit_code == 0
    out = result.output
    assert "Impostors (итог)" in out
    assert out.index("same.txt", out.index("Кандидат")) < out.index(
        "other.txt", out.index("Кандидат")
    )
    assert (
        "Порядок: по смеси методов (языковая модель, слова, каркас служебных слов, Delta)." in out
    )
    assert "(методы согласны)" in out
    assert "недоступ" not in out


def test_cli_dashes_and_hint_without_impostors(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    result = invoke(
        [
            "compare",
            "-u",
            spec(files["unknown"]),
            "-c",
            spec(files["other"]),
            "-c",
            spec(files["same"]),
        ]
    )
    assert result.exit_code == 0
    assert "—" in result.output
    assert (
        "Порядок: по смеси методов (языковая модель, слова, каркас служебных слов, Delta)."
        in result.output
    )
    assert "посторонних авторов 1 из 3" in result.output
    assert "--impostors DIR" in result.output


def test_cli_seed_option(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    base = ["compare", "-u", spec(files["unknown"]), "-c", spec(files["same"])]
    base += ["--impostors", str(files["impostors"])]
    assert invoke([*base, "--seed", "7"]).exit_code == 0
    assert invoke([*base, "--seed", "-1"]).exit_code == 2


def test_cli_missing_impostor_directory_fails_before_collecting(tmp_path: Path) -> None:
    result = invoke(
        [
            "compare",
            "-u",
            "file:nope_xyz.txt",
            "-c",
            "file:nope_abc.txt",
            "--impostors",
            str(tmp_path / "нет"),
        ]
    )
    assert result.exit_code == 2
    assert "Папка с посторонними текстами не найдена" in result.output
    assert "nope_xyz" not in result.output


def test_report_contains_methods_and_no_impostor_file_names(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    report = tmp_path / "report.md"
    result = invoke(
        [
            "compare",
            "-u",
            spec(files["unknown"]),
            "-c",
            spec(files["other"]),
            "-c",
            spec(files["same"]),
            "--impostors",
            str(files["impostors"]),
            "--seed",
            "5",
            "--report",
            str(report),
        ]
    )
    assert result.exit_code == 0
    text = report.read_text(encoding="utf-8")
    assert "| Кандидат | Слов | Сообщений | Сходство (косинус) | Delta | Итоговая оценка |" in text
    assert "## Итоговая оценка" in text
    assert "## Чем различаются стили (Burrows Delta)" in text
    assert "доля сообщений с заглавной буквы" in text  # читаемое название признака Delta
    assert "seed 5; посторонних авторов из папки: 4" in text
    assert "(методы согласны)" in text
    assert "General Impostors." in text  # описание метода
    for index in range(4):
        assert f"o{index}.txt" not in text  # имена файлов папки в отчёт не попадают


def test_html_report_for_partial_availability(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    report = tmp_path / "report.html"
    result = invoke(
        [
            "compare",
            "-u",
            spec(files["unknown"]),
            "-c",
            spec(files["same"]),
            "--report",
            str(report),
        ]
    )
    assert result.exit_code == 0
    text = report.read_text(encoding="utf-8")
    assert '<th class="num">Итоговая оценка</th>' in text
    assert '<td class="num">—</td>' in text
    assert "посторонних авторов 0 из 3" in text
