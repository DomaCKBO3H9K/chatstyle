"""Переводы окна: одинаковые наборы ключей и плейсхолдеров, нет пропусков и мёртвых ключей."""

import json
import re
from importlib import resources
from pathlib import Path

import pytest
from chatstyle.delta import DeltaScore
from chatstyle.features import FEATURE_LABELS, FEATURE_SECTIONS, RHYTHM_LABELS
from chatstyle.gui.model import _FORM_ERROR_TEXTS
from chatstyle.impostors import DEFAULT_MIN_IMPOSTORS, ImpostorsScore
from chatstyle.morph import ALL_CODES
from chatstyle.pipeline import (
    DISCLAIMER,
    METHOD_NAMES,
    AuthorStats,
    CandidateResult,
    ComparisonResult,
    unavailable_facts,
)
from chatstyle.securestore import MODES

WEB = Path(str(resources.files("chatstyle").joinpath("gui", "web")))
CODES = ("ru", "en", "ar", "es", "zh", "fr")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
# подписи, в которых русские буквы и слова сами являются примером («ё», «тся», «приветттт»)
CYRILLIC_EXAMPLES = {
    "feature.f:yo_ratio",
    "feature.o:tsya_share",
    "feature.o:repeat_letters",
}


def _read(*parts: str) -> str:
    return WEB.joinpath(*parts).read_text(encoding="utf-8")


def _dictionary(code: str) -> dict[str, str]:
    text = _read("lang", f"{code}.js")
    match = re.fullmatch(rf'registerLanguage\("{code}", (\{{.*\}})\);\s*', text, re.DOTALL)
    assert match, f"{code}.js должен быть вызовом registerLanguage с JSON-словарём"
    return json.loads(match.group(1))


DICTIONARIES = {code: _dictionary(code) for code in CODES}


def test_supported_languages_match_files_and_page() -> None:
    declared = re.findall(r'\{ code: "(\w+)", name: "[^"]+", dir: "(ltr|rtl)" \}', _read("i18n.js"))
    assert [code for code, _ in declared] == list(CODES)
    assert {code for code, direction in declared if direction == "rtl"} == {"ar"}
    page = _read("index.html")
    for code in CODES:
        assert f'<script src="lang/{code}.js"></script>' in page
    assert sorted(path.stem for path in WEB.joinpath("lang").glob("*.js")) == sorted(CODES)


@pytest.mark.parametrize("code", CODES)
def test_every_language_has_the_same_keys_as_russian(code: str) -> None:
    assert list(DICTIONARIES[code]) == list(DICTIONARIES["ru"])


@pytest.mark.parametrize("code", CODES)
def test_translations_are_not_empty_and_keep_placeholders(code: str) -> None:
    for key, source in DICTIONARIES["ru"].items():
        text = DICTIONARIES[code][key]
        assert text.strip(), f"{code}: пустой перевод {key}"
        assert set(PLACEHOLDER.findall(text)) == set(PLACEHOLDER.findall(source)), (code, key)


def test_russian_disclaimer_is_the_one_from_the_core() -> None:
    assert DICTIONARIES["ru"]["disclaimer"] == DISCLAIMER


def test_non_russian_languages_are_really_translated() -> None:
    russian = DICTIONARIES["ru"]
    for code in ("en", "ar", "es", "zh", "fr"):
        same = [
            k for k, v in DICTIONARIES[code].items() if v == russian[k] and re.search("[а-яё]", v)
        ]
        assert same == [], f"{code}: не переведено {same}"
        assert not any(
            re.search("[а-яёА-ЯЁ]", v)
            for k, v in DICTIONARIES[code].items()
            if k not in CYRILLIC_EXAMPLES
        ), code


def _static_keys() -> set[str]:
    keys: set[str] = set()
    for name in ("app.js", "i18n.js"):
        keys.update(re.findall(r'\bt(?:Nodes)?\("([\w.:+]+)"', _read(name)))
        keys.update(re.findall(r't\(\s*(?:state\.\w+ === "\w+" \? )?"([\w.]+)"', _read(name)))
    page = _read("index.html")
    keys.update(re.findall(r'data-i18n(?:-placeholder|-aria)?="([\w.]+)"', page))
    for name in ("app.js", "i18n.js"):
        # любой строковый литерал вида «раздел.ключ» (ключи передают и аргументами функций)
        keys.update(re.findall(r'"([a-z_]+(?:\.[a-z_0-9:+]+)+)"', _read(name)))
    keys -= {"app.js"}
    return keys


