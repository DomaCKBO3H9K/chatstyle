"""Генератор таблиц Unicode для C++ ядра.

Скрипт анализирует данные модуля `unicodedata` и создаёт два файла:
- `unicode_letters.inc` — диапазоны букв (категории L и M).
- `unicode_lower.inc` — правила приведения к нижнему регистру.

Файлы записываются в `core/src/` относительно корня репозитория.
"""

import unicodedata
from pathlib import Path


def letter_ranges() -> list[tuple[int, int]]:
    """Вернуть отсортированный список диапазонов букв (L* и M*).

    Обходит кодпоинты 0..0x10FFFF, исключая суррогаты (0xD800..0xDFFF).
    Смежные кодпоинты объединяются в [first, last] включительно.
    """
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    prev: int | None = None

    for cp in range(0x110000):
        # Пропускаем суррогаты
        if 0xD800 <= cp <= 0xDFFF:
            continue

        cat = unicodedata.category(chr(cp))
        if cat.startswith("L") or cat.startswith("M"):
            if start is None:
                start = cp
                prev = cp
            elif cp == prev + 1:
                prev = cp
            else:
                ranges.append((start, prev))
                start = cp
                prev = cp
        else:
            if start is not None:
                ranges.append((start, prev))
                start = None
                prev = None

    if start is not None and prev is not None:
        ranges.append((start, prev))

    return ranges


def lower_ranges() -> list[tuple[int, int, int, int]]:
    """Вернуть сжатые правила приведения к нижнему регистру.

    Для каждого кодпоинта (без суррогатов) вычисляется `chr(cp).lower()`.
    Записываются только те, у которых результат — один символ и отличен от исходного.
    Данные сжимаются в диапазоны (first, last, delta, step).
    """
    pairs: list[tuple[int, int]] = []  # (cp, delta)
    for cp in range(0x110000):
        if 0xD800 <= cp <= 0xDFFF:
            continue
        lowered = chr(cp).lower()
        if len(lowered) == 1:
            lower_cp = ord(lowered)
            if lower_cp != cp:
                pairs.append((cp, lower_cp - cp))

    if not pairs:
        return []

    ranges: list[tuple[int, int, int, int]] = []
    index = 0
    while index < len(pairs):
        first_cp, delta = pairs[index]
        last = index
        step = 1
        # шаг 1 или 2 выбирается один раз по двум первым элементам и дальше не меняется
        if index + 1 < len(pairs) and pairs[index + 1][1] == delta:
            gap = pairs[index + 1][0] - first_cp
            if gap in (1, 2):
                step = gap
                last = index + 1
                while (
                    last + 1 < len(pairs)
                    and pairs[last + 1][1] == delta
                    and pairs[last + 1][0] - pairs[last][0] == step
                ):
                    last += 1
        ranges.append((first_cp, pairs[last][0], delta, step))
        index = last + 1
    return ranges


def render_letters(ranges: list[tuple[int, int]]) -> str:
    """Отрендерить диапазоны букв в C++ код."""
    lines = [
        "// Сгенерировано tools/gen_unicode_tables.py (Unicode "
        + unicodedata.unidata_version
        + "). Не править вручную.\n"
    ]
    for first, last in ranges:
        lines.append(f"    {{0x{first:04X}, 0x{last:04X}}},\n")
    return "".join(lines)


def render_lower(ranges: list[tuple[int, int, int, int]]) -> str:
    """Отрендерить правила lower в C++ код."""
    lines = [
        "// Сгенерировано tools/gen_unicode_tables.py (Unicode "
        + unicodedata.unidata_version
        + "). Не править вручную.\n"
    ]
    for first, last, delta, step in ranges:
        lines.append(f"    {{0x{first:04X}, 0x{last:04X}, {delta}, {step}}},\n")
    return "".join(lines)


def main() -> None:
    """Записать сгенерированные файлы и вывести статистику."""
    root = Path(__file__).resolve().parent.parent
    out_dir = root / "core" / "src"
    out_dir.mkdir(parents=True, exist_ok=True)

    letters = letter_ranges()
    lowers = lower_ranges()

    letters_path = out_dir / "unicode_letters.inc"
    lowers_path = out_dir / "unicode_lower.inc"

    letters_path.write_text(render_letters(letters), encoding="utf-8", newline="\n")
    lowers_path.write_text(render_lower(lowers), encoding="utf-8", newline="\n")

    print(f"Unicode version: {unicodedata.unidata_version}")
    print(f"Letter ranges: {len(letters)} -> {letters_path}")
    print(f"Lower ranges: {len(lowers)} -> {lowers_path}")


if __name__ == "__main__":
    main()
