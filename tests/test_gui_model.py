import threading
import time
from pathlib import Path

import pytest
from chatstyle.collectors.tg_export import TgSender, list_tg_senders
from chatstyle.errors import ChatstyleError
from chatstyle.features import FEATURE_LABELS, top_words, word_list_lines
from chatstyle.gui.model import (
    PROFILE_COLUMNS,
    RESULT_COLUMNS,
    BackgroundJob,
    CompareForm,
    build_profile_view,
    build_result_view,
    normalize_source,
    run_compare,
    run_profile,
    short_labels,
    tgexport_spec,
    validate_compare_form,
)
from chatstyle.pipeline import DISCLAIMER, profile_author, run_comparison
from synthetic import write_workspace

FIXTURES = Path(__file__).parent / "fixtures"


def form(**changes: object) -> CompareForm:
    base = {"unknown": "file:u.txt", "candidates": ("file:a.txt", "file:b.txt")}
    return CompareForm(**{**base, **changes})  # type: ignore[arg-type]


# --- источники ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("chat.txt", "file:chat.txt"),
        ("  chat.txt  ", "file:chat.txt"),
        ('"C:\\Users\\me\\my chat.txt"', "file:C:\\Users\\me\\my chat.txt"),
        ("C:\\data\\a.txt", "file:C:\\data\\a.txt"),  # буква диска не принимается за схему
        ("file:chat.txt", "file:chat.txt"),
        ("FILE:chat.txt", "FILE:chat.txt"),
        ("tg:@friend", "tg:@friend"),
        ("tgexport:r.json#Анна", "tgexport:r.json#Анна"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalize_source(text: str, expected: str) -> None:
    assert normalize_source(text) == expected


def test_tgexport_spec_prefers_unique_name_else_id() -> None:
    anna = TgSender("user1", "Анна", 5)
    twin_a, twin_b = TgSender("user2", "Борис", 3), TgSender("user3", "Борис", 2)
    hashed = TgSender("user4", "Вася #1", 1)
    senders = [anna, twin_a, twin_b, hashed]
    assert tgexport_spec("r.json", anna, senders) == "tgexport:r.json#Анна"
    assert tgexport_spec("r.json", twin_a, senders) == "tgexport:r.json#user2"
    assert tgexport_spec("r.json", hashed, senders) == "tgexport:r.json#user4"


def test_list_tg_senders_orders_by_activity_and_skips_noise() -> None:
    senders = list_tg_senders(FIXTURES / "result.json")
    assert [(s.key, s.name, s.messages) for s in senders] == [
        ("user111", "Анна Петрова", 5),
        ("user222", "Борис", 3),
    ]


# --- проверка формы ---


def test_valid_form_has_no_errors(tmp_path: Path) -> None:
    folder = tmp_path / "x"
    folder.mkdir()
    ok = form(impostors_dir=str(folder), report_path=str(tmp_path / "r.html"), seed=7)
    assert validate_compare_form(ok) == []


def test_form_errors_are_listed_together() -> None:
    errors = validate_compare_form(
        form(unknown="", candidates=(), seed=None, report_path="r.txt", impostors_dir="/no/such")
    )
    text = "\n".join(errors)
    assert "Укажите неизвестного автора" in text
    assert "хотя бы одного кандидата" in text
    assert "Seed" in text
    assert "Папка с чужими текстами не найдена" in text
    assert "Неизвестный формат отчёта" in text


def test_duplicate_and_self_candidates_are_reported() -> None:
    errors = validate_compare_form(
        form(unknown="file:u.txt", candidates=("file:a.txt", "file:a.txt", "file:u.txt"))
    )
    text = "\n".join(errors)
    assert "Кандидат указан дважды: file:a.txt" in text
    assert "совпадают: file:u.txt" in text


def test_negative_seed_is_rejected() -> None:
    assert any("Seed" in error for error in validate_compare_form(form(seed=-1)))
    assert validate_compare_form(form(seed=0)) == []


# --- запуск ---


def test_run_compare_with_fixtures_and_report(tmp_path: Path) -> None:
    report = tmp_path / "report.html"
    outcome = run_compare(
        CompareForm(
            unknown=f"file:{FIXTURES / 'unknown.txt'}",
            candidates=(f"file:{FIXTURES / 'same.txt'}", f"file:{FIXTURES / 'other.txt'}"),
            report_path=str(report),
        )
    )
    assert outcome.report_path == report
    assert "<h1>Отчёт chatstyle</h1>" in report.read_text(encoding="utf-8")
    assert [c.label.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] for c in outcome.result.candidates] == [
        "same.txt",
        "other.txt",
    ]


