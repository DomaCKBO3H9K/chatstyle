"""Методы, которые вызывает веб-интерфейс через pywebview.

Окно (JS) обращается к ``window.pywebview.api.<метод>``. Здесь только сериализуемые
результаты: словари, списки, строки, числа, ``None``. Вычислительная логика живёт
в ``chatstyle.gui.model``, здесь она только оборачивается в нужные формы.

Готовых фраз здесь нет: пояснения, предупреждения и ошибки приходят в окно кодами с параметрами
(``{"code": ..., "params": {...}}``), а переводит их страница на выбранный язык. Исключение —
``core``: русский текст ошибки из ядра и сборщиков показывается как подробность.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
import webbrowser
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from chatstyle import __version__, chatstore, morph
from chatstyle.collectors.telegram import DEFAULT_LIMIT
from chatstyle.collectors.telegram_login import LoginState, TelegramLogin
from chatstyle.collectors.tg_export import list_tg_senders
from chatstyle.errors import ChatstyleError, CodedError
from chatstyle.features import (
    FEATURE_LABELS,
    FILLER_WORD_PREFIX,
    FUNCTION_WORD_PREFIX,
    NONSTANDARD_WORD_PREFIX,
    feature_section,
    top_words,
)
from chatstyle.gui.model import (
    BackgroundJob,
    CompareForm,
    CompareOutcome,
    build_result_view,
    check_compare_form,
    normalize_source,
    run_compare,
    run_profile,
    short_labels,
    tgexport_spec,
)
from chatstyle.gui.settings import load_settings, save_setting
from chatstyle.impostors import DEFAULT_SEED
from chatstyle.pipeline import (
    DISCLAIMER,
    ENSEMBLE_TEMPERATURE,
    METHOD_ENSEMBLE,
    METHOD_IMPOSTORS,
    MIN_WORDS,
    AuthorProfile,
    ComparisonResult,
    best_methods_text,
    charlm_text,
    delta_text,
    emoji_text,
    ensemble_text,
    final_score_text,
    lexical_hint,
    low_volume_sides,
    morph_text,
    rhythm_text,
    unavailable_facts,
    wordgram_text,
)

TELEGRAM_SITE = "https://my.telegram.org"  # единственный адрес, который окно открывает в браузере
MAX_TEXT = 4096  # длиннее любой путь или подпись из формы: такие данные отбрасываются
MAX_CANDIDATES = 50
MAX_PHONE, MAX_CODE, MAX_PASSWORD, MAX_API_ID, MAX_API_HASH = 64, 32, 256, 20, 64
REPORT_SUFFIXES = (".html", ".md")
WORD_LIST_PREFIXES = (
    ("fw", FUNCTION_WORD_PREFIX),
    ("fl", FILLER_WORD_PREFIX),
    ("ms", NONSTANDARD_WORD_PREFIX),
)
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


def _ensemble_shares(result: ComparisonResult) -> dict[str, float]:
    """Относительная близость кандидатов: softmax по смеси методов (сумма долей 1)."""
    scores = {
        row.label: row.ensemble_score for row in result.candidates if row.ensemble_score is not None
    }
    if not scores:
        return {}
    best = max(scores.values())
    weights = {
        label: math.exp((score - best) / ENSEMBLE_TEMPERATURE) for label, score in scores.items()
    }
    total = sum(weights.values())
    return {label: weight / total for label, weight in weights.items()}


def compare_view_dict(outcome: CompareOutcome) -> dict[str, Any]:
    """Результат сравнения для JS: числа, подписи и коды пояснений."""
    result = outcome.result
    view = build_result_view(result)
    names = short_labels([result.unknown_label, *(c.label for c in result.candidates)])
    metric = (
        result.ranked_by if result.ranked_by in (METHOD_IMPOSTORS, METHOD_ENSEMBLE) else "cosine"
    )
    shares = _ensemble_shares(result) if metric == METHOD_ENSEMBLE else {}

    candidates: list[dict[str, Any]] = []
    for index, candidate in enumerate(result.candidates):
        if metric == METHOD_ENSEMBLE:
            value = shares.get(candidate.label)
        elif metric == METHOD_IMPOSTORS:
            value = candidate.final_score
        else:
            value = candidate.similarity
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
                "ensemble": ensemble_text(candidate),
                "morph": morph_text(candidate),
                "charlm": charlm_text(candidate),
                "wordgrams": wordgram_text(candidate),
                "emoji": emoji_text(candidate),
                "rhythm": rhythm_text(candidate),
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
    hint = lexical_hint(result)
    if hint:
        notes.append(hint)

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
        "ensemble": bool(result.ensemble),
        "morph": bool(result.morph),
        "charlm": bool(result.charlm),
        "wordgrams": bool(result.wordgrams),
        "emoji": bool(result.emoji),
        "rhythm": bool(result.rhythm),
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
            {"key": key, "value": f"{profile.features[key]:.3f}", "section": feature_section(key)}
            for key in FEATURE_LABELS
        ],
        "morph": (
            None
            if profile.morph_features is None
            else [
                {"code": key[2:], "value": f"{value:.3f}"}
                for key, value in sorted(
                    profile.morph_features.items(), key=lambda item: (-item[1], item[0])
                )
                if value > 0
            ]
        ),
        "rhythm": (
            None
            if profile.rhythm_features is None
            else [
                {"key": key, "value": f"{value:.3f}"}
                for key, value in profile.rhythm_features.items()
            ]
        ),
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


def chat_view_dict(chat: chatstore.StoredChat) -> dict[str, Any]:
    """Загруженный чат для JS."""
    return {
        "id": chat.id,
        "name": chat.name,
        "messages": chat.messages,
        "updated": chat.updated,
        "senders": [
            {"key": sender.key, "name": sender.name, "messages": sender.messages}
            for sender in chat.senders
        ],
    }


def state_dict(state: LoginState) -> dict[str, Any]:
    """Состояние входа для окна."""
    return {
        "step": state.step,
        "name": state.name,
        "has_keys": state.has_keys,
        "remote_failed": state.remote_failed,
        "mode": state.mode,
        "legacy": state.legacy,
        "problem": state.problem,
        "two_factor": state.two_factor,
    }


def is_text(value: object, limit: int = MAX_TEXT) -> bool:
    """Строка допустимой длины без нулевых символов: всё, что приходит со страницы, проверяется."""
    return isinstance(value, str) and len(value) <= limit and "\x00" not in value


def norm_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def first_path(chosen: Any) -> str | None:
    """Путь из ответа диалога pywebview (кортеж путей, строка или пусто при отмене)."""
    if not chosen:
        return None
    path = chosen[0] if isinstance(chosen, (list, tuple)) else chosen
    return str(path) if path else None


class Api:
    """Мосты для JS-интерфейса: диалоги, запуск фоновых задач, опрос результатов."""

    def __init__(
        self,
        window_provider: Callable[[], Any | None] = lambda: None,
        telegram: TelegramLogin | None = None,
        allowed_paths: Iterable[str] = (),
        allowed_reports: Iterable[str] = (),
    ) -> None:
        # Источники и папки принимаются только те, что выбраны в диалогах этого окна: страница не
        # может заставить программу читать или перезаписывать произвольный файл.
        self._allowed_paths = {norm_path(path) for path in allowed_paths}
        self._allowed_reports = {norm_path(path) for path in allowed_reports}
        self._written_reports: set[str] = set()
        self._window_provider = window_provider
        self._telegram = telegram if telegram is not None else TelegramLogin()
        self._job: BackgroundJob[Any] | None = None
        self._job_error_code: str | None = None
        self._job_error_params: dict[str, str] = {}

    def get_settings(self) -> dict[str, str]:
        """Сохранённые язык и тема (только значения из белого списка)."""
        return load_settings()

    def set_setting(self, name: str, value: str) -> dict[str, Any]:
        try:
            return {"ok": True, "settings": save_setting(name, value)}
        except ChatstyleError as exc:
            return {"ok": False, "error": core_error(exc)}

    def _remember_path(self, path: str) -> None:
        self._allowed_paths.add(norm_path(path))

    def _remember_report(self, path: str) -> None:
        self._allowed_reports.add(norm_path(path))

    def _spec_allowed(self, spec: object) -> bool:
        if not is_text(spec):
            return False
        scheme, _, value = str(spec).partition(":")
        scheme = scheme.lower()
        if scheme == "file":
            return bool(value) and norm_path(value) in self._allowed_paths
        if scheme == "tgexport":
            path = value.rpartition("#")[0]
            return bool(path) and norm_path(path) in self._allowed_paths
        if scheme == "chat":
            chat_ref = value.rpartition("#")[0]
            try:
                return bool(chat_ref) and bool(chatstore.get_chat(chat_ref))
            except ChatstyleError:
                return False
        return scheme == "tg" and bool(value.strip())

    def morph_available(self) -> bool:
        """Установлено ли необязательное дополнение chatstyle[morph] (части речи)."""
        return morph.available()

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
        self._remember_path(path)
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
        self._remember_path(path)
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
        if not is_text(path) or not is_text(key):
            return {"error": error("bad_input")}
        if norm_path(path) not in self._allowed_paths:
            return {"error": error("path_not_allowed")}
        try:
            senders = list_tg_senders(Path(path))
        except ChatstyleError as exc:
            return {"error": core_error(exc)}
        sender = next((s for s in senders if s.key == key), None)
        if sender is None:
            return {"error": error("sender_missing")}
        spec = tgexport_spec(path, sender, senders)
        return {"spec": spec, "label": short_labels([spec])[spec]}

    def chats_list(self) -> list[dict[str, Any]]:
        """Загруженные чаты для вкладки «Чаты» и диалога выбора."""
        return [chat_view_dict(chat) for chat in chatstore.list_chats()]

    def chats_add(self) -> dict[str, Any] | None:
        """Диалог выбора экспорта и загрузка чата в список; None при отмене."""
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
            return {"chat": chat_view_dict(chatstore.import_chat(Path(path)))}
        except ChatstyleError as exc:
            return {"error": core_error(exc)}

    def chats_remove(self, chat_id: str) -> dict[str, Any]:
        if not is_text(chat_id):
            return {"ok": False, "error": error("bad_input")}
        try:
            chatstore.remove_chat(chat_id)
        except ChatstyleError:
            return {"ok": False, "error": error("chat_missing")}
        return {"ok": True}

    def chat_source(self, chat_id: str, key: str) -> dict[str, Any]:
        """Источник `chat:id#участник` для участника загруженного чата."""
        if not is_text(chat_id) or not is_text(key):
            return {"error": error("bad_input")}
        try:
            chat = chatstore.get_chat(chat_id)
        except ChatstyleError:
            return {"error": error("chat_missing")}
        sender = next((s for s in chat.senders if s.key == key), None)
        if sender is None:
            return {"error": error("sender_missing")}
        same_name = [item for item in chat.senders if item.name == sender.name]
        reference = sender.name if len(same_name) == 1 and "#" not in sender.name else sender.key
        return {"spec": f"chat:{chat.id}#{reference}", "label": f"{chat.name} › {sender.name}"}

    def pick_folder(self) -> str | None:
        import webview

        folder = first_path(self._dialog(webview.FileDialog.FOLDER))
        if folder is not None:
            self._remember_path(folder)
        return folder

    def pick_report_path(self) -> str | None:
        import webview

        path = first_path(
            self._dialog(
                webview.FileDialog.SAVE,
                save_filename="report.html",
                file_types=("HTML files (*.html)", "Markdown files (*.md)", "All files (*.*)"),
            )
        )
        if path is not None:
            self._remember_report(path)
        return path

    def start_compare(self, form: dict[str, Any]) -> dict[str, Any]:
        if self._job is not None:
            return {"ok": False, "errors": [error("busy")]}
        refused = self._refuse_form(form)
        if refused:
            return {"ok": False, "errors": refused}

        seed_text = str(form.get("seed", "") or "").strip()
        seed: int | None
        if seed_text == "":
            seed = DEFAULT_SEED
        else:
            try:
                seed = int(seed_text)
            except ValueError:
                seed = None

        limit_text = str(form.get("limit", "") or "").strip()
        limit: int | None
        if limit_text == "":
            limit = DEFAULT_LIMIT
        else:
            try:
                limit = int(limit_text)
            except ValueError:
                limit = None

        compare_form = CompareForm(
            unknown=form.get("unknown", ""),
            candidates=tuple(form.get("candidates", []) or []),
            impostors_dir=form.get("impostors_dir", ""),
            seed=seed,
            report_path=form.get("report_path", ""),
            limit=limit,
            refresh=bool(form.get("refresh", False)),
            morph=bool(form.get("morph", False)),
            charlm=bool(form.get("charlm", False)),
            wordgrams=bool(form.get("wordgrams", False)),
            emoji=bool(form.get("emoji", False)),
            lexical=bool(form.get("lexical", False)),
            rhythm=bool(form.get("rhythm", False)),
        )
        problems = check_compare_form(compare_form)
        if problems:
            return {"ok": False, "errors": [error(p.code, **p.params) for p in problems]}

        self._telegram.touch()
        self._job = BackgroundJob(lambda: run_compare(compare_form))
        self._job.start()
        return {"ok": True}

    def start_profile(self, source: str, morph: bool = False) -> dict[str, Any]:
        if self._job is not None:
            return {"ok": False, "errors": [error("busy")]}
        if not is_text(source) or not isinstance(morph, bool):
            return {"ok": False, "errors": [error("bad_input")]}
        if not source.strip():
            return {"ok": False, "errors": [error("source_missing")]}
        if not self._spec_allowed(normalize_source(source)):
            return {"ok": False, "errors": [error("path_not_allowed")]}
        self._job = BackgroundJob(lambda: run_profile(source, morph))
        self._job.start()
        return {"ok": True}

    def poll(self) -> dict[str, Any]:
        if self._job is None:
            return {"state": "idle"}
        polled = self._job.poll()
        if polled is None:
            return {"state": "running"}
        self._job_error_code = getattr(self._job, "error_code", None)
        self._job_error_params = getattr(self._job, "error_params", {})
        self._job = None
        ok, payload = polled
        if not ok:
            code = self._job_error_code
            known = error(code, **self._job_error_params) if code else core_error(str(payload))
            return {"state": "error", "error": known}
        if isinstance(payload, CompareOutcome):
            if payload.report_path is not None:
                self._written_reports.add(norm_path(str(payload.report_path)))
            return {"state": "done", "kind": "compare", "view": compare_view_dict(payload)}
        return {"state": "done", "kind": "profile", "view": profile_view_dict(payload)}

    # --- вход в Telegram: шаги, секреты (код, пароль) нигде не сохраняются ---

    def telegram_status(self) -> dict[str, Any]:
        """Без сети: шаг входа, имя аккаунта, заданы ли ключи."""
        return state_dict(self._telegram.status())

    @staticmethod
    def _bad_input() -> dict[str, Any]:
        return {"ok": False, "error": error("bad_input")}

    def telegram_setup(
        self, mode: str, password: str, api_id: str, api_hash: str
    ) -> dict[str, Any]:
        """Создать хранилище выбранного режима (password, dpapi, memory) и сохранить ключи API."""
        texts = (
            is_text(mode, 16),
            is_text(password, MAX_PASSWORD),
            is_text(api_id, MAX_API_ID),
            is_text(api_hash, MAX_API_HASH),
        )
        if not all(texts):
            return self._bad_input()
        return self._telegram_step(
            lambda: self._telegram.setup(mode, password or None, api_id, api_hash)
        )

    def telegram_unlock(self, password: str) -> dict[str, Any]:
        if not is_text(password, MAX_PASSWORD):
            return self._bad_input()
        return self._telegram_step(lambda: self._telegram.unlock(password or None))

    def telegram_lock(self) -> dict[str, Any]:
        return self._telegram_step(self._telegram.lock)

    def telegram_forget(self) -> dict[str, Any]:
        """Удалить хранилище, сессию (и в Telegram, если можно) и старые открытые файлы."""
        return self._telegram_step(self._telegram.forget)

    def telegram_remove_legacy(self) -> dict[str, Any]:
        return self._telegram_step(self._telegram.remove_legacy_files)

    def shutdown(self) -> None:
        """Вызывается при закрытии окна."""
        self._telegram.shutdown()

    def telegram_save_keys(self, api_id: str, api_hash: str) -> dict[str, Any]:
        if not (is_text(api_id, MAX_API_ID) and is_text(api_hash, MAX_API_HASH)):
            return self._bad_input()

        def action() -> LoginState:
            self._telegram.save_keys(api_id, api_hash)
            return self._telegram.status()

        return self._telegram_step(action)

    def telegram_begin(self, phone: str) -> dict[str, Any]:
        if not is_text(phone, MAX_PHONE):
            return self._bad_input()
        return self._telegram_step(lambda: self._telegram.begin(phone))

    def telegram_code(self, code: str) -> dict[str, Any]:
        if not is_text(code, MAX_CODE):
            return self._bad_input()
        return self._telegram_step(lambda: self._telegram.submit_code(code))

    def telegram_password(self, password: str) -> dict[str, Any]:
        if not is_text(password, MAX_PASSWORD):
            return self._bad_input()
        return self._telegram_step(lambda: self._telegram.submit_password(password))

    def telegram_cancel(self) -> dict[str, Any]:
        return self._telegram_step(self._telegram.cancel)

    def telegram_logout(self) -> dict[str, Any]:
        return self._telegram_step(self._telegram.logout)

    def telegram_open_site(self) -> None:
        webbrowser.open(TELEGRAM_SITE)

    def _telegram_step(self, action: Callable[[], LoginState]) -> dict[str, Any]:
        self._telegram.touch()
        try:
            return {"ok": True, "state": state_dict(action())}
        except CodedError as exc:
            return {"ok": False, "error": error(exc.code, **exc.params)}
        except ChatstyleError as exc:
            return {"ok": False, "error": core_error(exc)}

    def _refuse_form(self, form: object) -> list[dict[str, Any]]:
        """Отказать, если форма не того вида или ссылается на путь не из диалогов этого окна."""
        if not isinstance(form, dict):
            return [error("bad_input")]
        candidates = form.get("candidates", [])
        texts = (form.get(name, "") for name in ("unknown", "impostors_dir", "report_path", "seed"))
        well_formed = (
            isinstance(candidates, list)
            and len(candidates) <= MAX_CANDIDATES
            and all(is_text(item) for item in candidates)
            and all(is_text(value) for value in texts)
            and is_text(form.get("limit", ""), 32)
            and isinstance(form.get("refresh", False), bool)
            and isinstance(form.get("morph", False), bool)
            and isinstance(form.get("charlm", False), bool)
            and isinstance(form.get("wordgrams", False), bool)
            and isinstance(form.get("emoji", False), bool)
            and isinstance(form.get("lexical", False), bool)
            and isinstance(form.get("rhythm", False), bool)
        )
        if not well_formed:
            return [error("bad_input")]
        unknown = form.get("unknown", "")
        specs = [unknown, *candidates] if unknown else list(candidates)
        impostors = form.get("impostors_dir", "")
        report = form.get("report_path", "")
        if (
            any(not self._spec_allowed(spec) for spec in specs)
            or (impostors and norm_path(impostors) not in self._allowed_paths)
            or (report and norm_path(report) not in self._allowed_reports)
        ):
            return [error("path_not_allowed")]
        return []

    def open_report(self, path: str) -> dict[str, Any] | None:
        if not is_text(path):
            return {"error": error("bad_input")}
        file_path = Path(path)
        if norm_path(path) not in self._written_reports or file_path.suffix.lower() not in (
            REPORT_SUFFIXES
        ):
            return {"error": error("path_not_allowed")}
        if not file_path.is_file():
            return {"error": error("report_missing")}
        if sys.platform.startswith("win"):
            os.startfile(str(file_path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(file_path)])
        else:
            subprocess.Popen(["xdg-open", str(file_path)])
        return None
