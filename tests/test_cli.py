from pathlib import Path

import pytest
from chatstyle import cli as cli_module
from chatstyle.cli import app
from chatstyle.collectors import telegram as tg
from chatstyle.errors import ChatstyleError
from typer.testing import CliRunner

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def invoke(args: list[str]) -> pytest.CaptureFixture:
    """Invoke the CLI with given arguments."""
    return runner.invoke(app, args, env={"COLUMNS": "200"})


@pytest.fixture
def fixtures_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Change working directory to the fixtures directory."""
    monkeypatch.chdir(FIXTURES)


def test_compare_success(fixtures_cwd: None) -> None:
    args = [
        "compare",
        "-u",
        "file:unknown.txt",
        "-c",
        "file:other.txt",
        "-c",
        "file:same.txt",
    ]
    result = invoke(args)
    assert result.exit_code == 0
    output = result.output
    assert "file:same.txt" in output
    assert "file:other.txt" in output
    assert "Неизвестный автор: file:unknown.txt" in output
    assert "Сходство" in output


def test_rows_sorted_by_similarity(fixtures_cwd: None) -> None:
    args = [
        "compare",
        "-u",
        "file:unknown.txt",
        "-c",
        "file:other.txt",
        "-c",
        "file:same.txt",
    ]
    result = invoke(args)
    output = result.output
    start = output.find("Сходство")
    assert start != -1
    idx_same = output.find("file:same.txt", start)
    idx_other = output.find("file:other.txt", start)
    assert idx_same < idx_other


def test_disclaimer_and_low_volume_warning(fixtures_cwd: None) -> None:
    args = [
        "compare",
        "-u",
        "file:unknown.txt",
        "-c",
        "file:other.txt",
        "-c",
        "file:same.txt",
    ]
    result = invoke(args)
    output = result.output.lower()
    assert "не доказательство авторства" in output
    assert "меньше 1000 слов" in output


def test_long_option_names(fixtures_cwd: None) -> None:
    args = [
        "compare",
        "--unknown",
        "file:unknown.txt",
        "--candidate",
        "file:same.txt",
    ]
    result = invoke(args)
    assert result.exit_code == 0


def test_missing_file(fixtures_cwd: None) -> None:
    args = ["compare", "-u", "file:nope_xyz.txt", "-c", "file:same.txt"]
    result = invoke(args)
    assert result.exit_code == 2
    assert "Ошибка:" in result.output


def test_tg_source_without_keys(fixtures_cwd: None) -> None:
    args = ["compare", "-u", "tg:@user", "-c", "file:same.txt"]
    result = invoke(args)
    assert result.exit_code == 2
    assert "my.telegram.org" in result.output


def test_not_utf8_source(fixtures_cwd: None) -> None:
    args = ["compare", "-u", "file:not_utf8.txt", "-c", "file:same.txt"]
    result = invoke(args)
    assert result.exit_code == 2
    assert "UTF-8" in result.output


def test_missing_candidate_option(fixtures_cwd: None) -> None:
    args = ["compare", "-u", "file:unknown.txt"]
    result = invoke(args)
    assert result.exit_code == 2


def test_duplicate_candidate(fixtures_cwd: None) -> None:
    args = [
        "compare",
        "-u",
        "file:unknown.txt",
        "-c",
        "file:same.txt",
        "-c",
        "file:same.txt",
    ]
    result = invoke(args)
    assert result.exit_code == 2
    assert "дважды" in result.output.lower()


def test_version(fixtures_cwd: None) -> None:
    args = ["--version"]
    result = invoke(args)
    assert result.exit_code == 0
    output = result.output
    assert "chatstyle 0.1.0" in output
    assert "ядро 0.1.0" in output


def test_help(fixtures_cwd: None) -> None:
    result = invoke(["--help"])
    assert result.exit_code == 0
    assert "compare" in result.output

    result2 = invoke(["compare", "--help"])
    assert result2.exit_code == 0
    assert "--unknown" in result2.output


def test_no_args_shows_help(fixtures_cwd: None) -> None:
    result = invoke([])
    assert "compare" in result.output


def test_compare_with_tgexport(fixtures_cwd: None) -> None:
    args = [
        "compare",
        "-u",
        "tgexport:result.json#Борис",
        "-c",
        "tgexport:result.json#Анна Петрова",
        "-c",
        "file:same.txt",
    ]
    result = invoke(args)
    assert result.exit_code == 0
    assert "tgexport:result.json#Анна Петрова" in result.output
    assert "file:same.txt" in result.output
    assert "Неизвестный автор: tgexport:result.json#Борис" in result.output


def test_compare_tgexport_unknown_sender(fixtures_cwd: None) -> None:
    result = invoke(["compare", "-u", "tgexport:result.json#Вася", "-c", "file:same.txt"])
    assert result.exit_code == 2
    assert "Ошибка:" in result.output
    assert "Анна Петрова" in result.output


class FakeTelegram:
    """Подмена TelethonFetcher для CLI: без сети и без файлов пользователя."""

    instances: list["FakeTelegram"] = []

    def __init__(self) -> None:
        self.fetched: list[tuple[tg.TelegramSource, int]] = []
        FakeTelegram.instances.append(self)

    def fetch(self, source: tg.TelegramSource, limit: int) -> list[str]:
        self.fetched.append((source, limit))
        return ["ну привет))", "короче я щас дома", "типа весь день сидел за компом))"]

    def login(self) -> str:
        return "Иван Петров"


@pytest.fixture
def fake_telegram(monkeypatch: pytest.MonkeyPatch) -> type[FakeTelegram]:
    FakeTelegram.instances = []
    monkeypatch.setattr(tg, "TelethonFetcher", FakeTelegram)
    monkeypatch.setattr(cli_module, "TelethonFetcher", FakeTelegram)
    return FakeTelegram


def test_compare_with_tg_source(fixtures_cwd: None, fake_telegram: type[FakeTelegram]) -> None:
    args = ["compare", "-u", "tg:@boris", "-c", "file:same.txt", "--limit", "50"]
    result = invoke(args)
    assert result.exit_code == 0
    assert "Неизвестный автор: tg:@boris" in result.output
    assert "загружено из Telegram 3" in result.output
    assert fake_telegram.instances[0].fetched == [(tg.TelegramSource("@boris", "@boris"), 50)]


def test_tg_source_second_run_uses_cache_and_refresh_bypasses_it(
    fixtures_cwd: None, fake_telegram: type[FakeTelegram]
) -> None:
    args = ["compare", "-u", "tg:@g#@u", "-c", "file:same.txt"]
    assert invoke(args).exit_code == 0
    second = invoke(args)
    assert second.exit_code == 0
    assert "из кэша" in second.output
    refreshed = invoke([*args, "--refresh"])
    assert refreshed.exit_code == 0
    assert "загружено из Telegram" in refreshed.output
    fetches = sum(len(instance.fetched) for instance in fake_telegram.instances)
    assert fetches == 2


def test_default_limit_is_3000(fixtures_cwd: None, fake_telegram: type[FakeTelegram]) -> None:
    invoke(["compare", "-u", "tg:@boris", "-c", "file:same.txt"])
    assert fake_telegram.instances[0].fetched[0][1] == 3000


def test_limit_must_be_positive(fixtures_cwd: None) -> None:
    result = invoke(["compare", "-u", "file:unknown.txt", "-c", "file:same.txt", "--limit", "0"])
    assert result.exit_code == 2


def test_login_success(fake_telegram: type[FakeTelegram]) -> None:
    result = invoke(["login"])
    assert result.exit_code == 0
    assert "Вход выполнен: Иван Петров" in result.output
    assert "telegram.session" in result.output


def test_login_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Failing:
        def login(self) -> str:
            raise ChatstyleError("нет ключей")

    monkeypatch.setattr(cli_module, "TelethonFetcher", Failing)
    result = invoke(["login"])
    assert result.exit_code == 2
    assert "Ошибка: нет ключей" in result.output


def test_features_command(fixtures_cwd: None) -> None:
    result = invoke(["features", "file:same.txt"])
    assert result.exit_code == 0
    assert "Автор: file:same.txt — " in result.output
    assert "«))» на сообщение" in result.output
    assert "доля сообщений с заглавной буквы" in result.output
    assert "Частые слова-паразиты: ну " in result.output
    assert "Частые служебные слова:" in result.output


def test_features_top_limits_word_lists(fixtures_cwd: None) -> None:
    result = invoke(["features", "file:same.txt", "--top", "1"])
    assert result.exit_code == 0
    line = next(x for x in result.output.splitlines() if x.startswith("Частые слова-паразиты"))
    assert line.count(",") == 0


def test_features_error_has_exit_code_2(fixtures_cwd: None) -> None:
    result = invoke(["features", "file:nope_xyz.txt"])
    assert result.exit_code == 2
    assert "Ошибка:" in result.output


def test_features_help_lists_command() -> None:
    result = invoke(["--help"])
    assert "features" in result.output
