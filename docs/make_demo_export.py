"""Собирает из вымышленных переписок docs/demo/ экспорты в формате Telegram Desktop (result.json).

    python docs/make_demo_export.py ПАПКА

Для каждого языка и каждой переписки создаётся файл ПАПКА/<язык>/<trip|work>.json: его можно
загрузить во вкладку «Чаты» или сравнить через `tgexport:`. Люди и время сообщений вымышлены.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

DEMO = Path(__file__).resolve().parent / "demo"
LANGUAGES = ("ru", "en", "es", "fr", "zh", "ar")
CHATS = {"trip": (101, datetime(2024, 6, 7, 18, 0)), "work": (102, datetime(2024, 6, 10, 10, 0))}
TITLES = {
    "ru": {"trip": "Поездка на озеро", "work": "Рабочий проект"},
    "en": {"trip": "Lake trip", "work": "Work project"},
    "es": {"trip": "Viaje al lago", "work": "Proyecto de trabajo"},
    "fr": {"trip": "Voyage au lac", "work": "Projet de travail"},
    "zh": {"trip": "湖边旅行", "work": "工作项目"},
    "ar": {"trip": "رحلة البحيرة", "work": "مشروع العمل"},
}


def titles(lang: str) -> dict[str, str]:
    return TITLES[lang]


def people_of(lang: str) -> list[str]:
    """Имена в порядке первых реплик переписки «поездка»: Аня, Борис, Вера, Глеб."""
    names: list[str] = []
    for line in (DEMO / f"trip.{lang}.txt").read_text(encoding="utf-8").splitlines():
        name = line.split("\t", 1)[0]
        if name not in names:
            names.append(name)
    return names


def build_export(chat: str, lang: str) -> dict:
    chat_id, start = CHATS[chat]
    order = people_of(lang)
    clock = start
    records = []
    lines = [
        line
        for line in (DEMO / f"{chat}.{lang}.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for number, line in enumerate(lines, start=1):
        name, text = line.split("\t", 1)
        clock += timedelta(minutes=1 + (number * 7) % 4, seconds=(number * 13) % 50)
        records.append(
            {
                "id": number,
                "type": "message",
                "date": clock.strftime("%Y-%m-%dT%H:%M:%S"),
                "from": name,
                "from_id": f"user{order.index(name) + 1}",
                "text": text,
            }
        )
    return {"name": titles(lang)[chat], "type": "private_group", "id": chat_id, "messages": records}


def write_all(target: Path, languages: tuple[str, ...] = LANGUAGES) -> list[Path]:
    written = []
    for lang in languages:
        folder = target / lang
        folder.mkdir(parents=True, exist_ok=True)
        for chat in CHATS:
            path = folder / f"{chat}.json"
            path.write_text(
                json.dumps(build_export(chat, lang), ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
            written.append(path)
    return written


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit("Использование: python docs/make_demo_export.py ПАПКА")
    for path in write_all(Path(argv[1])):
        print(path)


if __name__ == "__main__":
    main(sys.argv)
