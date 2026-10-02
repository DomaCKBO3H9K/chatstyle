"""Логика графического интерфейса без окна: форма, проверка, фоновый запуск, представления.

Окно ничего не считает само: оно вызывает те же функции, что и CLI (`run_comparison`,
`profile_author`, `write_report`), а здесь только готовятся данные для показа. Благодаря этому
всё, кроме виджетов, проверяется обычными тестами без дисплея.
"""

import queue
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, TypeVar

from chatstyle.collectors import CollectOptions
from chatstyle.collectors.impostors import load_impostor_directory
from chatstyle.collectors.telegram import DEFAULT_LIMIT
from chatstyle.collectors.tg_export import TgSender
from chatstyle.errors import ChatstyleError
from chatstyle.features import FEATURE_LABELS, word_list_lines
from chatstyle.impostors import DEFAULT_SEED
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

RESULT_COLUMNS = ("Кандидат", "Слов", "Сообщений", "Сходство", "Delta", "Итоговая оценка")
PROFILE_COLUMNS = ("Признак", "Значение")
_EXPLICIT_SCHEMES = ("file", "tg", "tgexport")

T = TypeVar("T")


def normalize_source(text: str) -> str:
    """Источник из поля ввода: явная схема остаётся, голый путь становится `file:путь`."""
    value = text.strip().strip('"')
    if not value:
        return ""
    if value.partition(":")[0].lower() in _EXPLICIT_SCHEMES:
        return value
    return f"file:{value}"


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def short_labels(specs: Sequence[str]) -> dict[str, str]:
    """Короткие подписи источников для таблицы: имя файла вместо полного пути.

    `file:C:/data/a.txt` -> `a.txt`, `tgexport:C:/x/result.json#Анна` -> `result.json#Анна`.
    Если короткие подписи двух источников совпали, обоим остаётся полная строка.
    """
    shorts: dict[str, str] = {}
    for spec in specs:
        scheme, _, value = spec.partition(":")
        if scheme.lower() == "file" and value:
            shorts[spec] = _basename(value)
        elif scheme.lower() == "tgexport" and value:
            path, sep, sender = value.rpartition("#")
            shorts[spec] = f"{_basename(path)}#{sender}" if sep else _basename(value)
        else:
            shorts[spec] = spec
    counts: dict[str, int] = {}
    for short in shorts.values():
        counts[short] = counts.get(short, 0) + 1
    return {spec: (short if counts[short] == 1 else spec) for spec, short in shorts.items()}


def _shorten(text: str, labels: dict[str, str]) -> str:
    """Заменить полные подписи в тексте на короткие (длинные подписи первыми)."""
    for full in sorted(labels, key=len, reverse=True):
        text = text.replace(full, labels[full])
    return text


def tgexport_spec(path: str, sender: TgSender, senders: Sequence[TgSender]) -> str:
    """Источник `tgexport:путь#отправитель` для выбранного участника чата.

    По имени, если оно уникально в чате и не содержит `#` (так понятнее в таблице), иначе по
    идентификатору, который всегда однозначен.
    """
    same_name = [item for item in senders if item.name == sender.name]
    reference = sender.name if len(same_name) == 1 and "#" not in sender.name else sender.key
    return f"tgexport:{path}#{reference}"


@dataclass(frozen=True)
class CompareForm:
    """Поля формы «Сравнение» (источники уже приведены к виду схема:значение)."""

    unknown: str
    candidates: tuple[str, ...]
    impostors_dir: str = ""
    seed: int | None = DEFAULT_SEED  # None: в поле введено не число
    report_path: str = ""  # пусто: отчёт не сохранять
    limit: int | None = DEFAULT_LIMIT  # сообщений на источник tg:; None: введено не число
    refresh: bool = False  # для tg:: загрузить заново, не из кэша


@dataclass(frozen=True)
class FormError:
    """Ошибка формы: код для перевода в окне и параметры (строки)."""

    code: str
    params: dict[str, str] = field(default_factory=dict)


def check_compare_form(form: CompareForm) -> list[FormError]:
    """Ошибки в форме в виде кодов (пустой список, если всё в порядке)."""
    errors: list[FormError] = []
    if not form.unknown:
        errors.append(FormError("unknown_missing"))
    if not form.candidates:
        errors.append(FormError("no_candidates"))
    seen: set[str] = set()
    for candidate in form.candidates:
        if candidate in seen:
            errors.append(FormError("duplicate_candidate", {"spec": candidate}))
        seen.add(candidate)
        if form.unknown and candidate == form.unknown:
            errors.append(FormError("same_as_unknown", {"spec": candidate}))
    if form.seed is None or form.seed < 0:
        errors.append(FormError("bad_seed"))
    if form.limit is None or form.limit <= 0:
        errors.append(FormError("bad_limit"))
    if form.impostors_dir and not Path(form.impostors_dir).is_dir():
        errors.append(FormError("impostors_dir_missing", {"path": form.impostors_dir}))
    if form.report_path:
        try:
            report_format(Path(form.report_path))
        except ChatstyleError as exc:
            errors.append(FormError("report_format", {"message": str(exc)}))
    return errors


