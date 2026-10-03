import random
from pathlib import Path

import pytest
from chatstyle.cli import app
from chatstyle.ensemble import (
    balanced_candidates,
    cap_messages,
    mask_rare_words,
    masked_charlm,
    mix,
    skeleton_cosine,
    z_scores,
)
from chatstyle.gui.api import Api, compare_view_dict
from chatstyle.gui.model import CompareForm, CompareOutcome, run_compare
from chatstyle.pipeline import (
    METHOD_ENSEMBLE,
    CandidateResult,
    ensemble_text,
    lexical_hint,
    lexical_hint_text,
    ranking_text,
    run_comparison,
)
from chatstyle.report import write_report
from chatstyle.timeline import Messages
from synthetic import casual, formal, write_lines, write_workspace
from typer.testing import CliRunner

runner = CliRunner()


def spec(path: Path) -> str:
    return f"file:{path}"


def test_cap_messages_is_deterministic_keeps_order_and_times() -> None:
    messages = Messages([f"слово{i} ещё одно слово" for i in range(100)], list(range(100)))
    first = cap_messages(messages, 40, "ключ")
    again = cap_messages(messages, 40, "ключ")
    assert list(first) == list(again) and first.times == again.times
    assert first.times == sorted(first.times or [])
    assert 40 <= sum(len(m.split()) for m in first) <= 44
    assert list(cap_messages(messages, 40, "другой ключ")) != list(first)
    assert first.times is not None and all(
        messages[t] == m for t, m in zip(first.times, first, strict=True)
    )


def test_cap_messages_without_times_and_with_huge_cap() -> None:
    plain = ["раз два", "три четыре"]
    capped = cap_messages(plain, 1000, "k")
    assert list(capped) == plain and capped.times is None
    assert list(cap_messages([], 10, "k")) == []


def test_balanced_candidates_equalizes_sizes_but_never_below_the_shortest() -> None:
    big = [f"слово{i} раз два три" for i in range(500)]
    small = [f"слово{i} раз два" for i in range(100)]
    capped = balanced_candidates({"big": big, "small": small}, cap_words=50)
    # короче самого короткого кандидата (300 слов) не режем: предел max(50, 300)
    assert sum(len(m.split()) for m in capped["small"]) == 300
    assert 300 <= sum(len(m.split()) for m in capped["big"]) <= 304
    tiny = balanced_candidates({"a": ["раз два"], "b": ["три " * 10]}, cap_words=5)
    assert sum(len(m.split()) for m in tiny["a"]) == 2


def test_z_scores() -> None:
    z = z_scores({"a": 1.0, "b": 2.0, "c": 3.0})
    assert z["b"] == 0.0 and z["a"] == pytest.approx(-z["c"])
    assert z_scores({"a": 5.0, "b": 5.0}) == {"a": 0.0, "b": 0.0}


def test_mix_uses_only_signals_available_for_everyone_and_needs_two() -> None:
    labels = ["a", "b", "c"]
    full = {"a": 3.0, "b": 2.0, "c": 1.0}
    partial = {"a": 9.0, "b": 8.0}  # у «c» нет значения: сигнал не входит
    only_one = mix([full, partial], labels)
    assert only_one == {}
    two = mix([full, {"a": 30.0, "b": 20.0, "c": 10.0}], labels)
    assert two["a"] > two["b"] > two["c"]
    assert two["b"] == pytest.approx(0.0)
    assert mix([full, full], ["a"]) == {}  # один кандидат: нечего смешивать


def test_two_candidates_give_a_vote_share() -> None:
    votes = mix([{"a": 1.0, "b": 0.0}, {"a": 1.0, "b": 0.0}, {"a": 0.0, "b": 1.0}], ["a", "b"])
    assert votes["a"] == pytest.approx(1 / 3)
    assert votes["b"] == pytest.approx(-1 / 3)


def test_skeleton_ignores_content_words() -> None:
    # одинаковая «грамматика» служебных слов, разные темы: каркас у них совпадает
    unknown = ["я не знаю что делать с кошкой", "я не знаю что купить в магазине"] * 10
    same_frame = ["я не знаю что делать с собакой", "я не знаю что взять в аптеке"] * 10
    other_frame = ["вчера купили новый красивый диван", "сегодня сломался старый холодильник"] * 10
    scores = skeleton_cosine(unknown, {"same": same_frame, "other": other_frame}, keep_words=8)
    assert scores["same"] > scores["other"]
    assert skeleton_cosine([], {"a": ["раз"]}) == {}
    assert skeleton_cosine(["раз"], {"a": []}) == {}


