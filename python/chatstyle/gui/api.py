"""Методы, которые вызывает веб-интерфейс через pywebview.

Окно (JS) обращается к ``window.pywebview.api.<метод>``. Здесь только сериализуемые
результаты: словари, списки, строки, числа, ``None``. Вычислительная логика живёт
в ``chatstyle.gui.model``, здесь она только оборачивается в нужные формы.

Готовых фраз здесь нет: пояснения, предупреждения и ошибки приходят в окно кодами с параметрами
(``{"code": ..., "params": {...}}``), а переводит их страница на выбранный язык. Исключение —
``core``: русский текст ошибки из ядра и сборщиков показывается как подробность.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from chatstyle import __version__
from chatstyle.collectors.tg_export import list_tg_senders
from chatstyle.errors import ChatstyleError
from chatstyle.features import (
    FEATURE_LABELS,
    FILLER_WORD_PREFIX,
    FUNCTION_WORD_PREFIX,
    top_words,
)
from chatstyle.gui.model import (
    BackgroundJob,
    CompareForm,
    CompareOutcome,
    build_result_view,
    check_compare_form,
    run_compare,
    run_profile,
    short_labels,
    tgexport_spec,
)
from chatstyle.impostors import DEFAULT_SEED
from chatstyle.pipeline import (
    DISCLAIMER,
    METHOD_IMPOSTORS,
    MIN_WORDS,
    AuthorProfile,
    best_methods_text,
    delta_text,
    final_score_text,
    low_volume_sides,
    unavailable_facts,
)

WORD_LIST_PREFIXES = (("fw", FUNCTION_WORD_PREFIX), ("fl", FILLER_WORD_PREFIX))
WORD_LIST_LIMIT = 10
WHY_LIMIT = 6


def error(code: str, **params: object) -> dict[str, Any]:
    """Ошибка для окна: код и строковые параметры."""
    return {"code": code, "params": {key: str(value) for key, value in params.items()}}


def core_error(exc: Exception | str) -> dict[str, Any]:
    """Ошибка ядра или сборщика: её русский текст показывается подробностью."""
    return error("core", message=str(exc))


def _shorten_all(labels: list[str], names: dict[str, str]) -> list[str]:
    return [names.get(label, label) for label in labels]


def compare_view_dict(outcome: CompareOutcome) -> dict[str, Any]:
    """Результат сравнения для JS: числа, подписи и коды пояснений."""
    result = outcome.result
    view = build_result_view(result)
    names = short_labels([result.unknown_label, *(c.label for c in result.candidates)])
    metric = METHOD_IMPOSTORS if result.ranked_by == METHOD_IMPOSTORS else "cosine"

    candidates: list[dict[str, Any]] = []
    for index, candidate in enumerate(result.candidates):
        value = candidate.final_score if metric == METHOD_IMPOSTORS else candidate.similarity
        value = max(0.0, min(1.0, 0.0 if value is None else value))
        why: list[str] = []
        if index == 0:
            for feature in candidate.top_features[:WHY_LIMIT]:
                if feature.feature not in why:
                    why.append(feature.feature)
        candidates.append(
            {
                "label": view.rows[index][0],
                "words": candidate.words,
                "messages": candidate.messages,
                "value": value,
                "value_text": f"{value:.2f}",
                "cosine": f"{candidate.similarity:.2f}",
                "delta": delta_text(candidate),
                "final": final_score_text(candidate),
                "why": why,
            }
        )

    notes: list[dict[str, Any]] = [{"code": "ranking", "method": metric}]
    if best_methods_text(result):
        notes.append(
            {
                "code": "best_methods",
                "agree": bool(result.methods_agree()),
                "parts": [
                    {"method": method, "labels": _shorten_all(list(labels), names)}
                    for method, labels in result.best_by_method().items()
                ],
            }
        )
    for fact in unavailable_facts(result):
        notes.append({**fact, "labels": _shorten_all(list(fact["labels"]), names)})  # type: ignore[call-overload]

    sides = low_volume_sides(result)
    warning = (
        {
            "min": MIN_WORDS,
            "sides": [
                {"who": None if label is None else names.get(label, label), "words": words}
                for label, words in sides
            ],
        }
        if sides
        else None
    )
    return {
        "metric": metric,
        "unknown": {
            "label": names[result.unknown_label],
            "words": result.unknown.words,
            "messages": result.unknown.messages,
        },
        "candidates": candidates,
        "notes": notes,
        "warning": warning,
        "report_path": str(outcome.report_path) if outcome.report_path else None,
    }


def profile_view_dict(profile: AuthorProfile) -> dict[str, Any]:
    """Профиль стиля для JS: ключи признаков и списки слов, подписи переводит окно."""
    return {
        "label": short_labels([profile.label])[profile.label],
        "words": profile.stats.words,
        "messages": profile.stats.messages,
        "features": [
            {"key": key, "value": f"{profile.features[key]:.3f}"} for key in FEATURE_LABELS
        ],
        "word_lists": [
            {
                "kind": kind,
                "items": [
                    {"word": word, "value": f"{value:.3f}"}
                    for word, value in top_words(profile.features, prefix, WORD_LIST_LIMIT)
                ],
            }
            for kind, prefix in WORD_LIST_PREFIXES
        ],
    }


def first_path(chosen: Any) -> str | None:
    """Путь из ответа диалога pywebview (кортеж путей, строка или пусто при отмене)."""
    if not chosen:
        return None
    path = chosen[0] if isinstance(chosen, (list, tuple)) else chosen
    return str(path) if path else None


class Api:
    """Мосты для JS-интерфейса: диалоги, запуск фоновых задач, опрос результатов."""

    def __init__(self, window_provider: Callable[[], Any | None] = lambda: None) -> None:
        self._window_provider = window_provider
        self._job: BackgroundJob[Any] | None = None

    def init(self) -> dict[str, str]:
        return {"disclaimer": DISCLAIMER, "version": __version__}

    def _dialog(self, kind: Any, **kwargs: Any) -> Any:
        window = self._window_provider()
        if window is None:
            raise ChatstyleError("Окно ещё не готово.")
        return window.create_file_dialog(kind, **kwargs)

    def pick_file(self) -> dict[str, str] | None:
        import webview

        path = first_path(
            self._dialog(
                webview.FileDialog.OPEN,
                file_types=("Text files (*.txt)", "All files (*.*)"),
            )
        )
        if path is None:
            return None
        return {"spec": f"file:{path}", "label": Path(path).name}

    def pick_tg_export(self) -> dict[str, Any] | None:
        import webview

        path = first_path(
            self._dialog(
                webview.FileDialog.OPEN,
                file_types=("JSON files (*.json)", "All files (*.*)"),
            )
        )
        if path is None:
            return None
        try:
            senders = list_tg_senders(Path(path))
        except ChatstyleError as exc:
            return {"error": core_error(exc)}
        return {
            "path": path,
            "senders": [
                {"key": sender.key, "name": sender.name, "messages": sender.messages}
                for sender in senders
            ],
        }

    def tg_source(self, path: str, key: str) -> dict[str, Any]:
        try:
            senders = list_tg_senders(Path(path))
        except ChatstyleError as exc:
            return {"error": core_error(exc)}
        sender = next((s for s in senders if s.key == key), None)
        if sender is None:
            return {"error": error("sender_missing")}
        spec = tgexport_spec(path, sender, senders)
        return {"spec": spec, "label": short_labels([spec])[spec]}

    def pick_folder(self) -> str | None:
        import webview

        return first_path(self._dialog(webview.FileDialog.FOLDER))

    def pick_report_path(self) -> str | None:
        import webview

        return first_path(
            self._dialog(
                webview.FileDialog.SAVE,
                save_filename="report.html",
                file_types=("HTML files (*.html)", "Markdown files (*.md)", "All files (*.*)"),
            )
        )

    def start_compare(self, form: dict[str, Any]) -> dict[str, Any]:
        if self._job is not None:
            return {"ok": False, "errors": [error("busy")]}

        seed_text = str(form.get("seed", "") or "").strip()
        seed: int | None
        if seed_text == "":
            seed = DEFAULT_SEED
        else:
            try:
                seed = int(seed_text)
            except ValueError:
                seed = None

        compare_form = CompareForm(
            unknown=form.get("unknown", ""),
            candidates=tuple(form.get("candidates", []) or []),
            impostors_dir=form.get("impostors_dir", ""),
            seed=seed,
            report_path=form.get("report_path", ""),
        )
        problems = check_compare_form(compare_form)
        if problems:
            return {"ok": False, "errors": [error(p.code, **p.params) for p in problems]}

        self._job = BackgroundJob(lambda: run_compare(compare_form))
        self._job.start()
        return {"ok": True}

    def start_profile(self, source: str) -> dict[str, Any]:
        if self._job is not None:
            return {"ok": False, "errors": [error("busy")]}
        if not source or not source.strip():
            return {"ok": False, "errors": [error("source_missing")]}
        self._job = BackgroundJob(lambda: run_profile(source))
        self._job.start()
        return {"ok": True}

    def poll(self) -> dict[str, Any]:
        if self._job is None:
            return {"state": "idle"}
        polled = self._job.poll()
        if polled is None:
            return {"state": "running"}
        self._job = None
        ok, payload = polled
        if not ok:
            return {"state": "error", "error": core_error(str(payload))}
        if isinstance(payload, CompareOutcome):
            return {"state": "done", "kind": "compare", "view": compare_view_dict(payload)}
        return {"state": "done", "kind": "profile", "view": profile_view_dict(payload)}

    def open_report(self, path: str) -> dict[str, Any] | None:
        file_path = Path(path)
        if not file_path.is_file():
            return {"error": error("report_missing")}
        if sys.platform.startswith("win"):
            os.startfile(str(file_path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(file_path)])
        else:
            subprocess.Popen(["xdg-open", str(file_path)])
        return None
