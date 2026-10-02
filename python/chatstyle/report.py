"""Отчёты о сравнении авторов: Markdown и HTML.

Модуль только оформляет готовый ComparisonResult, расчётов в нём нет.
"""

import html
import re
from datetime import datetime
from pathlib import Path

from chatstyle import __version__, _core
from chatstyle.errors import ChatstyleError
from chatstyle.features import describe_feature
from chatstyle.pipeline import (
    DISCLAIMER,
    MIN_WORDS,
    CandidateResult,
    ComparisonResult,
    SharedFeature,
    best_methods_text,
    delta_text,
    final_score_text,
    low_volume_sides,
    morph_text,
    ranking_text,
    unavailable_notes,
)

REPORT_TOP_FEATURES = 20
REPORT_TOP_DELTA = 10
SUPPORTED_FORMATS: dict[str, str] = {".md": "md", ".html": "html"}
SPACE_SYMBOL = "␣"

FINAL_SCORE_PARAGRAPHS: tuple[str, ...] = (
    "Итоговая оценка — оценка General Impostors: доля случайных итераций, в которых текст "
    "кандидата оказался ближе к тексту неизвестного автора, чем тексты всех посторонних "
    "авторов. Это число от 0 до 1, но не вероятность авторства.",
    "Прочерк означает, что метод недоступен (мало посторонних авторов или мало текста): "
    "число в этом случае было бы выдумкой. Косинус и Delta показаны отдельно; их значения "
    "можно сравнивать только между кандидатами одного запуска.",
)
METHOD_PARAGRAPHS: tuple[str, ...] = (
    "Сообщения очищаются: ссылки и упоминания заменяются метками, пустые и служебные "
    "сообщения отбрасываются; для n-грамм текст приводится к нижнему регистру.",
    "Косинусное сходство. Для каждого автора считаются символьные n-граммы длиной от 1 до 4; "
    "к началу и концу каждого сообщения добавляются маркеры, n-граммы не пересекают границы "
    "сообщений. Частоты взвешиваются TF-IDF: TF = 1 + ln(частота), IDF сглаженный и считается "
    "по всем авторам сравнения. Сходство — косинус между векторами неизвестного автора и "
    "кандидата, число от 0 до 1.",
    "Burrows Delta. Сравниваются стилевые признаки: серии «)», многоточия, «!» и «?», точка в "
    "конце, доля сообщений с заглавной буквы, «ё» против «е», латиница, эмодзи, средняя длина "
    "сообщения и частоты 100 самых частых служебных слов и слов-паразитов. Разброс признака "
    "оценивается по кускам текста (около 200 слов) всех авторов сравнения; Delta — среднее "
    "отличие значений неизвестного автора и кандидата в единицах этого разброса. Чем меньше "
    "Delta, тем ближе стили. Нужно не меньше шести кусков на всё сравнение.",
    "General Impostors. В каждой из 100 итераций выбирается случайная половина n-грамм, "
    "случайный кусок неизвестного автора, случайный кусок кандидата и по куску у случайных "
    "посторонних авторов (остальные кандидаты и тексты из папки --impostors). Итерация "
    "засчитывается кандидату, если его кусок ближе к куску неизвестного автора, чем куски всех "
    "посторонних. Нужно не меньше трёх посторонних авторов; результат воспроизводим при "
    "одинаковом seed.",
)
EXPLANATION_TEXT = (
    "«Доля сходства» показывает, какую часть значения косинусного сходства дала n-грамма; сумма "
    "по всем общим n-граммам равна сходству. В n-граммах «␣» — пробел, «^» — начало сообщения, "
    "«$» — конец. Одиночные буквы и пробел скрыты: они общие для любых русских текстов."
)
DELTA_TEXT = (
    "Признаки, по которым стили различаются сильнее всего. «Отличие» — разность значений "
    "неизвестного автора и кандидата в единицах естественного разброса признака по кускам "
    "текста; знак «+» значит, что у неизвестного автора значение выше."
)
LIMITATION_PARAGRAPHS: tuple[str, ...] = (
    f"Чем меньше текста, тем менее надёжна оценка; при объёме меньше {MIN_WORDS} слов у "
    "любой из сторон она может быть случайной.",
    "Оценка General Impostors зависит от набора посторонних авторов: если он мал или "
    "непохож на реальную среду общения, оценка искажается.",
    "Сходство стиля не доказывает авторство: похожим стилем пишут люди одного круга, "
    "возраста и темы, а один человек пишет по-разному в разных чатах.",
    "Отчёт содержит фрагменты текста переписки (n-граммы) и названия источников. Не "
    "публикуйте его и не передавайте без согласия авторов сообщений.",
)
NO_FEATURES_TEXT = "Общих n-грамм, кроме одиночных букв и пробела, нет."
LOW_VOLUME_HEADING = (
    f"Внимание: мало текста (меньше {MIN_WORDS} слов). Оценка может быть ненадёжной:"
)
UNKNOWN_AUTHOR = "неизвестный автор"
COLUMN_HEADERS = ("Кандидат", "Слов", "Сообщений", "Сходство (косинус)", "Delta", "Итоговая оценка")
MORPH_HEADER = "Части речи (косинус)"


