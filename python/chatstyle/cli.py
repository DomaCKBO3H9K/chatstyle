from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from chatstyle import __version__, _core
from chatstyle.collectors import CollectOptions
from chatstyle.collectors.impostors import load_impostor_directory
from chatstyle.collectors.telegram import DEFAULT_LIMIT, TelethonFetcher
from chatstyle.errors import ChatstyleError
from chatstyle.features import FEATURE_LABELS, FILLER_WORD_PREFIX, FUNCTION_WORD_PREFIX
from chatstyle.impostors import DEFAULT_SEED
from chatstyle.paths import session_file
from chatstyle.pipeline import (
    DISCLAIMER,
    AuthorProfile,
    ComparisonResult,
    best_methods_text,
    delta_text,
    final_score_text,
    low_volume_warning,
    profile_author,
    ranking_text,
    run_comparison,
    unavailable_notes,
)
from chatstyle.report import report_format, write_report

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="chatstyle — верификация авторства русскоязычной переписки по стилю письма.",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"chatstyle {__version__} (ядро {_core.version()})")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Показать версию и выйти.",
        ),
    ] = False,
) -> None:
    """chatstyle"""


@app.command()
def compare(
    unknown: Annotated[
        str,
        typer.Option(
            "--unknown",
            "-u",
            help="Источник неизвестного автора, например file:unknown.txt",
        ),
    ],
    candidate: Annotated[
        list[str],
        typer.Option(
            "--candidate",
            "-c",
            help="Источник кандидата; можно указать несколько раз",
        ),
    ],
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-n",
            min=1,
            help="Максимум сообщений на автора для источников tg:",
        ),
    ] = DEFAULT_LIMIT,
    refresh: Annotated[
        bool,
        typer.Option(
            "--refresh",
            help="Игнорировать кэш и заново загрузить сообщения из Telegram",
        ),
    ] = False,
    report: Annotated[
        Path | None,
        typer.Option("--report", help="Сохранить отчёт в файл .md или .html"),
    ] = None,
    impostors: Annotated[
        Path | None,
        typer.Option(
            "--impostors",
            help="Папка с чужими текстами для General Impostors: один файл .txt на автора",
        ),
    ] = None,
    seed: Annotated[
        int,
        typer.Option(
            "--seed",
            min=0,
            help="Seed General Impostors: один и тот же seed даёт один и тот же результат",
        ),
    ] = DEFAULT_SEED,
) -> None:
    """Сравнить неизвестного автора с каждым кандидатом."""
    try:
        if report is not None:
            report_format(report)  # формат проверяется до сбора данных
    except ChatstyleError as exc:
        typer.echo(f"Ошибка: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    options = CollectOptions(
        limit=limit,
        refresh=refresh,
        notify=lambda message: typer.echo(message, err=True),
    )
    try:
        impostor_authors = load_impostor_directory(impostors) if impostors is not None else None
        result = run_comparison(unknown, candidate, options, impostors=impostor_authors, seed=seed)
    except ChatstyleError as exc:
        typer.echo(f"Ошибка: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    _print_result(unknown, result)

    if report is not None:
        try:
            write_report(report, result)
        except ChatstyleError as exc:
            typer.echo(f"Ошибка: {exc}", err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(f"Отчёт сохранён: {report}")


@app.command()
def features(
    source: Annotated[str, typer.Argument(help="Источник автора, например file:chat.txt")],
    top: Annotated[
        int,
        typer.Option("--top", min=1, help="Сколько самых частых слов показать"),
    ] = 10,
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", min=1, help="Максимум сообщений для источников tg:"),
    ] = DEFAULT_LIMIT,
    refresh: Annotated[
        bool,
        typer.Option("--refresh", help="Игнорировать кэш и заново загрузить сообщения"),
    ] = False,
) -> None:
    """Показать стилевой профиль одного автора (пунктуация, оформление, частые слова)."""
    options = CollectOptions(
        limit=limit,
        refresh=refresh,
        notify=lambda message: typer.echo(message, err=True),
    )
    try:
        profile = profile_author(source, options)
    except ChatstyleError as exc:
        typer.echo(f"Ошибка: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    _print_profile(profile, top)


def _print_profile(profile: AuthorProfile, top: int) -> None:
    console = Console(highlight=False, markup=False)
    console.print(
        f"Автор: {profile.label} — {profile.stats.words} слов, {profile.stats.messages} сообщений",
        soft_wrap=True,
    )

    table = Table(title=None)
    table.add_column("Признак")
    table.add_column("Значение", justify="right")
    for key, label in FEATURE_LABELS.items():
        table.add_row(label, f"{profile.features[key]:.3f}")
    console.print(table)

    for prefix, title in (
        (FUNCTION_WORD_PREFIX, "Частые служебные слова"),
        (FILLER_WORD_PREFIX, "Частые слова-паразиты"),
    ):
        ranked = sorted(
            (
                (key[len(prefix) :], value)
                for key, value in profile.features.items()
                if key.startswith(prefix) and value > 0
            ),
            key=lambda item: (-item[1], item[0]),
        )[:top]
        line = ", ".join(f"{word} {value:.3f}" for word, value in ranked) or "нет"
        console.print(f"{title}: {line}", soft_wrap=True)


@app.command()
def login() -> None:
    """Войти в Telegram и сохранить сессию (один раз, для источников tg:)."""
    typer.echo(
        "Будут запрошены номер телефона, код из Telegram и пароль двухфакторной защиты "
        "(если включена). Данные вводятся только в этом окне."
    )
    try:
        name = TelethonFetcher().login()
    except ChatstyleError as exc:
        typer.echo(f"Ошибка: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Вход выполнен: {name}. Сессия сохранена в {session_file()}")


def _print_result(unknown_spec: str, result: ComparisonResult) -> None:
    console = Console(highlight=False, markup=False)

    # 1. Строка с неизвестным автором
    console.print(
        f"Неизвестный автор: {unknown_spec} — "
        f"{result.unknown.words} слов, {result.unknown.messages} сообщений",
        soft_wrap=True,
    )

    # 2. Таблица кандидатов
    table = Table(title=None)
    # длинная подпись источника переносится, а заголовки чисел не сокращаются
    table.add_column("Кандидат", overflow="fold")
    for header in ("Слов", "Сообщений", "Сходство", "Delta", "Impostors (итог)"):
        table.add_column(header, justify="right", no_wrap=True, min_width=len(header))

    for cand in result.candidates:
        table.add_row(
            cand.label,
            str(cand.words),
            str(cand.messages),
            f"{cand.similarity:.3f}",
            delta_text(cand),
            final_score_text(cand),
        )

    console.print(table)
    console.print(ranking_text(result), soft_wrap=True)
    best_line = best_methods_text(result)
    if best_line:
        console.print(best_line, soft_wrap=True)
    for note in unavailable_notes(result):
        console.print(note, soft_wrap=True)

    # 3. Предупреждение о малом объёме текста
    warning = low_volume_warning(result)
    if warning:
        console.print(warning, soft_wrap=True)

    # 4. Дисклеймер
    console.print(DISCLAIMER, soft_wrap=True)
