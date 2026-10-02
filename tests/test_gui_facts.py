"""Коды ошибок формы и причины недоступности методов: основа для перевода окна."""

from pathlib import Path

import pytest
from chatstyle.delta import DEFAULT_CHUNK_WORDS, DEFAULT_MIN_CHUNKS, DeltaScore
from chatstyle.gui.model import CompareForm, FormError, check_compare_form, validate_compare_form
from chatstyle.impostors import DEFAULT_MIN_IMPOSTORS, ImpostorsScore
from chatstyle.pipeline import (
    AuthorStats,
    CandidateResult,
    ComparisonResult,
    unavailable_facts,
    unavailable_notes,
)


def _form(**changes: object) -> CompareForm:
    base = {"unknown": "file:u.txt", "candidates": ("file:a.txt",), "seed": 1}
    return CompareForm(**{**base, **changes})  # type: ignore[arg-type]


def test_correct_form_has_no_errors() -> None:
    assert check_compare_form(_form()) == []
    assert validate_compare_form(_form()) == []


@pytest.mark.parametrize(
    ("form", "expected"),
    [
        (_form(unknown=""), [FormError("unknown_missing")]),
        (_form(candidates=()), [FormError("no_candidates")]),
        (
            _form(candidates=("file:a.txt", "file:a.txt")),
            [FormError("duplicate_candidate", {"spec": "file:a.txt"})],
        ),
        (
            _form(candidates=("file:u.txt",)),
            [FormError("same_as_unknown", {"spec": "file:u.txt"})],
        ),
        (_form(seed=None), [FormError("bad_seed")]),
        (_form(seed=-1), [FormError("bad_seed")]),
    ],
)
def test_check_compare_form_codes(form: CompareForm, expected: list[FormError]) -> None:
    assert check_compare_form(form) == expected


def test_missing_impostors_folder_and_bad_report_format(tmp_path: Path) -> None:
    missing = str(tmp_path / "нет")
    errors = check_compare_form(_form(impostors_dir=missing, report_path=str(tmp_path / "r.pdf")))
    assert errors[0] == FormError("impostors_dir_missing", {"path": missing})
    assert errors[1].code == "report_format" and errors[1].params["message"]


def test_validate_compare_form_keeps_the_russian_texts() -> None:
    form = _form(unknown="", candidates=("file:a.txt", "file:a.txt"), seed=None)
    assert validate_compare_form(form) == [
        "Укажите неизвестного автора.",
        "Кандидат указан дважды: file:a.txt",
        "Seed должен быть целым неотрицательным числом.",
    ]


def _candidate(label: str, delta_ok: bool | None, impostors: ImpostorsScore | None):
    delta = None if delta_ok is None else DeltaScore(delta_ok, 0.5, 5, ())
    return CandidateResult(
        label=label,
        words=1200,
        messages=100,
        similarity=0.4,
        delta=delta,
        impostors_score=impostors,
    )


def _result(*candidates: CandidateResult) -> ComparisonResult:
    return ComparisonResult("u", AuthorStats(1200, 100), tuple(candidates))


def test_unavailable_facts_empty_when_every_method_is_available_or_not_run() -> None:
    ok = ImpostorsScore(True, 0.5, DEFAULT_MIN_IMPOSTORS, 100)
    assert unavailable_facts(_result(_candidate("a", True, ok), _candidate("b", None, None))) == []
    assert unavailable_notes(_result(_candidate("a", True, ok))) == []


def test_unavailable_facts_groups_candidates_by_reason_in_a_stable_order() -> None:
    few = ImpostorsScore(False, 0.0, 1, 0)
    short = ImpostorsScore(False, 0.0, DEFAULT_MIN_IMPOSTORS, 0)
    result = _result(
        _candidate("a", False, few),
        _candidate("b", False, few),
        _candidate("c", True, short),
    )
    facts = unavailable_facts(result)
    assert [fact["code"] for fact in facts] == ["delta_short", "impostors_few", "impostors_short"]
    assert facts[0]["labels"] == ["a", "b"]
    assert facts[0]["min_chunks"] == DEFAULT_MIN_CHUNKS
    assert facts[0]["chunk_words"] == DEFAULT_CHUNK_WORDS
    assert facts[1] == {
        "code": "impostors_few",
        "labels": ["a", "b"],
        "count": 1,
        "need": DEFAULT_MIN_IMPOSTORS,
    }
    assert facts[2]["labels"] == ["c"]
    assert len(unavailable_notes(result)) == len(facts)
