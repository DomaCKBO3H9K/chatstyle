import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from chatstyle import __version__, _core
from chatstyle.collectors import CollectOptions
from chatstyle.collectors.impostors import load_impostor_directory
from chatstyle.collectors.telegram import DEFAULT_LIMIT, TelethonFetcher
from chatstyle.collectors.telegram_login import TelegramLogin
from chatstyle.config import load_credentials_with_vault
from chatstyle.errors import ChatstyleError
from chatstyle.features import (
    FEATURE_LABELS,
    FEATURE_SECTIONS,
    feature_section,
    morph_summary,
    parse_style_groups,
    word_list_lines,
)
from chatstyle.impostors import DEFAULT_SEED
from chatstyle.pipeline import (
    DISCLAIMER,
    AuthorProfile,
    ComparisonResult,
    best_methods_text,
    charlm_text,
    delta_text,
    final_score_text,
    low_volume_warning,
    morph_text,
    profile_author,
    ranking_text,
    run_comparison,
    unavailable_notes,
    wordgram_text,
)
from chatstyle.report import report_format, write_report
from chatstyle.securestore import (
    MIN_PASSWORD_LENGTH,
    MODE_DPAPI,
    MODE_PASSWORD,
    Vault,
    default_vault,
    set_password_prompt,
    unlock_interactively,
)

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
    ctx: typer.Context,
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
    if ctx.invoked_subcommand not in (None, "gui"):
        _use_console_password_prompt()  # окно спрашивает мастер-пароль у себя


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
    style_groups: Annotated[
        str,
        typer.Option(
            "--style-groups",
            help=(
                "Группы признаков для Burrows Delta: all, none или список через запятую из "
                "punctuation, orthography, words, sentences"
            ),
        ),
    ] = "all",
    morph: Annotated[
        bool,
        typer.Option(
            "--morph",
            help="Добавить сходство по частям речи (нужно: pip install chatstyle[morph])",
        ),
    ] = False,
    charlm: Annotated[
        bool,
        typer.Option(
            "--charlm",
            help="Добавить языковую модель символов (выигрыш кандидата, бит на символ)",
        ),
    ] = False,
    wordgrams: Annotated[
        bool,
        typer.Option("--wordgrams", help="Добавить сходство по пословным n-граммам (1-4 слова)"),
    ] = False,
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
        groups = parse_style_groups(style_groups)
        result = run_comparison(
            unknown,
            candidate,
            options,
            impostors=impostor_authors,
            seed=seed,
            style_groups=groups,
            morph=morph,
            charlm=charlm,
            wordgrams=wordgrams,
        )
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
    morph: Annotated[
        bool,
        typer.Option(
            "--morph",
            help="Показать доли частей речи (нужно дополнение: pip install chatstyle[morph])",
        ),
    ] = False,
) -> None:
    """Показать стилевой профиль одного автора (пунктуация, оформление, частые слова)."""
    options = CollectOptions(
        limit=limit,
        refresh=refresh,
        notify=lambda message: typer.echo(message, err=True),
    )
    try:
        profile = profile_author(source, options, morph=morph)
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
    current_section = None
    for key, label in FEATURE_LABELS.items():
        section = feature_section(key)
        if section != current_section:
            current_section = section
            table.add_row(FEATURE_SECTIONS[section], "", style="bold")
        table.add_row(label, f"{profile.features[key]:.3f}")
    console.print(table)

    for line in word_list_lines(profile.features, top):
        console.print(line, soft_wrap=True)
    if profile.morph_features is not None:
        console.print(morph_summary(profile.morph_features), soft_wrap=True)


@app.command()
def gui() -> None:
    """Открыть графический интерфейс (окно приложения)."""
    try:
        import webview  # noqa: F401
    except ImportError as exc:
        typer.echo(
            "Ошибка: графический интерфейс недоступен: не найден pywebview "
            "(pip install pywebview); в chatstyle.exe окна нет, запустите chatstyle-gui.exe.",
            err=True,
        )
        raise typer.Exit(code=2) from exc
    from chatstyle.gui import main as run_gui

    raise typer.Exit(code=run_gui())


