from pathlib import Path

import pytest
from chatstyle.errors import ChatstyleError
from chatstyle.pipeline import MIN_WORDS, count_words, run_comparison

FIXTURES = Path(__file__).parent / "fixtures"


def test_count_words() -> None:
    assert count_words(["привет мир", "ну))"]) == 3
    assert count_words(["смотри <URL> тут", "<MENTION> привет"]) == 3
    assert count_words([]) == 0
    assert count_words(["))", "..."]) == 0


def test_min_words() -> None:
    assert MIN_WORDS == 1000


def test_ranking_same_author_first() -> None:
    unknown_spec = f"file:{FIXTURES / 'unknown.txt'}"
    same_spec = f"file:{FIXTURES / 'same.txt'}"
    other_spec = f"file:{FIXTURES / 'other.txt'}"
    result = run_comparison(unknown_spec, [other_spec, same_spec])
    labels = [c.label for c in result.candidates]
    assert labels == [same_spec, other_spec]
    assert result.candidates[0].similarity > result.candidates[1].similarity


def test_similarity_in_unit_interval() -> None:
    unknown_spec = f"file:{FIXTURES / 'unknown.txt'}"
    same_spec = f"file:{FIXTURES / 'same.txt'}"
    other_spec = f"file:{FIXTURES / 'other.txt'}"
    result = run_comparison(unknown_spec, [same_spec, other_spec])
    for c in result.candidates:
        assert 0.0 <= c.similarity <= 1.0


def test_stats() -> None:
    unknown_spec = f"file:{FIXTURES / 'unknown.txt'}"
    same_spec = f"file:{FIXTURES / 'same.txt'}"
    other_spec = f"file:{FIXTURES / 'other.txt'}"
    result = run_comparison(unknown_spec, [same_spec, other_spec])
    assert result.unknown.messages == 19
    assert result.unknown.words > 50
    same_candidate = [c for c in result.candidates if c.label == same_spec][0]
    assert same_candidate.messages == 19
    other_candidate = [c for c in result.candidates if c.label == other_spec][0]
    assert other_candidate.messages == 14
    assert other_candidate.words > 50


def test_no_candidates_raises() -> None:
    unknown_spec = f"file:{FIXTURES / 'unknown.txt'}"
    with pytest.raises(ChatstyleError):
        run_comparison(unknown_spec, [])


def test_duplicate_candidate_raises() -> None:
    unknown_spec = f"file:{FIXTURES / 'unknown.txt'}"
    same_spec = f"file:{FIXTURES / 'same.txt'}"
    with pytest.raises(ChatstyleError, match="дважды"):
        run_comparison(unknown_spec, [same_spec, same_spec])


def test_empty_after_preprocess_raises(tmp_path: Path) -> None:
    unknown_spec = f"file:{FIXTURES / 'unknown.txt'}"
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("[Фото]\nhttps://a.ru\n", encoding="utf-8")
    empty_spec = f"file:{empty_file}"
    with pytest.raises(ChatstyleError, match="не осталось сообщений"):
        run_comparison(unknown_spec, [empty_spec])
    with pytest.raises(ChatstyleError, match="не осталось сообщений"):
        run_comparison(empty_spec, [f"file:{FIXTURES / 'same.txt'}"])


def test_missing_file_propagates() -> None:
    same_spec = f"file:{FIXTURES / 'same.txt'}"
    with pytest.raises(ChatstyleError):
        run_comparison("file:nonexistent_xyz.txt", [same_spec])


def test_not_implemented_source() -> None:
    same_spec = f"file:{FIXTURES / 'same.txt'}"
    with pytest.raises(ChatstyleError):
        run_comparison("tg:@user", [same_spec])
