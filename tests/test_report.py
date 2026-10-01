from datetime import datetime
from pathlib import Path

import pytest
from chatstyle.errors import ChatstyleError
from chatstyle.pipeline import (
    DISCLAIMER,
    MIN_WORDS,
    AuthorStats,
    CandidateResult,
    ComparisonResult,
    SharedFeature,
    low_volume_sides,
    low_volume_warning,
)
from chatstyle.report import (
    REPORT_TOP_FEATURES,
    _md_code,
    explanation_features,
    is_trivial_feature,
    render_html,
    render_markdown,
    report_format,
    write_report,
)

GENERATED = datetime(2026, 10, 1, 12, 30)


def feature(name: str, contribution: float = 0.01) -> SharedFeature:
    return SharedFeature(
        feature=name, contribution=contribution, unknown_count=3.0, candidate_count=4.0
    )


def make_result(
    *,
    unknown_words: int = 2000,
    candidate_words: int = 2000,
    features: tuple[SharedFeature, ...] = (),
    label: str = "file:friend.txt",
    similarity: float = 0.5,
    unknown_label: str = "file:unknown.txt",
) -> ComparisonResult:
    candidate = CandidateResult(
        label=label,
        words=candidate_words,
        messages=100,
        similarity=similarity,
        top_features=features,
    )
    return ComparisonResult(
        unknown_label=unknown_label,
        unknown=AuthorStats(words=unknown_words, messages=120),
        candidates=(candidate,),
    )


# --- содержимое ---


def test_markdown_has_all_sections() -> None:
    text = render_markdown(make_result(features=(feature("ну"),)), GENERATED)
    assert text.startswith("# Отчёт chatstyle\n")
    assert f"> {DISCLAIMER}" in text
    assert "Дата: 2026-10-01 12:30 · chatstyle 0.1.0 (ядро 0.1.0)" in text
    for heading in ("## Результат", "## Что совпало", "## Метод", "## Ограничения и приватность"):
        assert heading in text
    assert "Неизвестный автор: `file:unknown.txt` — 2000 слов, 120 сообщений" in text
    assert "| `file:friend.txt` | 2000 | 100 | 0.500 |" in text
    assert "| 1 | `ну` | 2.0% | 3 | 4 |" in text
    assert "косинус" in text
    assert "не вероятность" in text


def test_html_has_all_sections_and_is_self_contained() -> None:
    text = render_html(make_result(features=(feature("ну"),)), GENERATED)
    assert text.startswith("<!DOCTYPE html>")
    assert "<h1>Отчёт chatstyle</h1>" in text
    assert DISCLAIMER in text
    assert "Дата: 2026-10-01 12:30" in text
    for heading in ("Результат", "Что совпало", "Метод", "Ограничения и приватность"):
        assert f"<h2>{heading}</h2>" in text
    assert "<code>file:friend.txt</code>" in text
    assert '<td class="num">0.500</td>' in text
    assert "<code>ну</code>" in text
    for forbidden in ("<script", "http://", "https://", "src=", "href="):
        assert forbidden not in text


def test_report_is_deterministic() -> None:
    result = make_result(features=(feature("ну"), feature(")")))
    assert render_markdown(result, GENERATED) == render_markdown(result, GENERATED)
    assert render_html(result, GENERATED) == render_html(result, GENERATED)


# --- предупреждение о малом объёме ---


def test_no_warning_when_enough_text() -> None:
    result = make_result(unknown_words=MIN_WORDS, candidate_words=MIN_WORDS)
    assert low_volume_sides(result) == []
    assert low_volume_warning(result) is None
    assert "Внимание" not in render_markdown(result, GENERATED)
    assert "Внимание" not in render_html(result, GENERATED)


def test_warning_lists_short_sides() -> None:
    result = make_result(unknown_words=999, candidate_words=500)
    assert low_volume_sides(result) == [(None, 999), ("file:friend.txt", 500)]
    markdown = render_markdown(result, GENERATED)
    assert "Внимание: мало текста (меньше 1000 слов)" in markdown
    assert "- неизвестный автор — 999" in markdown
    assert "- `file:friend.txt` — 500" in markdown
    html_text = render_html(result, GENERATED)
    assert "Внимание: мало текста (меньше 1000 слов)" in html_text
    assert "<li>неизвестный автор — 999</li>" in html_text
    assert "<li><code>file:friend.txt</code> — 500</li>" in html_text


def test_warning_only_for_the_short_candidate() -> None:
    result = make_result(unknown_words=5000, candidate_words=10)
    assert low_volume_sides(result) == [("file:friend.txt", 10)]
    assert "неизвестный автор — " not in render_markdown(result, GENERATED)


# --- признаки в отчёте ---


@pytest.mark.parametrize(
    ("name", "trivial"),
    [
        ("а", True),
        ("Я", True),
        ("o", True),
        ("␣", True),
        (")", False),
        ("😀", False),
        ("5", False),
        ("ну", False),
        ("^а", False),
        ("а␣", False),
    ],
)
def test_is_trivial_feature(name: str, trivial: bool) -> None:
    assert is_trivial_feature(name) is trivial


