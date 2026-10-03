"""Проверка порядка кандидатов на загруженных чатах (без ручной разметки).

    python -m experiments.chats_eval [--chats-dir ПАПКА] [--min-words 2500] [--lexical]

Один и тот же идентификатор участника (`from_id`) в разных чатах — один человек. Из этого
строятся задачи с известным ответом:

* «через контексты»: тексты человека из одного чата против остальных людей, чьи тексты
  берутся из ДРУГИХ чатов (так тема и собеседники не совпадают);
* «по времени»: последние сообщения человека в самом большом чате против остальных его
  сообщений, соперники — все остальные люди.

У всех кандидатов одинаковый объём текста. Метрики: доля задач, где настоящий человек на первом
месте (top1), средний обратный ранг (MRR) и доля при случайном угадывании. В вывод попадают
только числа: ни имён, ни текстов. Данные не покидают компьютер.

Задачи зависят друг от друга (один человек — несколько задач), выбор метода по этим же данным
оптимистичен: цифры нельзя считать оценкой точности на других людях.
"""

import argparse
import getpass
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from chatstyle import chatstore
from chatstyle.ensemble import DEFAULT_CAP_WORDS, cap_messages
from chatstyle.errors import ChatstyleError
from chatstyle.pipeline import compare_messages, count_words
from chatstyle.preprocess import preprocess_timed
from chatstyle.securestore import default_vault, set_password_prompt, unlock_interactively
from chatstyle.timeline import Messages

MIN_UNKNOWN_WORDS = 600  # меньше текста в контексте — задача не строится


@dataclass(frozen=True)
class Task:
    kind: str  # "cross" или "time"
    person: str
    unknown: Messages
    candidates: dict[str, Messages]


@dataclass(frozen=True)
class Summary:
    tasks: int
    top1: float
    mrr: float
    chance: float  # доля при случайном угадывании


def load_people(chats_dir: Path | None) -> dict[str, dict[str, Messages]]:
    """чат -> идентификатор участника -> предобработанные сообщения со временем.

    Без `chats_dir` читается рабочее зашифрованное хранилище (нужно открыть общее хранилище
    секретов), с `chats_dir` — открытые файлы чатов из этой папки (копия для проверок).
    """
    data: dict[str, dict[str, Messages]] = {}
    for chat in chatstore.list_chats(chats_dir):
        data[chat.id] = {
            sender.key: preprocess_timed(
                chatstore.read_chat_sender(f"{chat.id}#{sender.key}", chats_dir)
            )
            for sender in chat.senders
        }
    return data


def corpus(data: dict[str, dict[str, Messages]], person: str, exclude: set[str]) -> Messages:
    """Все сообщения человека, кроме чатов из `exclude`."""
    texts: list[str] = []
    times: list[int | None] = []
    for chat_id, senders in data.items():
        if chat_id in exclude or person not in senders:
            continue
        messages = senders[person]
        texts += list(messages)
        times += list(messages.times or [None] * len(messages))
    return Messages(texts, times)


def pool(
    data: dict[str, dict[str, Messages]], exclude: set[str], skip: set[str], min_words: int
) -> dict[str, Messages]:
    """Люди с не менее чем `min_words` слов вне чатов `exclude`."""
    people = {key for senders in data.values() for key in senders} - skip
    found = {key: corpus(data, key, exclude) for key in sorted(people)}
    return {key: text for key, text in found.items() if count_words(text) >= min_words}


def equalize(candidates: dict[str, Messages], cap_words: int) -> dict[str, Messages]:
    return {key: cap_messages(text, cap_words, key) for key, text in candidates.items()}