def _secret(label: str) -> str:
    """Секрет без эха. В терминале скрытый ввод; если ввод перенаправлен (скрипт, канал),
    строка читается из stdin: скрытый ввод Windows читает консоль, а не канал."""
    if sys.stdin.isatty():
        return typer.prompt(label, hide_input=True)
    typer.echo(f"{label}: ", nl=False, err=True)
    return sys.stdin.readline().rstrip("\r\n")


def _ask_master_password() -> str:
    return _secret("Мастер-пароль Telegram")


def _new_master_password() -> str:
    first = _secret(f"Придумайте мастер-пароль (не короче {MIN_PASSWORD_LENGTH} символов)")
    if _secret("Повторите пароль") != first:
        raise ChatstyleError("Пароли не совпадают.")
    return first


def _use_console_password_prompt() -> None:
    """В консоли мастер-пароль спрашивается без эха; окно спрашивает его у себя."""
    set_password_prompt(_ask_master_password)


def _prepare_vault(vault: Vault) -> None:
    """Создать хранилище, если его нет (спросив способ защиты), и открыть его."""
    if not vault.exists():
        typer.echo(
            "Вход в Telegram хранится в зашифрованном хранилище. Выберите защиту:\n"
            "  1 - мастер-пароль (рекомендуется: без пароля файл бесполезен)\n"
            "  2 - привязка к вашей учётной записи Windows (DPAPI, пароль не нужен)"
        )
        choice = typer.prompt("Ваш выбор", default="1")
        if choice.strip() == "2":
            vault.create(MODE_DPAPI)
        else:
            vault.create(MODE_PASSWORD, _new_master_password())
    unlock_interactively(vault)


def _ensure_keys(vault: Vault) -> None:
    """Ключи API: из окружения, .env или хранилища; если их нет, спросить и сохранить."""
    try:
        load_credentials_with_vault(vault)
        return
    except ChatstyleError:
        pass
    typer.echo("Нужны ключи Telegram API: https://my.telegram.org, раздел API development tools.")
    api_id = typer.prompt("api_id")
    api_hash = _secret("api_hash")
    TelegramLogin(vault=vault).save_keys(api_id, api_hash)


@app.command()
def login() -> None:
    """Войти в Telegram и сохранить сессию в зашифрованном хранилище (один раз, для tg:)."""
    typer.echo(
        "Будут запрошены номер телефона, код из Telegram и пароль двухфакторной защиты "
        "(если включена). Данные вводятся только в этом окне."
    )
    _use_console_password_prompt()
    vault = default_vault()
    try:
        _prepare_vault(vault)
        _ensure_keys(vault)
        name = TelethonFetcher(vault=vault).login()
    except ChatstyleError as exc:
        typer.echo(f"Ошибка: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Вход выполнен: {name}. Сессия сохранена в {vault.path} (зашифрована).")


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
    headers = ("Слов", "Сообщений", "Сходство", "Delta", "Impostors (итог)")
    if result.morph:
        headers += ("Части речи",)
    if result.charlm:
        headers += ("Яз. модель",)
    if result.wordgrams:
        headers += ("Слова",)
    for header in headers:
        table.add_column(header, justify="right", no_wrap=True, min_width=len(header))

    for cand in result.candidates:
        cells = [
            cand.label,
            str(cand.words),
            str(cand.messages),
            f"{cand.similarity:.3f}",
            delta_text(cand),
            final_score_text(cand),
        ]
        if result.morph:
            cells.append(morph_text(cand))
        if result.charlm:
            cells.append(charlm_text(cand))
        if result.wordgrams:
            cells.append(wordgram_text(cand))
        table.add_row(*cells)

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
