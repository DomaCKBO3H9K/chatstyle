import json
from pathlib import Path

import pytest
from chatstyle.collectors.tg_export import read_tg_export_by_sender
from chatstyle.errors import ChatstyleError
from chatstyle.pipeline import compare_messages, run_comparison
from synthetic import casual, formal, other, write_lines

from experiments import evaluate, prepare_tgexport
from experiments.make_synthetic import make_dataset
from experiments.trials import (
    MIN_AUTHORS,
    SYNTHETIC_MARKER,
    build_trials,
    load_dataset,
    split_segments,
)

FIXTURES = Path(__file__).parent / "fixtures"


# --- compare_messages: общая часть CLI и оценки ---


def test_compare_messages_matches_run_comparison(tmp_path: Path) -> None:
    unknown = write_lines(tmp_path / "u.txt", casual(1))
    same = write_lines(tmp_path / "s.txt", casual(2))
    diff = write_lines(tmp_path / "d.txt", formal(3))
    impostors = {f"o{i}": other(i, 10 + i) for i in range(4)}
    full = run_comparison(
        f"file:{unknown}", [f"file:{diff}", f"file:{same}"], impostors=impostors, seed=3
    )
    rows, ranked_by = compare_messages(
        casual(1),
        {f"file:{diff}": formal(3), f"file:{same}": casual(2)},
        impostors=impostors,
        seed=3,
    )
    assert ranked_by == full.ranked_by
    assert [row.label for row in rows] == [row.label for row in full.candidates]
    for ours, theirs in zip(rows, full.candidates, strict=True):
        assert ours.similarity == theirs.similarity
        assert ours.delta == theirs.delta
        assert ours.impostors_score == theirs.impostors_score


def test_compare_messages_can_skip_explanations() -> None:
    rows, _ = compare_messages(
        casual(1), {"a": casual(2)}, impostors=None, top_features=0, top_differences=0
    )
    assert rows[0].top_features == ()
    assert rows[0].delta is not None and rows[0].delta.differences == ()


# --- нарезка на куски ---


def test_split_segments_are_consecutive_and_disjoint() -> None:
    messages = ["a b", "c", "d e f", "g", "h i"]
    parts = split_segments(messages, words=3)
    assert parts == (["a b", "c"], ["d e f"])


def test_split_segments_needs_enough_text() -> None:
    assert split_segments(["a b", "c", "d e f"], words=4) is None  # на второй кусок не хватает
    assert split_segments([], words=1) is None


# --- загрузка датасета ---


def write_authors(directory: Path, count: int, messages: int = 120) -> None:
    directory.mkdir(exist_ok=True)
    for index in range(count):
        write_lines(directory / f"a{index:02d}.txt", other(index, 20 + index, messages))


def test_load_dataset_splits_and_preprocesses(tmp_path: Path) -> None:
    write_authors(tmp_path, 6)
    lines = other(0, 20, 120)
    write_lines(tmp_path / "a00.txt", ["https://a.ru", "[Фото]", *lines])
    dataset = load_dataset(tmp_path, words=200)
    first, second = dataset.segments["a00"]
    assert first[0] == lines[0]  # ссылка и заполнитель отброшены предобработкой
    assert first + second == lines[: len(first) + len(second)]  # подряд и без пересечений
    assert len(dataset.segments) == 6
    assert dataset.skipped == ()
    assert dataset.synthetic is False


def test_load_dataset_skips_short_authors_and_detects_marker(tmp_path: Path) -> None:
    write_authors(tmp_path, 6)
    write_lines(tmp_path / "tiny.txt", ["привет"])
    (tmp_path / SYNTHETIC_MARKER).write_text("x", encoding="utf-8")
    (tmp_path / "notes.md").write_text("не автор", encoding="utf-8")
    dataset = load_dataset(tmp_path, words=200)
    assert "tiny" not in dataset.segments
    assert dataset.skipped == ("tiny",)
    assert dataset.synthetic is True
    assert "notes" not in dataset.segments