def _headers(result: ComparisonResult) -> tuple[str, ...]:
    return (*COLUMN_HEADERS, MORPH_HEADER) if result.morph else COLUMN_HEADERS


_CSS = """\
body { font-family: system-ui, -apple-system, "Segoe UI", Arial, sans-serif; color: #111;
  background: #fff; margin: 0; line-height: 1.5; }
main { max-width: 56rem; margin: 0 auto; padding: 1.5rem 1rem 3rem; }
h1 { font-size: 1.6rem; } h2 { font-size: 1.25rem; margin-top: 2rem; }
h3 { font-size: 1.05rem; margin-top: 1.5rem; }
table { border-collapse: collapse; margin: 0.75rem 0; }
th, td { border: 1px solid #bbb; padding: 0.3rem 0.6rem; text-align: left; }
th { background: #f3f3f3; }
td.num, th.num { text-align: right; }
code { font-family: ui-monospace, Consolas, monospace; background: #f3f3f3; padding: 0 0.2rem; }
.table-wrap { overflow-x: auto; }
code { overflow-wrap: anywhere; }
.disclaimer { border-left: 4px solid #111; padding: 0.4rem 0.8rem; font-weight: 600; }
.warning { border: 1px solid #b45309; padding: 0.4rem 0.8rem; }
.meta { color: #555; }
"""


def report_format(path: Path) -> str:
    """Формат отчёта по расширению файла: "md" или "html"."""
    try:
        return SUPPORTED_FORMATS[path.suffix.lower()]
    except KeyError:
        raise ChatstyleError(
            f"Неизвестный формат отчёта «{path.suffix}». Используйте файл .md или .html."
        ) from None


def is_trivial_feature(feature: str) -> bool:
    """Одиночные буквы и пробел общие для любых русских текстов и ничего не объясняют."""
    return len(feature) == 1 and (feature.isalpha() or feature == SPACE_SYMBOL)


def explanation_features(candidate: CandidateResult) -> list[SharedFeature]:
    """Первые REPORT_TOP_FEATURES нетривиальных признаков кандидата по убыванию вклада."""
    shown = [item for item in candidate.top_features if not is_trivial_feature(item.feature)]
    return shown[:REPORT_TOP_FEATURES]


def _share(candidate: CandidateResult, item: SharedFeature) -> str:
    share = item.contribution / candidate.similarity * 100 if candidate.similarity > 0 else 0.0
    return f"{share:.1f}%"


def _count(value: float) -> str:
    return f"{value:g}"


def _value(value: float) -> str:
    return f"{value:.3g}"


def _stamp(generated: datetime) -> str:
    return generated.strftime("%Y-%m-%d %H:%M")


def _versions() -> str:
    return f"chatstyle {__version__} (ядро {_core.version()})"


def _parameters(result: ComparisonResult) -> str:
    return f"seed {result.seed}; посторонних авторов из папки: {result.impostor_count}"


def _delta_rows(candidate: CandidateResult) -> list[tuple[str, str, str, str]]:
    """Строки таблицы стилевых различий: признак, значения у обоих авторов, отличие в σ."""
    if candidate.delta is None or not candidate.delta.available:
        return []
    return [
        (
            describe_feature(item.feature),
            _value(item.unknown_value),
            _value(item.candidate_value),
            f"{item.z_difference:+.2f}",
        )
        for item in candidate.delta.differences[:REPORT_TOP_DELTA]
    ]


# --- Markdown ---


def _md_code(text: str) -> str:
    """Кодовый фрагмент Markdown; `|` экранируется, чтобы не ломать таблицы."""
    text = " ".join(text.split()) if "\n" in text else text
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return (fence + pad + text + pad + fence).replace("|", "\\|")


def _md_plain(text: str) -> str:
    """Обычный текст в ячейке таблицы Markdown: `|` экранируется."""
    return text.replace("|", "\\|")


