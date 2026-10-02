import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from chatstyle import _core
from chatstyle.cache import load_cached, store_cached
from chatstyle.cli import app
from chatstyle.collectors.telegram import TelegramSource, _message_time, read_telegram
from chatstyle.collectors.tg_export import read_tg_export
from chatstyle.features import RHYTHM_LABELS, rhythm_summary
from chatstyle.gui.api import Api, compare_view_dict, profile_view_dict
from chatstyle.gui.model import CompareOutcome
from chatstyle.pipeline import CandidateResult, profile_author, rhythm_text, run_comparison
from chatstyle.preprocess import preprocess_timed
from chatstyle.report import write_report
from chatstyle.timeline import Messages, known_times, local_seconds, parse_export_date
from typer.testing import CliRunner

runner = CliRunner()
START = datetime(2024, 3, 4, 12, 0, 0)  # понедельник


def write_export(path: Path, senders: dict[str, tuple[datetime, int, str]]) -> Path:
    """Экспорт чата: {имя: (начало, шаг в секундах, число сообщений)} — по 40 сообщений и т.п."""
    records = []
    for number, (name, (start, step, count)) in enumerate(senders.items()):
        for index in range(count):
            moment = start + timedelta(seconds=step * index)
            records.append(
                {
                    "id": len(records),
                    "type": "message",
                    "date": moment.isoformat(timespec="seconds"),
                    "from": name,
                    "from_id": f"user{number}",
                    "text": f"сообщение номер {index} от {name}",
                }
            )
    path.write_text(json.dumps({"messages": records}, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def chat(tmp_path: Path) -> Path:
    """Анна пишет днём сериями, Борис — ночью редко, Вера — днём сериями, как Анна."""
    return write_export(
        tmp_path / "chat.json",
        {
            "Анна": (START, 20, 40),
            "Борис": (START.replace(hour=1), 5000, 40),
            "Вера": (START.replace(hour=13), 25, 40),
        },
    )


def spec(chat: Path, name: str) -> str:
    return f"tgexport:{chat}#{name}"


def test_messages_check_the_number_of_times() -> None:
    with pytest.raises(ValueError, match="Число моментов"):
        Messages(["a", "b"], [1])
    assert Messages(["a"]).times is None
    assert Messages(["a"], [5]).times == [5]


def test_local_seconds_and_export_dates() -> None:
    assert local_seconds(datetime(1970, 1, 2, 0, 0, 1)) == 86401
    aware = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    assert local_seconds(aware) == local_seconds(aware.astimezone().replace(tzinfo=None))
    assert parse_export_date("1970-01-01T00:00:10") == 10
    for bad in (None, 5, "вчера", ""):
        assert parse_export_date(bad) is None


def test_known_times_skips_missing_moments() -> None:
    assert known_times(Messages(["a", "b", "c"], [3, None, 1])) == [3, 1]
    assert known_times(["a", "b"]) == []


def test_preprocess_timed_keeps_times_aligned() -> None:
    raw = Messages(["один", "   ", "https://x.y", "смотри https://x.y", "три"], [1, 2, 3, 4, 5])
    cleaned = preprocess_timed(raw)
    assert list(cleaned) == ["один", "смотри <URL>", "три"]
    assert cleaned.times == [1, 4, 5]
    assert preprocess_timed(["один", " "]).times is None


def test_export_reader_attaches_times(chat: Path) -> None:
    messages = read_tg_export(chat, "Анна")
    assert len(messages) == 40
    assert messages.times is not None
    assert messages.times[1] - messages.times[0] == 20


def test_cache_round_trip_with_times_and_old_version_is_ignored(tmp_path: Path) -> None:
    store_cached("@чат", "@он", 10, Messages(["a", "b"], [100, None]), tmp_path)
    loaded = load_cached("@чат", "@он", 10, tmp_path)
    assert loaded is not None
    assert list(loaded) == ["a", "b"]
    assert loaded.times == [100, None]

    store_cached("@чат", "@он", 11, ["без", "времени"], tmp_path)
    plain = load_cached("@чат", "@он", 11, tmp_path)
    assert plain is not None and plain.times is None

    for file in tmp_path.glob("*.json"):
        data = json.loads(file.read_text(encoding="utf-8"))
        data["version"] = 1
        file.write_text(json.dumps(data), encoding="utf-8")
    assert load_cached("@чат", "@он", 10, tmp_path) is None


def test_cache_rejects_times_of_wrong_length(tmp_path: Path) -> None:
    store_cached("@чат", "@он", 12, Messages(["a", "b"], [1, 2]), tmp_path)
    for file in tmp_path.glob("*.json"):
        data = json.loads(file.read_text(encoding="utf-8"))
        data["times"] = [1]
        file.write_text(json.dumps(data), encoding="utf-8")
    assert load_cached("@чат", "@он", 12, tmp_path) is None


class _Fetcher:
    def fetch(self, source: TelegramSource, limit: int) -> Messages:
        return Messages(["привет", "пока"], [10, 20])


def test_read_telegram_stores_times_in_cache(tmp_path: Path) -> None:
    first = read_telegram("@друг", fetcher=_Fetcher(), cache_directory=tmp_path)
    assert getattr(first, "times", None) == [10, 20]
    again = read_telegram("@друг", cache_directory=tmp_path)
    assert getattr(again, "times", None) == [10, 20]


def test_message_time_from_telethon_message() -> None:
    class Fake:
        date = datetime(2024, 5, 6, 7, 8, 9, tzinfo=UTC)

    assert _message_time(Fake()) == local_seconds(Fake.date)

    class Naive:
        date = datetime(1970, 1, 1, 0, 0, 5)

    assert _message_time(Naive()) == 5

    class NoDate:
        pass

    assert _message_time(NoDate()) is None


def test_core_profile_and_compare_bindings() -> None:
    times = [1_000_000 + 3600 * i for i in range(40)]
    profile = _core.rhythm_profile(times)
    assert profile["available"] is True
    assert list(profile["features"]) == list(RHYTHM_LABELS)
    short = _core.rhythm_profile(times[:5])
    assert short["available"] is False and short["messages"] == 5

    reports = _core.rhythm_compare(times, {"same": times, "few": times[:3]})
    assert reports["same"] == {"available": True, "similarity": pytest.approx(1.0)}
    assert reports["few"]["available"] is False


def test_rhythm_in_comparison_prefers_the_similar_author(chat: Path) -> None:
    result = run_comparison(
        spec(chat, "Анна"), [spec(chat, "Борис"), spec(chat, "Вера")], rhythm=True
    )
    assert result.rhythm is True
    scores = {item.label: item.rhythm_similarity for item in result.candidates}
    assert scores[spec(chat, "Вера")] > scores[spec(chat, "Борис")]

    plain = run_comparison(spec(chat, "Анна"), [spec(chat, "Борис"), spec(chat, "Вера")])
    assert plain.rhythm is False
    assert all(item.rhythm_similarity is None for item in plain.candidates)


def test_text_files_have_no_rhythm(chat: Path) -> None:
    fixtures = Path(__file__).parent / "fixtures"
    result = run_comparison(
        f"file:{fixtures / 'unknown.txt'}", [f"file:{fixtures / 'same.txt'}"], rhythm=True
    )
    assert result.rhythm is True
    assert result.candidates[0].rhythm_similarity is None
    assert rhythm_text(result.candidates[0]) == "—"


def test_rhythm_text_format() -> None:
    shown = CandidateResult(
        label="x", words=1, messages=1, similarity=0.5, rhythm_similarity=0.8764
    )
    assert rhythm_text(shown) == "0.876"
    assert rhythm_text(CandidateResult(label="x", words=1, messages=1, similarity=0.5)) == "—"


def test_profile_has_rhythm_only_with_dates(chat: Path) -> None:
    dated = profile_author(spec(chat, "Анна"))
    assert dated.rhythm_features is not None
    assert list(dated.rhythm_features) == list(RHYTHM_LABELS)
    assert dated.rhythm_features["day"] == pytest.approx(1.0)
    assert dated.rhythm_features["burst_share"] == pytest.approx(1.0)

    fixtures = Path(__file__).parent / "fixtures"
    assert profile_author(f"file:{fixtures / 'same.txt'}").rhythm_features is None


def test_rhythm_summary_lists_all_features() -> None:
    line = rhythm_summary({key: 0.5 for key in RHYTHM_LABELS})
    assert line.startswith("Ритм:")
    assert all(label in line for label in RHYTHM_LABELS.values())


def test_cli_rhythm_column_and_hint(chat: Path) -> None:
    args = [
        "compare",
        "-u",
        spec(chat, "Анна"),
        "-c",
        spec(chat, "Борис"),
        "-c",
        spec(chat, "Вера"),
    ]
    with_flag = runner.invoke(app, [*args, "--rhythm"], env={"COLUMNS": "250"})
    assert with_flag.exit_code == 0
    assert "Ритм" in with_flag.output
    assert "Ритм недоступен" not in with_flag.output
    assert "Ритм" not in runner.invoke(app, args, env={"COLUMNS": "250"}).output

    fixtures = Path(__file__).parent / "fixtures"
    nodates = runner.invoke(
        app,
        [
            "compare",
            "-u",
            f"file:{fixtures / 'unknown.txt'}",
            "-c",
            f"file:{fixtures / 'same.txt'}",
            "--rhythm",
        ],
        env={"COLUMNS": "250"},
    )
    assert nodates.exit_code == 0
    assert "Ритм недоступен" in nodates.output


def test_cli_features_prints_rhythm(chat: Path) -> None:
    result = runner.invoke(app, ["features", spec(chat, "Анна")], env={"COLUMNS": "250"})
    assert result.exit_code == 0
    assert "Ритм:" in result.output


@pytest.mark.parametrize("suffix", ["md", "html"])
def test_reports_have_rhythm_header(tmp_path: Path, chat: Path, suffix: str) -> None:
    candidates = [spec(chat, "Борис"), spec(chat, "Вера")]
    with_rhythm = tmp_path / f"with.{suffix}"
    write_report(with_rhythm, run_comparison(spec(chat, "Анна"), candidates, rhythm=True))
    assert "Ритм (по времени)" in with_rhythm.read_text(encoding="utf-8")

    without = tmp_path / f"without.{suffix}"
    write_report(without, run_comparison(spec(chat, "Анна"), candidates))
    assert "Ритм (по времени)" not in without.read_text(encoding="utf-8")


def test_gui_views_have_rhythm(chat: Path) -> None:
    candidates = [spec(chat, "Борис"), spec(chat, "Вера")]
    view = compare_view_dict(
        CompareOutcome(run_comparison(spec(chat, "Анна"), candidates, rhythm=True), None)
    )
    assert view["rhythm"] is True
    assert all(re.fullmatch(r"\d\.\d{3}", item["rhythm"]) for item in view["candidates"])

    plain = compare_view_dict(CompareOutcome(run_comparison(spec(chat, "Анна"), candidates), None))
    assert plain["rhythm"] is False
    assert all(item["rhythm"] == "—" for item in plain["candidates"])

    profile = profile_view_dict(profile_author(spec(chat, "Анна")))
    assert [item["key"] for item in profile["rhythm"]] == list(RHYTHM_LABELS)
    fixtures = Path(__file__).parent / "fixtures"
    assert profile_view_dict(profile_author(f"file:{fixtures / 'same.txt'}"))["rhythm"] is None


def test_api_rejects_non_bool_rhythm() -> None:
    api = Api(allowed_paths=["u.txt", "a.txt"])
    answer = api.start_compare(
        {"unknown": "file:u.txt", "candidates": ["file:a.txt"], "rhythm": "yes"}
    )
    assert answer["ok"] is False
    assert {item["code"] for item in answer["errors"]} == {"bad_input"}