def _dynamic_keys() -> set[str]:
    api = Path(str(resources.files("chatstyle").joinpath("gui", "api.py"))).read_text(
        encoding="utf-8"
    )
    pipeline = Path(str(resources.files("chatstyle").joinpath("pipeline.py"))).read_text(
        encoding="utf-8"
    )
    coded = "".join(
        Path(str(resources.files("chatstyle").joinpath(*parts))).read_text(encoding="utf-8")
        for parts in (
            ("collectors", "telegram.py"),
            ("collectors", "telegram_login.py"),
            ("securestore.py",),
            ("morph.py",),
        )
    )
    coded_codes = set(
        re.findall(r'(?:CodedError|TelegramLoginError|VaultError)\(\s*"(\w+)"', coded)
    )
    error_codes = (
        set(_FORM_ERROR_TEXTS)
        | set(re.findall(r'error\("(\w+)"', api))
        | coded_codes
        | {"unexpected"}
    )
    fact_codes = set(re.findall(r'"code": "(\w+)"', pipeline))
    keys = {f"error.{code}" for code in error_codes}
    keys |= {f"note.{code}" for code in fact_codes}
    keys |= {f"feature.{key}" for key in FEATURE_LABELS}
    keys |= {f"method.{method}" for method in METHOD_NAMES}
    keys |= {f"metric.{m}" for m in ("impostors", "cosine", "delta")}
    keys |= {f"result.summary.{m}" for m in ("impostors", "cosine", "delta")}
    keys |= {f"note.ranking.{m}" for m in ("impostors", "cosine", "delta")}
    keys |= {"profile.fw", "profile.fl", "profile.ms"}
    keys |= {f"section.{section}" for section in FEATURE_SECTIONS}
    keys |= {f"error.{code}" for code in re.findall(r'"(vault_\w+)"', coded)}  # выбираются условием
    keys |= {f"tg.mode.{mode}" for mode in MODES} | {f"tg.mode.{mode}.desc" for mode in MODES}
    keys |= {f"pos.{code}" for code in ALL_CODES}
    keys |= {f"rhythm.{key}" for key in RHYTHM_LABELS}
    keys |= {"note.agree", "note.disagree"}  # выбираются тернарным оператором в noteText
    return keys


def test_every_key_used_by_the_page_exists_and_no_key_is_dead() -> None:
    known = set(DICTIONARIES["ru"])
    used = _static_keys() | _dynamic_keys()
    assert used - known == set(), f"в словарях нет: {sorted(used - known)}"
    assert known - used == set(), f"мёртвые ключи: {sorted(known - used)}"


def _result_with_every_note() -> ComparisonResult:
    few = ImpostorsScore(False, 0.0, 1, 0)
    short = ImpostorsScore(False, 0.0, DEFAULT_MIN_IMPOSTORS, 0)
    rows = (
        CandidateResult(
            "a", 1200, 100, 0.4, delta=DeltaScore(False, 0.5, 5, ()), impostors_score=few
        ),
        CandidateResult(
            "b", 1200, 100, 0.4, delta=DeltaScore(True, 0.5, 5, ()), impostors_score=short
        ),
    )
    return ComparisonResult("u", AuthorStats(1200, 100), rows)


def test_note_placeholders_match_the_parameters_python_sends() -> None:
    facts = unavailable_facts(_result_with_every_note())
    assert {fact["code"] for fact in facts} == {"delta_short", "impostors_few", "impostors_short"}
    for fact in facts:
        params = set(fact) - {"code"}
        for code in CODES:
            placeholders = set(PLACEHOLDER.findall(DICTIONARIES[code][f"note.{fact['code']}"]))
            assert placeholders == params, (code, fact["code"])


def test_error_placeholders_match_the_parameters_python_sends() -> None:
    sent = {
        "duplicate_candidate": {"spec"},
        "same_as_unknown": {"spec"},
        "impostors_dir_missing": {"path"},
        "report_format": {"message"},
        "core": {"message"},
        "flood_wait": {"minutes"},
        "telegram": {"reason"},
        "unexpected": {"message"},
    }
    for code in CODES:
        for error, params in sent.items():
            text = DICTIONARIES[code][f"error.{error}"]
            assert set(PLACEHOLDER.findall(text)) == params, (code, error)