def test_ensemble_picks_the_same_author_and_is_signed(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    result = run_comparison(spec(files["unknown"]), [spec(files["other"]), spec(files["same"])])
    assert result.ensemble is True and result.ranked_by == METHOD_ENSEMBLE
    same, other = result.candidates
    assert same.label == spec(files["same"])
    assert same.ensemble_score is not None and other.ensemble_score is not None
    assert same.ensemble_score > 0 > other.ensemble_score
    assert ensemble_text(same).startswith("+") and ensemble_text(other).startswith("-")


def test_single_candidate_has_no_ensemble(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    result = run_comparison(spec(files["unknown"]), [spec(files["same"])])
    assert result.ensemble is False
    assert result.candidates[0].ensemble_score is None
    assert ensemble_text(result.candidates[0]) == "—"


def test_ensemble_can_be_switched_off(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    result = run_comparison(
        spec(files["unknown"]), [spec(files["other"]), spec(files["same"])], ensemble=False
    )
    assert result.ensemble is False and result.ranked_by != METHOD_ENSEMBLE


def test_a_much_bigger_candidate_does_not_win_by_size(tmp_path: Path) -> None:
    """Огромный чужой кандидат не должен выигрывать только объёмом текста."""
    unknown = write_lines(tmp_path / "unknown.txt", casual(1, 60))
    small_same = write_lines(tmp_path / "same.txt", casual(2, 60))
    huge_other = write_lines(tmp_path / "huge.txt", formal(3, 1500))
    result = run_comparison(spec(unknown), [spec(huge_other), spec(small_same)])
    assert result.candidates[0].label == spec(small_same)


def test_ensemble_does_not_depend_on_candidate_order(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    forward = run_comparison(spec(files["unknown"]), [spec(files["other"]), spec(files["same"])])
    backward = run_comparison(spec(files["unknown"]), [spec(files["same"]), spec(files["other"])])
    by_label = {row.label: row.ensemble_score for row in forward.candidates}
    for row in backward.candidates:
        assert row.ensemble_score == pytest.approx(by_label[row.label])


def test_ensemble_result_is_reproducible(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    args = (spec(files["unknown"]), [spec(files["other"]), spec(files["same"])])
    assert run_comparison(*args) == run_comparison(*args)


def test_cli_and_reports_show_the_mix(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    args = [
        "compare",
        "-u",
        spec(files["unknown"]),
        "-c",
        spec(files["other"]),
        "-c",
        spec(files["same"]),
    ]
    out = runner.invoke(app, args, env={"COLUMNS": "220"}).output
    assert "Смесь" in out and "Порядок: по стилевой смеси" in out

    result = run_comparison(spec(files["unknown"]), [spec(files["other"]), spec(files["same"])])
    for suffix in ("md", "html"):
        path = tmp_path / f"r.{suffix}"
        write_report(path, result)
        assert "Смесь методов (z)" in path.read_text(encoding="utf-8")

    single = run_comparison(spec(files["unknown"]), [spec(files["same"])])
    path = tmp_path / "single.md"
    write_report(path, single)
    assert "Смесь методов (z)" not in path.read_text(encoding="utf-8")


def test_gui_view_has_relative_shares(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    result = run_comparison(spec(files["unknown"]), [spec(files["other"]), spec(files["same"])])
    view = compare_view_dict(CompareOutcome(result, None))
    assert view["metric"] == "ensemble" and view["ensemble"] is True
    shares = [item["value"] for item in view["candidates"]]
    assert sum(shares) == pytest.approx(1.0)
    assert shares[0] > shares[1]
    assert all(item["ensemble"][0] in "+-" for item in view["candidates"])


def test_candidate_result_text_format() -> None:
    row = CandidateResult(label="x", words=1, messages=1, similarity=0.5, ensemble_score=0.4567)
    assert ensemble_text(row) == "+0.46"
    assert ensemble_text(CandidateResult(label="x", words=1, messages=1, similarity=0.5)) == "—"


def test_random_synthetic_authors_are_recognized_beyond_the_workspace(tmp_path: Path) -> None:
    """Пять разных случайных «авторов»: свой всегда первый."""
    rng = random.Random(5)
    wins = 0
    for trial in range(5):
        seed = rng.randint(1, 10_000)
        unknown = write_lines(tmp_path / f"u{trial}.txt", casual(seed, 50))
        same = write_lines(tmp_path / f"s{trial}.txt", casual(seed + 1, 50))
        other = write_lines(tmp_path / f"o{trial}.txt", formal(seed + 2, 50))
        result = run_comparison(spec(unknown), [spec(other), spec(same)])
        wins += result.candidates[0].label == spec(same)
    assert wins == 5


# --- стилевая смесь и лексика ---


def test_mask_rare_words_keeps_frequent_words_punctuation_and_lengths() -> None:
    masked = mask_rare_words(["Я не знаю 42!", "   ", "!!!"], keep={"я", "не"})
    assert masked == ["я не **** ##!", "!!!"]


def test_masked_charlm_prefers_the_same_style(tmp_path: Path) -> None:
    unknown = casual(1, 60)
    scores = masked_charlm(unknown, {"same": casual(2, 60), "other": formal(3, 60)})
    assert scores["same"] > 0 > scores["other"]
    assert masked_charlm([], {"a": ["раз"], "b": ["два"]}) == {}


def test_style_mix_is_the_default_and_lexical_changes_the_note(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    args = (spec(files["unknown"]), [spec(files["other"]), spec(files["same"])])
    style = run_comparison(*args)
    lexical = run_comparison(*args, lexical=True)
    assert style.lexical is False and lexical.lexical is True
    assert "стилевой смеси" in ranking_text(style)
    assert "стилевой смеси" not in ranking_text(lexical)
    assert style.candidates[0].label == lexical.candidates[0].label == spec(files["same"])


def test_cli_lexical_flag(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    args = [
        "compare",
        "-u",
        spec(files["unknown"]),
        "-c",
        spec(files["other"]),
        "-c",
        spec(files["same"]),
    ]
    plain = runner.invoke(app, args, env={"COLUMNS": "220"})
    assert plain.exit_code == 0 and "Порядок: по стилевой смеси" in plain.output
    lexical = runner.invoke(app, [*args, "--lexical"], env={"COLUMNS": "220"})
    assert (
        lexical.exit_code == 0
        and "Порядок: по смеси методов (языковая модель, слова" in lexical.output
    )


def test_gui_form_passes_lexical_and_rejects_non_bool(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    outcome = run_compare(
        CompareForm(
            unknown=spec(files["unknown"]),
            candidates=(spec(files["other"]), spec(files["same"])),
            lexical=True,
        )
    )
    assert outcome.result.lexical is True
    api = Api(allowed_paths=["u.txt", "a.txt"])
    answer = api.start_compare(
        {"unknown": "file:u.txt", "candidates": ["file:a.txt"], "lexical": "yes"}
    )
    assert answer["ok"] is False
    assert {item["code"] for item in answer["errors"]} == {"bad_input"}


# --- подсказка включить лексику ---


def test_hint_appears_for_short_unknown_text_in_style_mode(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)  # у неизвестного около 660 слов
    args = (spec(files["unknown"]), [spec(files["other"]), spec(files["same"])])
    result = run_comparison(*args)
    hint = lexical_hint(result)
    assert hint is not None and hint["code"] == "lexical_hint"
    assert hint["min"] == 1000 and hint["words"] == result.unknown.words < 1000
    text = lexical_hint_text(result)
    assert text is not None and "--lexical" in text and str(result.unknown.words) in text


def test_no_hint_with_lexicon_enough_text_or_a_single_candidate(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    candidates = [spec(files["other"]), spec(files["same"])]
    assert lexical_hint(run_comparison(spec(files["unknown"]), candidates, lexical=True)) is None
    assert lexical_hint(run_comparison(spec(files["unknown"]), [spec(files["same"])])) is None
    assert lexical_hint(run_comparison(spec(files["unknown"]), candidates, ensemble=False)) is None
    long_unknown = write_lines(tmp_path / "long.txt", casual(1, 150))
    long_result = run_comparison(spec(long_unknown), candidates)
    assert long_result.unknown.words >= 1000
    assert lexical_hint(long_result) is None and lexical_hint_text(long_result) is None


def test_hint_is_shown_in_cli_reports_and_window(tmp_path: Path) -> None:
    files = write_workspace(tmp_path)
    candidates = [spec(files["other"]), spec(files["same"])]
    args = ["compare", "-u", spec(files["unknown"]), "-c", candidates[0], "-c", candidates[1]]
    assert "Подсказка:" in runner.invoke(app, args, env={"COLUMNS": "220"}).output
    lexical = runner.invoke(app, [*args, "--lexical"], env={"COLUMNS": "220"})
    assert "Подсказка:" not in lexical.output

    result = run_comparison(spec(files["unknown"]), candidates)
    for suffix in ("md", "html"):
        path = tmp_path / f"hint.{suffix}"
        write_report(path, result)
        assert "Подсказка:" in path.read_text(encoding="utf-8")

    view = compare_view_dict(CompareOutcome(result, None))
    assert {"code": "lexical_hint", "words": result.unknown.words, "min": 1000} in view["notes"]
    lexical_view = compare_view_dict(
        CompareOutcome(run_comparison(spec(files["unknown"]), candidates, lexical=True), None)
    )
    assert all(note["code"] != "lexical_hint" for note in lexical_view["notes"])