_FORM_ERROR_TEXTS = {
    "unknown_missing": "Укажите неизвестного автора.",
    "no_candidates": "Добавьте хотя бы одного кандидата.",
    "duplicate_candidate": "Кандидат указан дважды: {spec}",
    "same_as_unknown": "Неизвестный автор и кандидат совпадают: {spec}",
    "bad_seed": "Seed должен быть целым неотрицательным числом.",
    "bad_limit": "Число сообщений должно быть целым положительным числом.",
    "impostors_dir_missing": "Папка с чужими текстами не найдена: {path}",
    "report_format": "{message}",
}


def validate_compare_form(form: CompareForm) -> list[str]:
    """Сообщения об ошибках в форме (пустой список, если всё в порядке)."""
    return [
        _FORM_ERROR_TEXTS[error.code].format(**error.params) for error in check_compare_form(form)
    ]


@dataclass(frozen=True)
class CompareOutcome:
    result: ComparisonResult
    report_path: Path | None


def run_compare(form: CompareForm) -> CompareOutcome:
    """Полный цикл сравнения по форме: проверка, посторонние, расчёт, отчёт."""
    errors = validate_compare_form(form)
    if errors:
        raise ChatstyleError("\n".join(errors))
    impostors = load_impostor_directory(Path(form.impostors_dir)) if form.impostors_dir else None
    result = run_comparison(
        form.unknown,
        list(form.candidates),
        CollectOptions(limit=form.limit or DEFAULT_LIMIT, refresh=form.refresh),
        impostors=impostors,
        seed=form.seed if form.seed is not None else DEFAULT_SEED,
    )
    report_path = Path(form.report_path) if form.report_path else None
    if report_path is not None:
        write_report(report_path, result)
    return CompareOutcome(result=result, report_path=report_path)


def run_profile(source: str) -> AuthorProfile:
    """Профиль стиля автора по источнику из поля ввода."""
    spec = normalize_source(source)
    if not spec:
        raise ChatstyleError("Укажите источник автора.")
    return profile_author(spec, CollectOptions())


# --- представления для показа ---


@dataclass(frozen=True)
class ResultView:
    unknown_line: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    notes: tuple[str, ...]  # порядок, лучший по методам, причины недоступности
    warning: str | None  # предупреждение о малом объёме
    disclaimer: str


def build_result_view(result: ComparisonResult) -> ResultView:
    """Строки таблицы и пояснения; тексты те же, что в терминале и в отчёте."""
    labels = short_labels([result.unknown_label, *(c.label for c in result.candidates)])
    rows = tuple(
        (
            labels[candidate.label],
            str(candidate.words),
            str(candidate.messages),
            f"{candidate.similarity:.3f}",
            delta_text(candidate),
            final_score_text(candidate),
        )
        for candidate in result.candidates
    )
    notes = [ranking_text(result)]
    best = best_methods_text(result)
    if best:
        notes.append(best)
    notes += unavailable_notes(result)
    warning = low_volume_warning(result)
    return ResultView(
        unknown_line=(
            f"Неизвестный автор: {labels[result.unknown_label]} — "
            f"{result.unknown.words} слов, {result.unknown.messages} сообщений"
        ),
        columns=RESULT_COLUMNS,
        rows=rows,
        notes=tuple(_shorten(note, labels) for note in notes),
        warning=_shorten(warning, labels) if warning else None,
        disclaimer=DISCLAIMER,
    )


@dataclass(frozen=True)
class ProfileView:
    header: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, str], ...]
    word_lines: tuple[str, ...]


def build_profile_view(profile: AuthorProfile, top: int = 10) -> ProfileView:
    """Таблица стилевых признаков и списки частых слов."""
    return ProfileView(
        header=(
            f"Автор: {short_labels([profile.label])[profile.label]} — {profile.stats.words} слов, "
            f"{profile.stats.messages} сообщений"
        ),
        columns=PROFILE_COLUMNS,
        rows=tuple(
            (label, f"{profile.features[key]:.3f}") for key, label in FEATURE_LABELS.items()
        ),
        word_lines=tuple(word_list_lines(profile.features, top)),
    )


# --- фоновый запуск ---


class BackgroundJob(Generic[T]):
    """Выполняет функцию в фоновом потоке; результат забирается опросом из потока окна.

    Ядро отпускает GIL на время расчёта, поэтому окно остаётся отзывчивым. Исключения не
    теряются: `ChatstyleError` превращается в понятное сообщение, любое другое — в сообщение
    с типом ошибки.
    """

    def __init__(self, function: Callable[[], T]) -> None:
        self._function = function
        self._results: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)
        self.error_code: str | None = None  # код последней ошибки с кодом (CodedError)
        self.error_params: dict[str, str] = {}
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        try:
            self._results.put((True, self._function()))
        except ChatstyleError as exc:
            self.error_code = getattr(exc, "code", None)
            self.error_params = dict(getattr(exc, "params", {}))
            self._results.put((False, str(exc)))
        except Exception as exc:  # noqa: BLE001 - интерфейс не должен падать молча
            self._results.put((False, f"Непредвиденная ошибка ({type(exc).__name__}): {exc}"))

    def poll(self) -> tuple[bool, object] | None:
        """None, пока идёт расчёт; затем (True, результат) или (False, текст ошибки)."""
        try:
            return self._results.get_nowait()
        except queue.Empty:
            return None