def test_run_compare_with_impostors_gives_final_scores(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    outcome = run_compare(
        CompareForm(
            unknown=f"file:{files['unknown']}",
            candidates=(f"file:{files['same']}", f"file:{files['other']}"),
            impostors_dir=str(files["impostors"]),
            seed=3,
        )
    )
    same, other = outcome.result.candidates
    assert same.final_score is not None and other.final_score is not None
    assert same.final_score > other.final_score
    assert outcome.result.seed == 3
    assert outcome.report_path is None


def test_run_compare_reports_all_form_errors() -> None:
    with pytest.raises(ChatstyleError) as exc_info:
        run_compare(form(unknown="", candidates=()))
    assert "Укажите неизвестного автора" in str(exc_info.value)
    assert "хотя бы одного кандидата" in str(exc_info.value)


def test_run_compare_propagates_source_errors() -> None:
    with pytest.raises(ChatstyleError) as exc_info:
        run_compare(form(unknown="file:nope_xyz.txt", candidates=("file:nope_abc.txt",)))
    assert "nope_xyz" in str(exc_info.value)


def test_run_profile() -> None:
    profile = run_profile(str(FIXTURES / "same.txt"))  # голый путь превращается в file:
    assert profile.stats.messages == 19
    with pytest.raises(ChatstyleError):
        run_profile("  ")


# --- представления ---


def test_result_view_matches_the_terminal_texts() -> None:
    result = run_comparison(
        f"file:{FIXTURES / 'unknown.txt'}",
        [f"file:{FIXTURES / 'same.txt'}", f"file:{FIXTURES / 'other.txt'}"],
    )
    view = build_result_view(result)
    assert view.columns == RESULT_COLUMNS
    assert [row[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1] for row in view.rows] == [
        "same.txt",
        "other.txt",
    ]
    assert view.rows[0][1:] == ("79", "19", "0.643", "—", "—")
    assert view.notes[0] == "Порядок: по косинусному сходству (итоговая оценка недоступна)."
    assert any("Burrows Delta недоступна" in note for note in view.notes)
    assert any("посторонних авторов 1 из 3" in note for note in view.notes)
    assert view.warning is not None and "меньше 1000 слов" in view.warning
    assert view.disclaimer == DISCLAIMER
    assert view.unknown_line.endswith("— 81 слов, 19 сообщений")


def test_result_view_with_all_methods(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    outcome = run_compare(
        CompareForm(
            unknown=f"file:{files['unknown']}",
            candidates=(f"file:{files['same']}", f"file:{files['other']}"),
            impostors_dir=str(files["impostors"]),
        )
    )
    view = build_result_view(outcome.result)
    assert (
        view.notes[0]
        == "Порядок: по Delta (косинус профилей стиля); General Impostors показан отдельно."
    )
    assert "(методы согласны)" in view.notes[1]
    assert all("недоступ" not in note for note in view.notes)
    assert float(view.rows[0][5]) > float(view.rows[1][5])


def test_profile_view() -> None:
    view = build_profile_view(profile_author(f"file:{FIXTURES / 'same.txt'}"), top=3)
    assert view.columns == PROFILE_COLUMNS
    assert len(view.rows) == len(FEATURE_LABELS)
    assert ("«))» на сообщение", "0.263") in view.rows
    assert view.word_lines[0] == "Частые служебные слова: и 0.051, там 0.038, в 0.025"
    assert view.word_lines[1].startswith("Частые слова-паразиты: ну 0.089")
    assert view.header.startswith("Автор: same.txt — 79 слов")


def test_top_words_helpers() -> None:
    features = {"fw:и": 0.2, "fw:а": 0.2, "fw:в": 0.0, "fl:ну": 0.1, "p:paren1": 0.9}
    assert top_words(features, "fw:", 5) == [("а", 0.2), ("и", 0.2)]  # при равенстве по алфавиту
    assert top_words(features, "fw:", 1) == [("а", 0.2)]
    assert word_list_lines(features, 3) == [
        "Частые служебные слова: а 0.200, и 0.200",
        "Частые слова-паразиты: ну 0.100",
        "Частые нестандартные написания: нет",
    ]
    assert word_list_lines({}, 3)[0] == "Частые служебные слова: нет"


# --- фоновая задача ---


def wait_for(job: BackgroundJob, timeout: float = 5.0):  # noqa: ANN201
    deadline = time.time() + timeout
    while time.time() < deadline:
        outcome = job.poll()
        if outcome is not None:
            return outcome
        time.sleep(0.01)
    raise AssertionError("фоновая задача не завершилась")


def test_background_job_returns_the_value_from_another_thread() -> None:
    main_thread = threading.get_ident()
    job: BackgroundJob[int] = BackgroundJob(lambda: threading.get_ident())
    assert job.poll() is None  # ещё не запущена
    job.start()
    ok, value = wait_for(job)
    assert ok is True and value != main_thread


def test_background_job_turns_errors_into_messages() -> None:
    def user_error() -> None:
        raise ChatstyleError("Файл не найден")

    def bug() -> None:
        raise KeyError("oops")

    first = BackgroundJob(user_error)
    first.start()
    assert wait_for(first) == (False, "Файл не найден")
    second = BackgroundJob(bug)
    second.start()
    ok, message = wait_for(second)
    assert ok is False and "Непредвиденная ошибка (KeyError)" in str(message)


# --- короткие подписи ---


def test_short_labels_use_file_names() -> None:
    labels = short_labels(
        [
            "file:C:/data/a.txt",
            r"file:C:\data\b.txt",
            "tgexport:C:/x/result.json#Анна",
            "tg:@friend",
            "file:plain.txt",
        ]
    )
    expected = ["a.txt", "b.txt", "result.json#Анна", "tg:@friend", "plain.txt"]
    assert list(labels.values()) == expected


def test_short_labels_keep_full_text_when_names_collide() -> None:
    labels = short_labels(["file:one/a.txt", "file:two/a.txt", "file:three/b.txt"])
    assert labels["file:one/a.txt"] == "file:one/a.txt"
    assert labels["file:two/a.txt"] == "file:two/a.txt"
    assert labels["file:three/b.txt"] == "b.txt"


def test_result_view_shortens_paths_everywhere(tmp_path: Path) -> None:
    result = run_comparison(
        f"file:{FIXTURES / 'unknown.txt'}",
        [f"file:{FIXTURES / 'same.txt'}", f"file:{FIXTURES / 'other.txt'}"],
    )
    view = build_result_view(result)
    parts = [view.unknown_line, *view.notes, view.warning or "", *(r[0] for r in view.rows)]
    text = "\n".join(parts)
    assert str(FIXTURES) not in text
    assert "same.txt" in text and "other.txt" in text
    assert view.unknown_line.startswith("Неизвестный автор: unknown.txt — ")
    assert [row[0] for row in view.rows] == ["same.txt", "other.txt"]
