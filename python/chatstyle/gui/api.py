"""Методы, которые вызывает веб-интерфейс через pywebview.

Окно (JS) обращается к ``window.pywebview.api.<метод>``. Здесь только сериализуемые
результаты: словари, списки, строки, числа, ``None``. Вычислительная логика живёт
в ``chatstyle.gui.model``, здесь она только оборачивается в нужные формы.
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
from chatstyle.gui.model import (
    BackgroundJob,
    CompareForm,
    CompareOutcome,
    build_profile_view,
    build_result_view,
    run_compare,
    run_profile,
    short_labels,
    tgexport_spec,
    validate_compare_form,
)
from chatstyle.impostors import DEFAULT_SEED
from chatstyle.pipeline import (
    DISCLAIMER,
    METHOD_IMPOSTORS,
    delta_text,
    final_score_text,
)


def compare_view_dict(outcome: CompareOutcome) -> dict[str, Any]:
    """Сериализованное представление результата сравнения для JS."""
    result = outcome.result
    view = build_result_view(result)

    metric = METHOD_IMPOSTORS if result.ranked_by == METHOD_IMPOSTORS else "cosine"
    if metric == METHOD_IMPOSTORS:
        metric_name = "Итоговая оценка (General Impostors)"
        summary = (
            "Доля повторов, в которых кандидат оказался ближе к тексту, чем посторонние авторы. "
            "Это не вероятность авторства."
        )
    else:
        metric_name = "Косинусное сходство"
        summary = (
            "Итоговая оценка недоступна, кандидаты упорядочены по косинусному сходству. "
            "Это не вероятность авторства."
        )

    candidates: list[dict[str, Any]] = []
    for i, candidate in enumerate(result.candidates):
        label = view.rows[i][0]
        if metric == METHOD_IMPOSTORS:
            value = candidate.final_score
        else:
            value = candidate.similarity
        if value is None:
            value = 0.0
        value = max(0.0, min(1.0, value))
        value_text = f"{value:.2f}"
        cosine = f"{candidate.similarity:.2f}"
        delta = delta_text(candidate)
        final = final_score_text(candidate)

        why: list[str] = []
        if i == 0:
            for feature in candidate.top_features[:6]:
                text = feature.feature
                if text not in why:
                    why.append(text)

        candidates.append(
            {
                "label": label,
                "words": candidate.words,
                "messages": candidate.messages,
                "value": value,
                "value_text": value_text,
                "cosine": cosine,
                "delta": delta,
                "final": final,
                "why": why,
            }
        )

    return {
        "metric": metric,
        "metric_name": metric_name,
        "summary": summary,
        "candidates": candidates,
        "notes": list(view.notes),
        "warning": view.warning,
        "report_path": str(outcome.report_path) if outcome.report_path else None,
    }


def profile_view_dict(profile: Any) -> dict[str, Any]:
    """Сериализованное представление профиля стиля для JS."""
    view = build_profile_view(profile)
    features = [{"name": row[0], "value": row[1]} for row in view.rows]
    return {
        "header": view.header,
        "features": features,
        "word_lines": list(view.word_lines),
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
            return {"error": str(exc)}
        return {
            "path": path,
            "senders": [
                {"key": sender.key, "name": sender.name, "messages": sender.messages}
                for sender in senders
            ],
        }

    def tg_source(self, path: str, key: str) -> dict[str, str]:
        senders = list_tg_senders(Path(path))
        sender = next((s for s in senders if s.key == key), None)
        if sender is None:
            raise ChatstyleError("Отправитель не найден в экспорте.")
        spec = tgexport_spec(path, sender, senders)
        label = short_labels([spec])[spec]
        return {"spec": spec, "label": label}

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
            return {"ok": False, "errors": ["Расчёт уже идёт. Дождитесь результата."]}

        unknown = form.get("unknown", "")
        candidates = list(form.get("candidates", []) or [])
        impostors_dir = form.get("impostors_dir", "")
        seed_str = form.get("seed", "")
        report_path = form.get("report_path", "")

        if seed_str == "":
            seed = DEFAULT_SEED
        else:
            try:
                seed = int(seed_str)
            except ValueError:
                seed = None

        compare_form = CompareForm(
            unknown=unknown,
            candidates=tuple(candidates),
            impostors_dir=impostors_dir,
            seed=seed,
            report_path=report_path,
        )

        errors = validate_compare_form(compare_form)
        if errors:
            return {"ok": False, "errors": errors}

        self._job = BackgroundJob(lambda: run_compare(compare_form))
        self._job.start()
        return {"ok": True}

    def start_profile(self, source: str) -> dict[str, Any]:
        if self._job is not None:
            return {"ok": False, "errors": ["Расчёт уже идёт. Дождитесь результата."]}
        if not source or not source.strip():
            return {"ok": False, "errors": ["Укажите источник автора."]}
        self._job = BackgroundJob(lambda: run_profile(source))
        self._job.start()
        return {"ok": True}

    def poll(self) -> dict[str, Any]:
        if self._job is None:
            return {"state": "idle"}
        result = self._job.poll()
        if result is None:
            return {"state": "running"}
        ok, payload = result
        self._job = None
        if ok:
            if isinstance(payload, CompareOutcome):
                return {"state": "done", "kind": "compare", "view": compare_view_dict(payload)}
            return {"state": "done", "kind": "profile", "view": profile_view_dict(payload)}
        return {"state": "error", "message": payload}

    def open_report(self, path: str) -> None:
        file_path = Path(path)
        if not file_path.is_file():
            raise ChatstyleError("Отчёт не найден.")
        if sys.platform.startswith("win"):
            os.startfile(str(file_path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(file_path)])
        else:
            subprocess.Popen(["xdg-open", str(file_path)])