def render_markdown(result: ComparisonResult, generated: datetime) -> str:
    unknown = result.unknown
    lines = [
        "# Отчёт chatstyle",
        "",
        f"> {DISCLAIMER}",
        "",
        f"Дата: {_stamp(generated)} · {_versions()}",
        "",
        f"Параметры: {_parameters(result)}",
        "",
        "## Результат",
        "",
        f"Неизвестный автор: {_md_code(result.unknown_label)} — "
        f"{unknown.words} слов, {unknown.messages} сообщений",
        "",
        "| " + " | ".join(_headers(result)) + " |",
        "|---|" + "---:|" * (len(_headers(result)) - 1),
    ]
    for candidate in result.candidates:
        lines.append(
            f"| {_md_code(candidate.label)} | {candidate.words} | {candidate.messages} "
            f"| {candidate.similarity:.3f} | {delta_text(candidate)} "
            f"| {final_score_text(candidate)} |"
            + (f" {morph_text(candidate)} |" if result.morph else "")
        )
    lines += ["", ranking_text(result)]
    best_line = best_methods_text(result)
    if best_line:
        lines += ["", _md_plain_text(best_line)]

    notes = unavailable_notes(result)
    if notes:
        lines.append("")
        lines += [f"- {_md_plain_text(note)}" for note in notes]

    sides = low_volume_sides(result)
    if sides:
        lines += ["", f"**{LOW_VOLUME_HEADING}**", ""]
        for label, words in sides:
            name = UNKNOWN_AUTHOR if label is None else _md_code(label)
            lines.append(f"- {name} — {words}")

    lines += ["", "## Итоговая оценка", ""]
    lines += [f"{paragraph}\n" for paragraph in FINAL_SCORE_PARAGRAPHS]

    lines += ["## Что совпало", "", EXPLANATION_TEXT]
    for candidate in result.candidates:
        lines += ["", f"### {_md_code(candidate.label)} — сходство {candidate.similarity:.3f}", ""]
        shown = explanation_features(candidate)
        if not shown:
            lines.append(NO_FEATURES_TEXT)
            continue
        lines += [
            "| # | N-грамма | Доля сходства | У неизвестного | У кандидата |",
            "|---:|---|---:|---:|---:|",
        ]
        for number, item in enumerate(shown, start=1):
            lines.append(
                f"| {number} | {_md_code(item.feature)} | {_share(candidate, item)} "
                f"| {_count(item.unknown_count)} | {_count(item.candidate_count)} |"
            )

    delta_sections = [(row, _delta_rows(row)) for row in result.candidates]
    if any(rows for _, rows in delta_sections):
        lines += ["", "## Чем различаются стили (Burrows Delta)", "", DELTA_TEXT]
        for candidate, rows in delta_sections:
            if not rows:
                continue
            lines += [
                "",
                f"### {_md_code(candidate.label)} — Delta {delta_text(candidate)}",
                "",
                "| Признак | У неизвестного | У кандидата | Отличие |",
                "|---|---:|---:|---:|",
            ]
            lines += [f"| {_md_plain(name)} | {u} | {c} | {z} |" for name, u, c, z in rows]

    lines += ["", "## Метод", ""]
    lines += [f"{paragraph}\n" for paragraph in METHOD_PARAGRAPHS]
    lines += ["## Ограничения и приватность", ""]
    lines += [f"- {paragraph}" for paragraph in LIMITATION_PARAGRAPHS]
    return "\n".join(lines).rstrip() + "\n"


def _md_plain_text(text: str) -> str:
    """Строка с подписями источников вне кодовых фрагментов: экранируем спецсимволы Markdown."""
    return re.sub(r"([\\`*_\[\]<>|])", r"\\\1", text)


# --- HTML ---


def _e(text: str) -> str:
    return html.escape(text, quote=True)


def _h_code(text: str) -> str:
    return f"<code>{_e(text)}</code>"


