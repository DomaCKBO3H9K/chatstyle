import sys
from pathlib import Path

import pytest

# Пропускаем тесты, если pymorphy3 недоступен (они сами проверяют отсутствие)
pytest.importorskip("pymorphy3")

# ------------------------------
# Импортируем необходимые части проекта
# ------------------------------
from chatstyle.errors import CodedError
from chatstyle.features import ALL_STYLE_GROUPS, morph_summary
from chatstyle.morph import ALL_CODES, reset_cache
from chatstyle.pipeline import (
    CandidateResult,
    compare_messages,
    morph_text,
    profile_author,
    run_comparison,
)

# ------------------------------
# Вспомогательная функция для чтения фикстур
# ------------------------------
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def fixtures_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Источники задаются относительными путями file:unknown.txt: рабочая папка — фикстуры."""
    monkeypatch.chdir(FIXTURES_DIR)


def read_fixture(name: str) -> list[str]:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8").splitlines()


# ------------------------------
# 1. run_comparison с morph / без morph
# ------------------------------
def test_run_comparison_morph_and_without(monkeypatch):
    # переходим в директорию с фикстурами
    monkeypatch.chdir(FIXTURES_DIR)

    # --- с morph ---
    result = run_comparison(
        "file:unknown.txt",
        ["file:same.txt", "file:other.txt"],
        morph=True,
    )
    assert result.morph is True

    # проверяем, что у каждого кандидата есть значение morph_similarity в диапазоне [0, 1]
    for cand in result.candidates:
        assert cand.morph_similarity is not None
        assert 0.0 <= cand.morph_similarity <= 1.0

    # ищем кандидатов по метке (label)
    same_cand = next(c for c in result.candidates if c.label == "file:same.txt")
    other_cand = next(c for c in result.candidates if c.label == "file:other.txt")
    assert same_cand.morph_similarity > other_cand.morph_similarity

    # --- без morph ---
    result_no = run_comparison(
        "file:unknown.txt",
        ["file:same.txt", "file:other.txt"],
        morph=False,
    )
    assert result_no.morph is False
    for cand in result_no.candidates:
        assert cand.morph_similarity is None


# ------------------------------
# 2. morph_text
# ------------------------------
def test_morph_text_formatting():
    cand_with = CandidateResult(
        label="x",
        words=1,
        messages=1,
        similarity=0.5,
        morph_similarity=0.6489,
    )
    cand_none = CandidateResult(
        label="y",
        words=1,
        messages=1,
        similarity=0.5,
        morph_similarity=None,
    )
    assert morph_text(cand_with) == "0.649"
    assert morph_text(cand_none) == "—"


# ------------------------------
# 3. regression по style_groups
# ------------------------------
def test_style_groups_propagation(monkeypatch):
    import chatstyle.pipeline as pipeline

    captured = {}

    original = pipeline.burrows_delta

    def wrapper(*args, **kwargs):
        captured["kwargs"] = kwargs
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline, "burrows_delta", wrapper)

    unknown = read_fixture("unknown.txt")
    same = read_fixture("same.txt")

    # вызов с пустым кортежем
    compare_messages(unknown, {"a": same}, style_groups=())
    assert captured["kwargs"].get("groups") == ()

    # вызов без указания style_groups (по умолчанию)
    captured.clear()
    compare_messages(unknown, {"a": same})
    assert captured["kwargs"].get("groups") == ALL_STYLE_GROUPS

    # проверяем, что run_comparison тоже передаёт аргумент дальше
    captured.clear()
    monkeypatch.chdir(FIXTURES_DIR)
    run_comparison("file:unknown.txt", ["file:same.txt"], style_groups=())
    assert captured["kwargs"].get("groups") == ()


# ------------------------------
# 4. профиль и morph_summary
# ------------------------------
def test_profile_morph_features_and_summary():
    # профиль с morph
    profile = profile_author("file:same.txt", morph=True)
    features = profile.morph_features
    assert isinstance(features, dict)
    # все ключи начинаются с "m:" и код из ALL_CODES
    for key, value in features.items():
        assert key.startswith("m:")
        code = key.split(":", 1)[1]
        assert code in ALL_CODES
        assert 0.0 <= value <= 1.0
    # сумма приближённо 1
    assert sum(features.values()) == pytest.approx(1.0, rel=1e-3)

    # без morph – поле None
    profile_no = profile_author("file:same.txt", morph=False)
    assert profile_no.morph_features is None

    # проверка формата summary
    summary = morph_summary(features)
    assert summary.startswith("Части речи:")
    # в типичном наборе POS_LABELS встречается слово "существительные"
    assert "существительные" in summary.lower()


# ------------------------------
# 5. отсутствие pymorphy3 – ожидаем CodedError
# ------------------------------
def test_missing_morph_dependency(monkeypatch):
    # имитируем отсутствие модуля pymorphy3
    monkeypatch.setitem(sys.modules, "pymorphy3", None)
    # сбрасываем кэш, чтобы модуль заново проверил наличие зависимости
    reset_cache()

    # run_comparison должен бросить CodedError с кодом "morph_missing"
    with pytest.raises(CodedError) as excinfo:
        run_comparison("file:unknown.txt", ["file:same.txt"], morph=True)
    assert excinfo.value.code == "morph_missing"

    # profile_author тоже должен бросить ту же ошибку
    with pytest.raises(CodedError) as excinfo2:
        profile_author("file:same.txt", morph=True)
    assert excinfo2.value.code == "morph_missing"

    # после теста восстанавливаем кеш (чтобы последующие тесты, если они появятся, не падали)
    reset_cache()
