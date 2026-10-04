"""Проверка распознавания на вымышленных переписках docs/demo/ (на каждом языке).

    python docs/demo_eval.py [ru en es fr zh ar]

Для каждого человека берётся его текст из одной переписки как «неизвестный» и сравнивается с
текстами всех четырёх людей из другой переписки (поездка → работа и работа → поездка).
Правильно, если первым стоит тот же человек. Данные вымышленные, числа показывают только
работоспособность метода на разных письменностях, а не точность на живых людях.
"""

import sys
from pathlib import Path

from chatstyle.pipeline import run_comparison

DEMO = Path(__file__).resolve().parent / "demo"
CHATS = ("trip", "work")
LANGUAGES = ("ru", "en", "es", "fr", "zh", "ar")


def read_chat(chat: str, lang: str) -> dict[str, list[str]]:
    people: dict[str, list[str]] = {}
    path = DEMO / f"{chat}.{lang}.txt"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            name, text = line.split("\t", 1)
            people.setdefault(name, []).append(text)
    return people


def write_people(directory: Path, people: dict[str, list[str]]) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    sources = {}
    for index, (name, messages) in enumerate(people.items()):
        path = directory / f"person{index}.txt"
        path.write_text("\n".join(messages), encoding="utf-8")
        sources[name] = f"file:{path}"
    return sources


def evaluate(lang: str, work: Path, lexical: bool) -> tuple[int, int]:
    chats = {chat: read_chat(chat, lang) for chat in CHATS}
    hits = total = 0
    for source, target in (("trip", "work"), ("work", "trip")):
        known = write_people(work / lang / f"{target}", chats[target])
        unknown = write_people(work / lang / f"{source}", chats[source])
        for name in unknown:
            result = run_comparison(
                unknown[name], [known[person] for person in known], lexical=lexical
            )
            total += 1
            hits += result.candidates[0].label == known[name]
    return hits, total


def main(argv: list[str]) -> None:
    import tempfile

    languages = argv[1:] or [lang for lang in LANGUAGES if (DEMO / f"trip.{lang}.txt").exists()]
    with tempfile.TemporaryDirectory() as tmp:
        for lang in languages:
            row = []
            for lexical in (False, True):
                hits, total = evaluate(lang, Path(tmp), lexical)
                row.append(f"{'лексика' if lexical else 'стиль'}: {hits} из {total}")
            print(f"{lang}: " + "; ".join(row))


if __name__ == "__main__":
    main(sys.argv)