def render_html(result: ComparisonResult, generated: datetime) -> str:
    unknown = result.unknown
    header_cells = "".join(
        f"<th>{_e(name)}</th>" if index == 0 else f'<th class="num">{_e(name)}</th>'
        for index, name in enumerate(_headers(result))
    )
    out = [
        "<!DOCTYPE html>",
        '<html lang="ru">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Отчёт chatstyle</title>",
        f"<style>\n{_CSS}</style>",
        "</head>",
        "<body>",
        "<main>",
        "<h1>Отчёт chatstyle</h1>",
        f'<p class="disclaimer">{_e(DISCLAIMER)}</p>',
        f'<p class="meta">Дата: {_e(_stamp(generated))} · {_e(_versions())}</p>',
        f'<p class="meta">Параметры: {_e(_parameters(result))}</p>',
        "<h2>Результат</h2>",
        f"<p>Неизвестный автор: {_h_code(result.unknown_label)} — "
        f"{unknown.words} слов, {unknown.messages} сообщений</p>",
        "<table>",
        f"<tr>{header_cells}</tr>",
    ]
    for candidate in result.candidates:
        out.append(
            f"<tr><td>{_h_code(candidate.label)}</td>"
            f'<td class="num">{candidate.words}</td>'
            f'<td class="num">{candidate.messages}</td>'
            f'<td class="num">{candidate.similarity:.3f}</td>'
            f'<td class="num">{_e(delta_text(candidate))}</td>'
            f'<td class="num">{_e(final_score_text(candidate))}</td>'
            + (f'<td class="num">{_e(morph_text(candidate))}</td>' if result.morph else "")
            + "</tr>"
        )
    out.append("</table>")
    out.append(f"<p>{_e(ranking_text(result))}</p>")
    best_line = best_methods_text(result)
    if best_line:
        out.append(f"<p>{_e(best_line)}</p>")

    notes = unavailable_notes(result)
    if notes:
        out.append("<ul>")
        out += [f"<li>{_e(note)}</li>" for note in notes]
        out.append("</ul>")

    sides = low_volume_sides(result)
    if sides:
        out.append(f'<div class="warning"><strong>{_e(LOW_VOLUME_HEADING)}</strong><ul>')
        for label, words in sides:
            name = _e(UNKNOWN_AUTHOR) if label is None else _h_code(label)
            out.append(f"<li>{name} — {words}</li>")
        out.append("</ul></div>")

    out.append("<h2>Итоговая оценка</h2>")
    out += [f"<p>{_e(paragraph)}</p>" for paragraph in FINAL_SCORE_PARAGRAPHS]

    out += ["<h2>Что совпало</h2>", f"<p>{_e(EXPLANATION_TEXT)}</p>"]
    for candidate in result.candidates:
        out.append(f"<h3>{_h_code(candidate.label)} — сходство {candidate.similarity:.3f}</h3>")
        shown = explanation_features(candidate)
        if not shown:
            out.append(f"<p>{_e(NO_FEATURES_TEXT)}</p>")
            continue
        out += [
            "<table>",
            '<tr><th class="num">#</th><th>N-грамма</th><th class="num">Доля сходства</th>'
            '<th class="num">У неизвестного</th><th class="num">У кандидата</th></tr>',
        ]
        for number, item in enumerate(shown, start=1):
            out.append(
                f'<tr><td class="num">{number}</td><td>{_h_code(item.feature)}</td>'
                f'<td class="num">{_share(candidate, item)}</td>'
                f'<td class="num">{_count(item.unknown_count)}</td>'
                f'<td class="num">{_count(item.candidate_count)}</td></tr>'
            )
        out.append("</table>")

    delta_sections = [(row, _delta_rows(row)) for row in result.candidates]
    if any(rows for _, rows in delta_sections):
        out += ["<h2>Чем различаются стили (Burrows Delta)</h2>", f"<p>{_e(DELTA_TEXT)}</p>"]
        for candidate, rows in delta_sections:
            if not rows:
                continue
            out += [
                f"<h3>{_h_code(candidate.label)} — Delta {_e(delta_text(candidate))}</h3>",
                "<table>",
                '<tr><th>Признак</th><th class="num">У неизвестного</th>'
                '<th class="num">У кандидата</th><th class="num">Отличие</th></tr>',
            ]
            for name, unknown_value, candidate_value, z in rows:
                out.append(
                    f'<tr><td>{_e(name)}</td><td class="num">{unknown_value}</td>'
                    f'<td class="num">{candidate_value}</td><td class="num">{z}</td></tr>'
                )
            out.append("</table>")

    out.append("<h2>Метод</h2>")
    out += [f"<p>{_e(paragraph)}</p>" for paragraph in METHOD_PARAGRAPHS]
    out.append("<h2>Ограничения и приватность</h2>")
    out.append("<ul>")
    out += [f"<li>{_e(paragraph)}</li>" for paragraph in LIMITATION_PARAGRAPHS]
    out += ["</ul>", "</main>", "</body>", "</html>"]
    text = "\n".join(out) + "\n"
    # таблицы с длинными подписями источников прокручиваются, а не вылезают за страницу;
    # данные пользователя экранированы, поэтому литерал <table> в них встретиться не может
    return text.replace("<table>", '<div class="table-wrap"><table>').replace(
        "</table>", "</table></div>"
    )


# --- запись ---


def write_report(path: Path, result: ComparisonResult, generated: datetime | None = None) -> None:
    """Записать отчёт в формате, заданном расширением файла (.md или .html)."""
    fmt = report_format(path)
    moment = generated if generated is not None else datetime.now()
    text = render_markdown(result, moment) if fmt == "md" else render_html(result, moment)
    try:
        path.write_text(text, encoding="utf-8", newline="\n")
    except OSError as exc:
        raise ChatstyleError(f"Не удалось записать отчёт {path}: {exc}") from exc
