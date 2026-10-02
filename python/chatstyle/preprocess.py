"""Предобработка сообщений для ядра chatstyle."""

import re
import unicodedata
from collections.abc import Iterable, Sequence

from chatstyle.timeline import Messages

URL_TOKEN: str = "<URL>"
MENTION_TOKEN: str = "<MENTION>"

SERVICE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\[(?:фото|видео|стикер|голосовое сообщение|файл|gif"
        r"|photo|video|sticker|voice message|file)\]",
        re.IGNORECASE,
    ),
    re.compile(r"<media omitted>", re.IGNORECASE),
)

_URL_RE: re.Pattern[str] = re.compile(r"(?:https?://|www\.)[^\s<>]+")
_MENTION_RE: re.Pattern[str] = re.compile(r"(?<![\w@])@[A-Za-z][A-Za-z0-9_]{2,31}(?![\w@])")
_SURROGATE_RE: re.Pattern[str] = re.compile(r"[\ud800-\udfff]")
_INVISIBLE_RE: re.Pattern[str] = re.compile(r"[\u200b\ufeff\u2060]")
_SPACES_RE: re.Pattern[str] = re.compile(r"\s+")
_URL_TRAILING_PUNCT: str = ".,;:!?)]}»\"'…"


def _replace_url(match: re.Match[str]) -> str:
    url = match.group(0)
    stripped_url = url.rstrip(_URL_TRAILING_PUNCT)
    tail = url[len(stripped_url) :]
    return URL_TOKEN + tail


def clean_message(text: str) -> str:
    """Очищает одно сообщение; пустая строка означает, что его нужно отбросить."""
    text = _SURROGATE_RE.sub("\ufffd", text)
    text = unicodedata.normalize("NFC", text)
    text = _INVISIBLE_RE.sub("", text)
    text = _URL_RE.sub(_replace_url, text)
    text = _MENTION_RE.sub(MENTION_TOKEN, text)
    text = _SPACES_RE.sub(" ", text).strip()

    if not text.replace(URL_TOKEN, "").replace(MENTION_TOKEN, "").replace(" ", ""):
        return ""

    for pattern in SERVICE_PATTERNS:
        if pattern.fullmatch(text):
            return ""

    return text


def preprocess(messages: Iterable[str]) -> list[str]:
    """Применяет clean_message ко всем сообщениям и возвращает непустые результаты."""
    return [cleaned for m in messages if (cleaned := clean_message(m))]


def preprocess_timed(messages: Sequence[str]) -> Messages:
    """То же, что `preprocess`, но сохраняет моменты отправки (`times`) у оставшихся сообщений."""
    times = getattr(messages, "times", None)
    kept: list[str] = []
    kept_times: list[int | None] = []
    for index, message in enumerate(messages):
        cleaned = clean_message(message)
        if cleaned:
            kept.append(cleaned)
            kept_times.append(times[index] if times is not None else None)
    return Messages(kept, kept_times if times is not None else None)