def build_tasks(
    data: dict[str, dict[str, Messages]],
    min_words: int = 2500,
    unknown_words: int = 1400,
    cap_words: int = DEFAULT_CAP_WORDS,
    time_messages: int = 330,
    time_tasks: int = 12,
) -> list[Task]:
    """Задачи «через контексты» и «по времени» (см. описание модуля)."""
    tasks: list[Task] = []
    people = sorted({key for senders in data.values() for key in senders})
    for person in people:
        for chat_id, senders in data.items():
            own = senders.get(person)
            if own is None or count_words(own) < MIN_UNKNOWN_WORDS:
                continue
            candidates = pool(data, {chat_id}, set(), min_words)
            if person not in candidates or len(candidates) < 2:
                continue
            unknown = cap_messages(own, unknown_words, person + chat_id)
            tasks.append(Task("cross", person, unknown, equalize(candidates, cap_words)))

    if data:
        biggest = max(data, key=lambda chat_id: sum(len(m) for m in data[chat_id].values()))
        ranked = sorted(data[biggest].items(), key=lambda item: -count_words(item[1]))
        for person, _ in ranked[:time_tasks]:
            full = corpus(data, person, set())
            if len(full) < 3 * time_messages:
                continue
            times = full.times or [None] * len(full)
            order = sorted(range(len(full)), key=lambda i: (times[i] is None, times[i] or 0))
            last, rest = order[-time_messages:], order[:-time_messages]

            def take(indexes: list[int], full: Messages = full) -> Messages:
                ordered = sorted(indexes)
                stamps = full.times or [None] * len(full)
                return Messages([full[i] for i in ordered], [stamps[i] for i in ordered])

            candidates = pool(data, set(), {person}, min_words)
            candidates[person] = take(rest)
            if len(candidates) < 2 or count_words(candidates[person]) < min_words:
                continue
            unknown = cap_messages(take(last), unknown_words, person + "last")
            tasks.append(Task("time", person, unknown, equalize(candidates, cap_words)))
    return tasks


def evaluate(tasks: Sequence[Task], lexical: bool, cap_words: int = DEFAULT_CAP_WORDS) -> Summary:
    """Место настоящего человека по смеси методов во всех задачах."""
    ranks: list[int | None] = []
    chances: list[float] = []
    for task in tasks:
        results, _ = compare_messages(
            task.unknown, task.candidates, ensemble=True, lexical=lexical, cap_words=cap_words
        )
        order = [row.label for row in results]
        ranks.append(order.index(task.person) + 1 if task.person in order else None)
        chances.append(1 / len(task.candidates))
    count = len(tasks)
    if count == 0:
        return Summary(0, 0.0, 0.0, 0.0)
    return Summary(
        tasks=count,
        top1=sum(1 for rank in ranks if rank == 1) / count,
        mrr=sum(1 / rank for rank in ranks if rank) / count,
        chance=sum(chances) / count,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="experiments.chats_eval", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument(
        "--chats-dir",
        type=Path,
        default=None,
        help="папка с ОТКРЫТЫМИ файлами чатов (по умолчанию — зашифрованное хранилище)",
    )
    parser.add_argument("--min-words", type=int, default=2500, help="слов у кандидата вне чата")
    parser.add_argument("--unknown-words", type=int, default=1400, help="слов у неизвестного")
    parser.add_argument("--cap-words", type=int, default=DEFAULT_CAP_WORDS)
    parser.add_argument("--time-tasks", type=int, default=12, help="задач «по времени»")
    parser.add_argument("--lexical", action="store_true", help="смесь с лексикой")
    args = parser.parse_args(argv)

    try:
        if args.chats_dir is None:
            set_password_prompt(lambda: getpass.getpass("Мастер-пароль хранилища: "))
            unlock_interactively(default_vault())
        data = load_people(args.chats_dir)
    except ChatstyleError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    tasks = build_tasks(
        data,
        min_words=args.min_words,
        unknown_words=args.unknown_words,
        cap_words=args.cap_words,
        time_tasks=args.time_tasks,
    )
    if not tasks:
        print("Не нашлось ни одной задачи: нужны люди с текстом хотя бы в двух чатах.")
        return 1
    mode = "с лексикой" if args.lexical else "стилевая смесь"
    for kind in ("cross", "time", None):
        subset = [task for task in tasks if kind in (None, task.kind)]
        if not subset:
            continue
        summary = evaluate(subset, args.lexical, args.cap_words)
        title = {"cross": "через контексты", "time": "по времени", None: "все задачи"}[kind]
        print(
            f"{mode}, {title}: задач {summary.tasks}, top1 {summary.top1:.2f}, "
            f"MRR {summary.mrr:.2f}, случайно {summary.chance:.2f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
