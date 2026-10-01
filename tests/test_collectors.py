from pathlib import Path

import pytest
from chatstyle.collectors import collect, split_spec
from chatstyle.collectors.txt import read_txt
from chatstyle.errors import ChatstyleError

FIXTURES = Path(__file__).parent / "fixtures"


def test_read_txt_utf8(tmp_path: Path) -> None:
    file = tmp_path / "test.txt"
    file.write_bytes("привет\nмир\n".encode())
    result = read_txt(file)
    assert result == ["привет", "мир"]


def test_read_txt_bom_and_crlf(tmp_path: Path) -> None:
    file = tmp_path / "bom.txt"
    content = b"\xef\xbb\xbf" + "привет\r\nмир".encode()
    file.write_bytes(content)
    result = read_txt(file)
    assert result == ["привет", "мир"]


def test_read_txt_keeps_empty_lines(tmp_path: Path) -> None:
    file = tmp_path / "empty.txt"
    file.write_bytes(b"a\n\nb")
    result = read_txt(file)
    assert result == ["a", "", "b"]


def test_read_txt_not_utf8_raises() -> None:
    path = FIXTURES / "not_utf8.txt"
    with pytest.raises(ChatstyleError) as exc_info:
        read_txt(path)
    assert "UTF-8" in str(exc_info.value)


def test_read_txt_missing_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "nope.txt"
    with pytest.raises(ChatstyleError):
        read_txt(path)


def test_read_txt_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(ChatstyleError):
        read_txt(tmp_path)


@pytest.mark.parametrize(
    "spec, expected",
    [
        ("file:a.txt", ("file", "a.txt")),
        ("FILE:a.txt", ("file", "a.txt")),
        (r"file:C:\data\a.txt", ("file", r"C:\data\a.txt")),
        ("tg:@user", ("tg", "@user")),
    ],
)
def test_split_spec(spec: str, expected: tuple[str, str]) -> None:
    assert split_spec(spec) == expected


@pytest.mark.parametrize(
    "spec",
    [
        "a.txt",
        ":a.txt",
        "file:",
        "",
    ],
)
def test_split_spec_invalid(spec: str) -> None:
    with pytest.raises(ChatstyleError) as exc_info:
        split_spec(spec)
    if spec == "a.txt":
        assert "file:" in str(exc_info.value)


def test_collect_file() -> None:
    path = FIXTURES / "unknown.txt"
    spec = f"file:{path}"
    result = collect(spec)
    assert len(result) > 10
    assert result[0] == "ну привет))"


def test_collect_tg_without_keys_explains(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ChatstyleError) as exc_info:
        collect("tg:@user")
    assert "my.telegram.org" in str(exc_info.value)


def test_collect_tgexport() -> None:
    result = collect(f"tgexport:{FIXTURES / 'result.json'}#Анна Петрова")
    assert len(result) == 5
    assert result[0] == "привет))"
    assert result[-1] == "ладно))\nщас дойду"


def test_collect_tgexport_strips_sender() -> None:
    result = collect(f"tgexport:{FIXTURES / 'result.json'}#  Борис  ")
    assert result == ["Привет. Как дела?", "Посмотрю вечером.", "ок"]


@pytest.mark.parametrize(
    "spec",
    [
        f"tgexport:{FIXTURES / 'result.json'}",
        f"tgexport:{FIXTURES / 'result.json'}#",
        f"tgexport:{FIXTURES / 'result.json'}#   ",
        "tgexport:#Анна",
    ],
)
def test_collect_tgexport_without_sender(spec: str) -> None:
    with pytest.raises(ChatstyleError) as exc_info:
        collect(spec)
    assert "имя отправителя" in str(exc_info.value)


def test_collect_tgexport_unknown_sender() -> None:
    with pytest.raises(ChatstyleError) as exc_info:
        collect(f"tgexport:{FIXTURES / 'result.json'}#Вася")
    assert "не найден" in str(exc_info.value)


def test_collect_unknown_scheme() -> None:
    with pytest.raises(ChatstyleError) as exc_info:
        collect("ftp:x")
    assert "Неизвестный" in str(exc_info.value)
