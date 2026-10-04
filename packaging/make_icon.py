"""Рисует иконку chatstyle и сохраняет её в .ico (PNG-кадры 16-256 px).

    python packaging/make_icon.py [python/chatstyle/resources/chatstyle.ico]

Нужен matplotlib (`pip install -e .[experiments]`). Готовый chatstyle.ico лежит в
python/chatstyle/resources/ (его же берёт окно приложения), поэтому для сборки exe matplotlib
не требуется; скрипт нужен, чтобы иконку можно было воспроизвести и изменить. Знак собственный:
белое облачко сообщения с тремя строчками текста на синем фоне (цвет из палитры проекта).
"""

import struct
import sys
from io import BytesIO
from pathlib import Path

from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch, Polygon

SIZES = (16, 24, 32, 48, 64, 128, 256)
BLUE = "#2a78d6"
WHITE = "#ffffff"


def render_png(size: int) -> bytes:
    """Один кадр иконки в PNG с прозрачным фоном."""
    figure = Figure(figsize=(1, 1), dpi=size)
    axes = figure.add_axes((0, 0, 1, 1))
    axes.set_xlim(0, 100)
    axes.set_ylim(0, 100)
    axes.axis("off")
    figure.patch.set_alpha(0.0)
    axes.add_patch(
        FancyBboxPatch((2, 2), 96, 96, boxstyle="round,pad=0,rounding_size=22", fc=BLUE, ec="none")
    )
    axes.add_patch(
        FancyBboxPatch(
            (17, 34), 66, 46, boxstyle="round,pad=0,rounding_size=10", fc=WHITE, ec="none"
        )
    )
    axes.add_patch(Polygon([(30, 36), (30, 18), (50, 36)], closed=True, fc=WHITE, ec="none"))
    for y, width in ((66, 42), (55, 34), (44, 24)):
        axes.add_patch(
            FancyBboxPatch(
                (27, y - 2.5),
                width,
                5,
                boxstyle="round,pad=0,rounding_size=2.5",
                fc=BLUE,
                ec="none",
            )
        )
    buffer = BytesIO()
    figure.savefig(buffer, format="png", dpi=size, transparent=True)
    return buffer.getvalue()


def build_ico(frames: dict[int, bytes]) -> bytes:
    """Собрать .ico из PNG-кадров (формат ICONDIR, кадры в PNG поддерживает Windows Vista+)."""
    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = len(header) + 16 * len(frames)
    entries = b""
    body = b""
    for size, png in sorted(frames.items()):
        dimension = 0 if size >= 256 else size  # 0 означает 256
        entries += struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(png), offset)
        body += png
        offset += len(png)
    return header + entries + body


def main(target: Path) -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    frames = {size: render_png(size) for size in SIZES}
    target.write_bytes(build_ico(frames))
    print(f"Иконка записана: {target} ({target.stat().st_size} байт, размеры: {list(SIZES)})")


if __name__ == "__main__":
    main(
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parent.parent
        / "python"
        / "chatstyle"
        / "resources"
        / "chatstyle.ico"
    )