def test_load_dataset_errors(tmp_path: Path) -> None:
    with pytest.raises(ChatstyleError) as exc_info:
        load_dataset(tmp_path / "нет", words=100)
    assert "не найдена" in str(exc_info.value)

    with pytest.raises(ChatstyleError) as exc_info:
        load_dataset(tmp_path, words=100)
    assert "нет файлов .txt" in str(exc_info.value)

    write_authors(tmp_path, MIN_AUTHORS - 1)
    with pytest.raises(ChatstyleError) as exc_info:
        load_dataset(tmp_path, words=100)
    assert f"не меньше {MIN_AUTHORS} авторов" in str(exc_info.value)

    (tmp_path / "bad.txt").write_bytes("привет".encode("cp1251"))
    with pytest.raises(ChatstyleError) as exc_info:
        load_dataset(tmp_path, words=100)
    assert "UTF-8" in str(exc_info.value)


# --- испытания ---

AUTHORS = [f"a{i:02d}" for i in range(8)]


def test_trials_are_balanced_and_well_formed() -> None:
    trials = build_trials(AUTHORS, neg_per_pos=2, impostor_count=3, seed=1)
    assert len(trials) == len(AUTHORS) * 3
    assert sum(t.same for t in trials) == len(AUTHORS)
    assert [t.index for t in trials] == list(range(len(trials)))
    for trial in trials:
        assert (trial.unknown_author == trial.candidate_author) is trial.same
        assert trial.unknown_author not in trial.impostor_authors
        assert trial.candidate_author not in trial.impostor_authors
        assert len(trial.impostor_authors) == len(set(trial.impostor_authors)) == 3
    for author in AUTHORS:
        negatives = [
            t.candidate_author for t in trials if t.unknown_author == author and not t.same
        ]
        assert len(negatives) == len(set(negatives)) == 2


def test_trials_depend_only_on_authors_and_seed() -> None:
    first = build_trials(AUTHORS, seed=7)
    assert first == build_trials(list(reversed(AUTHORS)), seed=7)
    assert first != build_trials(AUTHORS, seed=8)


def test_trials_clip_impostors_and_negatives_to_available_authors() -> None:
    trials = build_trials(AUTHORS[:5], neg_per_pos=10, impostor_count=50, seed=1)
    assert len(trials) == 5 * (1 + 4)  # у каждого автора только четыре «чужих»
    positive = next(t for t in trials if t.same)
    assert len(positive.impostor_authors) == 4  # все, кроме самого автора
    negative = next(t for t in trials if not t.same)
    assert len(negative.impostor_authors) == 3


def test_trials_need_enough_authors() -> None:
    with pytest.raises(ChatstyleError):
        build_trials(AUTHORS[: MIN_AUTHORS - 1])


# --- оценка ---


def result(index: int, same: bool, cosine: float, delta: float | None, score: float | None):  # noqa: ANN201
    return evaluate.TrialResult(index, same, f"a{index % 4}", "x", cosine, delta, score)


def test_summarize_hand_computed_metrics() -> None:
    rows = [
        result(0, True, 0.9, 0.2, 0.9),
        result(1, True, 0.8, 0.4, 0.7),
        result(2, False, 0.3, 1.5, 0.2),
        result(3, False, 0.7, 0.9, None),  # Impostors недоступен для одного испытания
        result(4, True, 0.6, None, None),  # Delta недоступна
        result(5, False, 0.1, 2.0, 0.4),
    ]
    summary = evaluate.summarize(rows, seed=1, resamples=50, folds=2)
    assert summary["cosine"]["trials"] == 6
    assert summary["cosine"]["coverage"] == 1.0
    # косинус: положительные 0.9, 0.8, 0.6; отрицательные 0.3, 0.7, 0.1 -> 8 побед из 9
    assert summary["cosine"]["auc"] == pytest.approx(8 / 9)
    assert summary["delta"]["trials"] == 5
    assert summary["delta"]["coverage"] == pytest.approx(5 / 6)
    assert summary["delta"]["auc"] == 1.0  # меньшая Delta у пар от одного автора
    assert summary["impostors"]["trials"] == 4
    assert summary["impostors"]["auc"] == 1.0
    assert summary["impostors"]["accuracy_at_0.5"] == 1.0  # 0.9 и 0.7 >= 0.5, 0.2 и 0.4 < 0.5
    assert summary["cosine"]["accuracy_at_0.5"] is None  # только у Impostors есть шкала 0..1


def test_format_summary_marks_optimistic_column() -> None:
    summary = evaluate.summarize([result(i, i % 2 == 0, i / 10, i / 5, i / 10) for i in range(8)])
    text = evaluate.format_summary(summary)
    assert "Косинус" in text and "Impostors (итог)" in text
    assert "оптимистично" in text


# --- сквозной запуск на синтетике ---


