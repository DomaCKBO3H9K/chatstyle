"""Датасет из JSON-экспорта группового чата Telegram (с согласия участников!).

    python -m experiments.prepare_tgexport result.json DIR --min-messages 300

Для каждого участника, у которого не меньше --min-messages текстовых сообщений, создаётся файл
a001.txt, a002.txt, ... (по убыванию числа сообщений). Имена и id участников НЕ записываются
ни в файлы, ни в вывод: остаётся только анонимный номер. Папку с результатом держите вне git
(`data/` уже в .gitignore) и удалите, когда она больше не нужна.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from chatstyle.collectors.tg_export import read_tg_export_by_sender
from chatstyle.errors import ChatstyleError


def prepare(export: Path, directory: Path, min_messages: int) -> list[int]:
    """Записать файлы участников; вернуть числа сообщений по анонимным номерам."""
    senders = read_tg_export_by_sender(export)
    chosen = sorted(
        (messages for messages in senders.values() if len(messages) >= min_messages),
        key=len,
        reverse=True,
    )
    if not chosen:
        raise ChatstyleError(
            f"Нет участников с {min_messages} и более текстовыми сообщениями "
            f"(всего участников: {len(senders)})."
        )
    directory.mkdir(parents=True, exist_ok=True)
    for index, messages in enumerate(chosen, start=1):
        # перевод строки внутри сообщения заменяется пробелом: одно сообщение — одна строка
        lines = [" ".join(message.split()) for message in messages]
        (directory / f"a{index:03d}.txt").write_text("\n".join(lines), encoding="utf-8")
    return [len(messages) for messages in chosen]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Датасет из экспорта группового чата Telegram.")
    parser.add_argument("export", type=Path, help="result.json одного группового чата")
    parser.add_argument("directory", type=Path, help="куда записать файлы a001.txt, ...")
    parser.add_argument("--min-messages", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        counts = prepare(args.export, args.directory, args.min_messages)
    except ChatstyleError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    for index, count in enumerate(counts, start=1):
        print(f"a{index:03d}: {count} сообщений")
    print(f"Готово: {len(counts)} авторов в {args.directory}. Не добавляйте папку в git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