def test_trivial_features_are_hidden_and_order_kept() -> None:
    names = ["о", "а", "␣", ")", "б", "ну", "😀", "5"]
    result = make_result(features=tuple(feature(name) for name in names))
    shown = [item.feature for item in explanation_features(result.candidates[0])]
    assert shown == [")", "ну", "😀", "5"]
    text = render_markdown(result, GENERATED)
    assert "`о`" not in text
    assert "`␣`" not in text
    assert "| 1 | `)` |" in text


def test_features_are_cut_to_top_20_after_filtering() -> None:
    trivial = [feature(letter) for letter in "оаеинтсрвл"]
    meaningful = [feature(f"к{index}") for index in range(30)]
    result = make_result(features=tuple(trivial + meaningful))
    shown = explanation_features(result.candidates[0])
    assert len(shown) == REPORT_TOP_FEATURES == 20
    assert shown[0].feature == "к0"
    assert shown[-1].feature == "к19"
    text = render_markdown(result, GENERATED)
    assert "| 20 | `к19` |" in text
    assert "`к20`" not in text


def test_no_features_message() -> None:
    result = make_result(features=(feature("о"), feature("␣")))
    message = "Общих n-грамм, кроме одиночных букв и пробела, нет."
    assert message in render_markdown(result, GENERATED)
    assert message in render_html(result, GENERATED)


def test_share_is_percentage_of_similarity() -> None:
    result = make_result(similarity=0.5, features=(feature("ну", contribution=0.2),))
    assert "| 1 | `ну` | 40.0% | 3 | 4 |" in render_markdown(result, GENERATED)
    assert '<td class="num">40.0%</td>' in render_html(result, GENERATED)


def test_zero_similarity_does_not_divide_by_zero() -> None:
    result = make_result(similarity=0.0, features=(feature("ну", contribution=0.0),))
    assert "| 1 | `ну` | 0.0% |" in render_markdown(result, GENERATED)


# --- экранирование ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("file:a.txt", "`file:a.txt`"),
        ("a|b", "`a\\|b`"),
        ("a`b", "``a`b``"),
        ("`x", "`` `x ``"),
        ("x`", "`` x` ``"),
        ("a\nb", "`a b`"),
    ],
)
def test_md_code(text: str, expected: str) -> None:
    assert _md_code(text) == expected


def test_markdown_escapes_pipe_in_tables() -> None:
    result = make_result(label="tg:@a|b", features=(feature("|"),))
    text = render_markdown(result, GENERATED)
    assert "| `tg:@a\\|b` | 2000 | 100 | 0.500 |" in text
    assert "| 1 | `\\|` |" in text


def test_html_escapes_user_data() -> None:
    nasty = '<script>alert(1)</script>&"'
    result = make_result(label=nasty, unknown_label=nasty, features=(feature("<b>"),))
    text = render_html(result, GENERATED)
    assert "<script>alert" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;&amp;&quot;" in text
    assert "<code>&lt;b&gt;</code>" in text
    assert "<b>" not in text


# --- формат и запись ---


@pytest.mark.parametrize(
    ("name", "fmt"),
    [("r.md", "md"), ("r.MD", "md"), ("r.html", "html"), ("r.HTML", "html")],
)
def test_report_format(name: str, fmt: str) -> None:
    assert report_format(Path(name)) == fmt


@pytest.mark.parametrize("name", ["r.txt", "r", "r.htm", "r.pdf"])
def test_report_format_rejects_unknown(name: str) -> None:
    with pytest.raises(ChatstyleError) as exc_info:
        report_format(Path(name))
    assert "Неизвестный формат отчёта" in str(exc_info.value)
    assert ".md или .html" in str(exc_info.value)


def test_write_report_markdown_and_html(tmp_path: Path) -> None:
    result = make_result(features=(feature("ну"),))
    markdown = tmp_path / "report.md"
    html_file = tmp_path / "report.HTML"
    write_report(markdown, result, GENERATED)
    write_report(html_file, result, GENERATED)
    assert markdown.read_text(encoding="utf-8") == render_markdown(result, GENERATED)
    assert html_file.read_text(encoding="utf-8") == render_html(result, GENERATED)
    assert b"\r" not in markdown.read_bytes()


def test_write_report_overwrites_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "report.md"
    path.write_text("старое", encoding="utf-8")
    write_report(path, make_result(), GENERATED)
    assert "старое" not in path.read_text(encoding="utf-8")


def test_write_report_uses_current_time_by_default(tmp_path: Path) -> None:
    path = tmp_path / "report.md"
    write_report(path, make_result())
    assert f"Дата: {datetime.now().year}-" in path.read_text(encoding="utf-8")


def test_write_report_wrong_extension(tmp_path: Path) -> None:
    with pytest.raises(ChatstyleError):
        write_report(tmp_path / "report.txt", make_result(), GENERATED)
    assert not (tmp_path / "report.txt").exists()


def test_write_report_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(ChatstyleError) as exc_info:
        write_report(tmp_path / "нет" / "report.md", make_result(), GENERATED)
    assert "Не удалось записать отчёт" in str(exc_info.value)