@pytest.fixture
def synthetic_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "data"
    make_dataset(directory, authors=6, messages=250, seed=1, blend=0.5)
    return directory


def run_main(directory: Path, output: Path, *extra: str) -> int:
    args = [str(directory), "--words", "600", "--bootstrap", "50", "--output", str(output)]
    return evaluate.main([*args, *extra])


def test_end_to_end_report_has_no_texts_and_warns_about_synthetic(
    synthetic_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "results.json"
    assert run_main(synthetic_dir, output) == 0
    printed = capsys.readouterr().out
    assert printed.count("СИНТЕТИЧЕСКИЕ ДАННЫЕ") == 2
    assert "Косинус" in printed

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["dataset"] == {"authors": 6, "skipped_authors": 0, "synthetic": True}
    assert report["trials_total"] == 12
    assert report["trials_same"] == 6
    assert report["parameters"]["words"] == 600
    assert set(report["metrics"]) == {"cosine", "delta", "impostors"}
    for trial in report["trials"]:
        assert set(trial) == {
            "index",
            "same",
            "unknown_author",
            "candidate_author",
            "cosine",
            "delta",
            "impostors",
        }
        assert trial["unknown_author"].startswith("a")  # анонимный id, не текст
    assert report["metrics"]["cosine"]["auc"] > 0.8  # лёгкий синтетический набор


def test_results_do_not_depend_on_the_number_of_jobs(synthetic_dir: Path, tmp_path: Path) -> None:
    one = tmp_path / "one.json"
    two = tmp_path / "two.json"
    assert run_main(synthetic_dir, one, "--jobs", "1") == 0
    assert run_main(synthetic_dir, two, "--jobs", "2") == 0
    assert json.loads(one.read_text(encoding="utf-8")) == json.loads(
        two.read_text(encoding="utf-8")
    )


def test_main_reports_dataset_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert evaluate.main([str(tmp_path / "нет")]) == 2
    assert "Ошибка:" in capsys.readouterr().err


def test_main_validates_numeric_parameters(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        evaluate.main([str(tmp_path), "--words", "0"])


def test_synthetic_generator_is_deterministic_and_marked(tmp_path: Path) -> None:
    make_dataset(tmp_path / "x", authors=3, messages=20, seed=2)
    make_dataset(tmp_path / "y", authors=3, messages=20, seed=2)
    assert (tmp_path / "x" / SYNTHETIC_MARKER).exists()
    for name in ("a001.txt", "a002.txt", "a003.txt"):
        assert (tmp_path / "x" / name).read_text(encoding="utf-8") == (
            tmp_path / "y" / name
        ).read_text(encoding="utf-8")
    assert (tmp_path / "x" / "a001.txt").read_text(encoding="utf-8") != (
        tmp_path / "x" / "a002.txt"
    ).read_text(encoding="utf-8")


# --- подготовка датасета из группового чата ---


def test_read_tg_export_by_sender() -> None:
    senders = read_tg_export_by_sender(FIXTURES / "result.json")
    assert list(senders) == ["user111", "user222"]
    assert senders["user111"][0] == "привет))"
    assert len(senders["user111"]) == 5  # пересланное, стикер и пустое пропущены
    assert senders["user222"] == ["Привет. Как дела?", "Посмотрю вечером.", "ок"]


def test_prepare_tgexport_anonymizes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    directory = tmp_path / "dataset"
    code = prepare_tgexport.main(
        [str(FIXTURES / "result.json"), str(directory), "--min-messages", "3"]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert "a001: 5 сообщений" in printed and "a002: 3 сообщений" in printed
    for name in ("Анна", "Борис", "user111", "user222"):
        assert name not in printed
    first = (directory / "a001.txt").read_text(encoding="utf-8").splitlines()
    assert len(first) == 5
    assert first[-1] == "ладно)) щас дойду"  # перевод строки внутри сообщения заменён
    assert sorted(path.name for path in directory.iterdir()) == ["a001.txt", "a002.txt"]


def test_prepare_tgexport_min_messages_and_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = str(FIXTURES / "result.json")
    assert prepare_tgexport.main([export, str(tmp_path / "one"), "--min-messages", "4"]) == 0
    assert [p.name for p in (tmp_path / "one").iterdir()] == ["a001.txt"]
    assert prepare_tgexport.main([export, str(tmp_path / "none"), "--min-messages", "99"]) == 2
    assert "Ошибка:" in capsys.readouterr().err
    assert not (tmp_path / "none").exists()
