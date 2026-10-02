from datetime import datetime

from chatstyle.delta import DeltaScore, FeatureDifference
from chatstyle.features import describe_feature
from chatstyle.impostors import ImpostorsScore
from chatstyle.pipeline import AuthorStats, CandidateResult, ComparisonResult
from chatstyle.report import render_html, render_markdown

GENERATED = datetime(2026, 10, 1, 12, 30)


def difference(feature: str, unknown: float, candidate: float, z: float) -> FeatureDifference:
    return FeatureDifference(
        feature=feature,
        unknown_value=unknown,
        candidate_value=candidate,
        sigma=0.1,
        z_difference=z,
    )


def make_result(
    *,
    delta: DeltaScore | None,
    impostors: ImpostorsScore | None,
    label: str = "file:friend.txt",
    seed: int = 7,
    impostor_count: int = 4,
) -> ComparisonResult:
    candidate = CandidateResult(
        label=label,
        words=2000,
        messages=100,
        similarity=0.5,
        delta=delta,
        impostors_score=impostors,
    )
    return ComparisonResult(
        unknown_label="file:unknown.txt",
        unknown=AuthorStats(words=2000, messages=120),
        candidates=(candidate,),
        seed=seed,
        impostor_count=impostor_count,
        ranked_by="impostors" if impostors is not None and impostors.available else "cosine",
    )


AVAILABLE_DELTA = DeltaScore(
    available=True,
    delta=0.4567,
    features_used=21,
    differences=(
        difference("f:capital_start", 0.1, 0.9, -2.5),
        difference("fw:и", 0.05, 0.02, 1.25),
        difference("fl:ну", 0.03, 0.0, 0.9),
        difference("p:paren2", 0.4, 0.0, 3.0),
    ),
)
AVAILABLE_SCORE = ImpostorsScore(available=True, score=0.874, impostors=5, iterations=100)


def test_markdown_table_and_summary_with_all_methods() -> None:
    text = render_markdown(make_result(delta=AVAILABLE_DELTA, impostors=AVAILABLE_SCORE), GENERATED)
    assert "| Кандидат | Слов | Сообщений | Сходство (косинус) | Delta | Итоговая оценка |" in text
    assert "| `file:friend.txt` | 2000 | 100 | 0.500 | 0.46 | 0.87 |" in text
    assert "Порядок: по итоговой оценке (General Impostors)." in text
    assert "Параметры: seed 7; посторонних авторов из папки: 4" in text
    assert "## Итоговая оценка" in text
    assert "не вероятность авторства" in text
    assert "Burrows Delta недоступна" not in text
    assert "General Impostors недоступен" not in text


def test_markdown_delta_section_uses_readable_names() -> None:
    text = render_markdown(make_result(delta=AVAILABLE_DELTA, impostors=AVAILABLE_SCORE), GENERATED)
    assert "## Чем различаются стили (Burrows Delta)" in text
    assert "### `file:friend.txt` — Delta 0.46" in text
    assert "| доля сообщений с заглавной буквы | 0.1 | 0.9 | -2.50 |" in text
    assert "| служебное слово «и» | 0.05 | 0.02 | +1.25 |" in text
    assert "| слово-паразит «ну» | 0.03 | 0 | +0.90 |" in text
    assert "| «))» на сообщение | 0.4 | 0 | +3.00 |" in text
    assert "fw:и" not in text


def test_delta_section_is_limited_to_top_10() -> None:
    many = DeltaScore(
        available=True,
        delta=1.0,
        features_used=30,
        differences=tuple(difference(f"fw:слово{i}", 0.1, 0.2, 3.0 - i * 0.1) for i in range(15)),
    )
    text = render_markdown(make_result(delta=many, impostors=AVAILABLE_SCORE), GENERATED)
    assert "слово9»" in text
    assert "слово10»" not in text


