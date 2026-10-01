"""Создаёт ВЫМЫШЛЕННЫЕ данные для примера из README и docs/example_report.md.

    python docs/make_example_data.py example_data

В папке появятся: unknown.txt (неизвестный автор), candidate_same.txt (тот же вымышленный
автор, другая часть текста), candidate_other.txt (другой вымышленный автор) и папка
impostors/ с четырьмя посторонними. Всё получено из experiments/make_synthetic.py с seed 1
и не имеет отношения к реальным людям.
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments.make_synthetic import make_dataset  # noqa: E402


def write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(target: Path) -> None:
    raw = target / "_raw"
    make_dataset(raw, authors=6, messages=800, seed=1, blend=0.6)

    def lines(name: str) -> list[str]:
        return (raw / f"{name}.txt").read_text(encoding="utf-8").splitlines()

    first = lines("a001")
    write(target / "unknown.txt", first[:300])
    write(target / "candidate_same.txt", first[300:600])
    write(target / "candidate_other.txt", lines("a002")[:300])
    for index, name in enumerate(["a003", "a004", "a005", "a006"], start=1):
        write(target / "impostors" / f"stranger{index}.txt", lines(name)[:300])
    shutil.rmtree(raw)  # служебная папка с пометкой SYNTHETIC не нужна в примере


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Использование: python docs/make_example_data.py ПАПКА")
    main(Path(sys.argv[1]))
    print(f"Готово: {sys.argv[1]}")
