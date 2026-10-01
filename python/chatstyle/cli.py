from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from chatstyle import __version__, _core
from chatstyle.collectors import CollectOptions
from chatstyle.collectors.telegram import DEFAULT_LIMIT, TelethonFetcher
from chatstyle.errors import ChatstyleError
from chatstyle.paths import session_file
from chatstyle.pipeline import MIN_WORDS, ComparisonResult, run_comparison

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="chatstyle — верификация авторства русскоязычной переписки по стилю письма.",
)

DISCLAIMER: str = "Результат — статистическая оценка сходства стиля, а не доказательство авторства."


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
) -> None:
    """Сравнить неизвестного автора с каждым кандидатом."""
    options = CollectOptions(
        limit=limit,
        refresh=refresh,
        notify=lambda message: typer.echo(message, err=True),
    )
    try:
        result = run_comparison(unknown, candidate, options)
    except ChatstyleError as exc:
        typer.echo(f"Ошибка: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    _print_result(unknown, result)


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
    table.add_column("Кандидат", no_wrap=True)
    table.add_column("Слов", justify="right")
    table.add_column("Сообщений", justify="right")
    table.add_column("Сходство", justify="right")

    for cand in result.candidates:
        table.add_row(
            cand.label,
            str(cand.words),
            str(cand.messages),
            f"{cand.similarity:.3f}",
        )

    console.print(table)

    # 3. Предупреждение о малом объёме текста
    low_text_parts: list[str] = []

    if result.unknown.words < MIN_WORDS:
        low_text_parts.append(f"неизвестный автор — {result.unknown.words}")

    for cand in result.candidates:
        if cand.words < MIN_WORDS:
            low_text_parts.append(f"{cand.label} — {cand.words}")

    if low_text_parts:
        warning = (
            f"Внимание: мало текста (меньше {MIN_WORDS} слов): "
            + "; ".join(low_text_parts)
            + ". Оценка может быть ненадёжной."
        )
        console.print(warning, soft_wrap=True)

    # 4. Дисклеймер
    console.print(DISCLAIMER, soft_wrap=True)