def test_unavailable_methods_show_dashes_and_reasons() -> None:
    delta = DeltaScore(available=False, delta=0.0, features_used=0, differences=())
    score = ImpostorsScore(available=False, score=0.0, impostors=1, iterations=0)
    result = make_result(delta=delta, impostors=score, impostor_count=0)
    markdown = render_markdown(result, GENERATED)
    assert "| `file:friend.txt` | 2000 | 100 | 0.500 | — | — |" in markdown
    assert "Порядок: по косинусному сходству (итоговая оценка недоступна)." in markdown
    assert "Burrows Delta недоступна" in markdown
    assert "посторонних авторов 1 из 3" in markdown
    assert "--impostors DIR" in markdown
    assert "## Чем различаются стили" not in markdown
    html_text = render_html(result, GENERATED)
    assert '<td class="num">—</td><td class="num">—</td>' in html_text
    assert "<h2>Чем различаются стили" not in html_text


def test_methods_that_were_not_run_show_dashes() -> None:
    text = render_markdown(make_result(delta=None, impostors=None), GENERATED)
    assert "| 0.500 | — | — |" in text
    assert "Burrows Delta недоступна" not in text  # метод не запускался, жалобы нет


def test_html_has_delta_table_and_parameters() -> None:
    text = render_html(make_result(delta=AVAILABLE_DELTA, impostors=AVAILABLE_SCORE), GENERATED)
    assert "<h2>Чем различаются стили (Burrows Delta)</h2>" in text
    assert "<td>служебное слово «и»</td>" in text
    assert '<td class="num">+1.25</td>' in text
    assert '<td class="num">0.87</td>' in text
    assert "Параметры: seed 7; посторонних авторов из папки: 4" in text


def test_disagreement_is_reported_in_both_formats() -> None:
    low = CandidateResult(
        label="file:a.txt",
        words=2000,
        messages=100,
        similarity=0.6,
        delta=DeltaScore(True, 0.9, 20, ()),
        impostors_score=ImpostorsScore(True, 0.2, 5, 100),
    )
    high = CandidateResult(
        label="file:b.txt",
        words=2000,
        messages=100,
        similarity=0.3,
        delta=DeltaScore(True, 0.1, 20, ()),
        impostors_score=ImpostorsScore(True, 0.8, 5, 100),
    )
    result = ComparisonResult("u", AuthorStats(2000, 100), (high, low), ranked_by="impostors")
    expected = "Лучший по методам: косинус — file:a.txt; Delta — file:b.txt; Impostors — file:b.txt"
    assert expected in render_markdown(result, GENERATED).replace("\\", "")
    assert expected in render_html(result, GENERATED)
    assert "(методы расходятся)" in render_html(result, GENERATED)


def test_html_escapes_labels_in_new_sections() -> None:
    nasty = "<b>&</b>"
    score = ImpostorsScore(available=False, score=0.0, impostors=0, iterations=0)
    delta = DeltaScore(available=False, delta=0.0, features_used=0, differences=())
    text = render_html(make_result(delta=delta, impostors=score, label=nasty), GENERATED)
    assert "<b>&</b>" not in text
    assert "&lt;b&gt;&amp;&lt;/b&gt;" in text


def test_markdown_escapes_labels_outside_code_spans() -> None:
    delta = DeltaScore(available=False, delta=0.0, features_used=0, differences=())
    score = ImpostorsScore(available=False, score=0.0, impostors=0, iterations=0)
    text = render_markdown(make_result(delta=delta, impostors=score, label="a_b*c"), GENERATED)
    assert "a\\_b\\*c" in text  # в строках пояснений подпись экранирована
    assert "`a_b*c`" in text  # в таблице она в кодовом фрагменте


def test_describe_feature() -> None:
    assert describe_feature("p:paren2") == "«))» на сообщение"
    assert describe_feature("r:avg_words") == "средняя длина сообщения, слов"
    assert describe_feature("fw:из-за") == "служебное слово «из-за»"
    assert describe_feature("fl:короче") == "слово-паразит «короче»"
    assert describe_feature("unknown:key") == "unknown:key"


def test_html_tables_are_scrollable_wrappers() -> None:
    text = render_html(make_result(delta=AVAILABLE_DELTA, impostors=AVAILABLE_SCORE), GENERATED)
    assert text.count("<table>") == text.count("</table>") >= 2
    assert text.count('<div class="table-wrap"><table>') == text.count("<table>")
    assert text.count("</table></div>") == text.count("</table>")
