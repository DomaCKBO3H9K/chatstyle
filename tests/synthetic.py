"""Детерминированные синтетические «авторы» для тестов: никаких реальных переписок."""

import random
from pathlib import Path

CASUAL = ["ну", "типа", "короче", "блин", "я", "и", "не", "щас"]
FORMAL = ["что", "для", "при", "также", "однако", "это", "в", "поэтому"]
OTHERS = [
    ["да", "нет", "может", "сегодня", "завтра", "потом"],
    ["работа", "проект", "срок", "отчёт", "задача", "встреча"],
    ["кот", "дом", "лес", "река", "поле", "город"],
    ["книга", "фильм", "музыка", "игра", "спорт", "кино"],
]


def casual(seed: int, count: int = 60) -> list[str]:
    rng = random.Random(seed)
    lines = []
    for _ in range(count):
        text = " ".join(rng.choice(CASUAL) for _ in range(rng.randint(8, 14)))
        lines.append(text + ("))" if rng.random() < 0.6 else ""))
    return lines


def formal(seed: int, count: int = 60) -> list[str]:
    rng = random.Random(seed)
    lines = []
    for _ in range(count):
        words = [rng.choice(FORMAL) for _ in range(rng.randint(8, 14))]
        words[0] = words[0].capitalize()
        lines.append(" ".join(words) + ".")
    return lines


def other(index: int, seed: int, count: int = 60) -> list[str]:
    rng = random.Random(seed)
    words = OTHERS[index % len(OTHERS)]
    return [" ".join(rng.choice(words) for _ in range(rng.randint(8, 14))) for _ in range(count)]


def write_lines(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_workspace(root: Path) -> dict[str, Path]:
    """Неизвестный автор, «свой» и «чужой» кандидаты и папка с четырьмя посторонними."""
    impostors = root / "impostors"
    impostors.mkdir()
    for index in range(len(OTHERS)):
        write_lines(impostors / f"o{index}.txt", other(index, 10 + index))
    return {
        "unknown": write_lines(root / "unknown.txt", casual(1)),
        "same": write_lines(root / "same.txt", casual(2)),
        "other": write_lines(root / "other.txt", formal(3)),
        "impostors": impostors,
    }
