"""График «качество в зависимости от объёма текста» (matplotlib, светлая тема).

Цвета методов — первые три слота проверенной категориальной палитры (синий, оранжевый,
аквамарин); различие закреплено формой маркеров, а не только цветом. У аквамарина контраст с
фоном ниже 3:1, поэтому всегда есть легенда и таблица volume.md. Текст не окрашивается цветом
серий. Фигура создаётся напрямую, без pyplot: глобальный бэкенд не затрагивается.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from matplotlib.figure import Figure
from matplotlib.ticker import NullLocator

from experiments.evaluate import METHODS

if TYPE_CHECKING:
    from experiments.volume import VolumeReport

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
AXIS = "#c9c8c3"
GRID = "#e4e3df"
SERIES = {"cosine": "#2a78d6", "delta": "#eb6834", "impostors": "#1baf7a"}
MARKERS = {"cosine": "o", "delta": "s", "impostors": "^"}
WATERMARK = "СИНТЕТИЧЕСКИЕ ДАННЫЕ"

TITLE = "Качество верификации в зависимости от объёма текста"
SUBTITLE = (
    "Объём — слов у неизвестного автора и у кандидата; n — число авторов.\n"
    "Полоса — 95% ДИ (бутстрэп по авторам). Точность: порог подобран кросс-валидацией (CV)."
)


def _points(report: "VolumeReport", method: str, metric: str) -> list[tuple[int, float]]:
    points = []
    for item in report.slices:
        value = item.metrics[method][metric]
        if value is not None and item.metrics[method]["trials"]:
            points.append((item.words, float(value)))  # type: ignore[arg-type]
    return points


def _band(report: "VolumeReport", method: str) -> list[tuple[int, float, float]]:
    rows = []
    for item in report.slices:
        interval = item.metrics[method]["auc_ci95"]
        if interval is not None:
            rows.append((item.words, float(interval[0]), float(interval[1])))  # type: ignore[index]
    return rows


def _style_axes(ax, report: "VolumeReport", ylabel: str) -> None:  # noqa: ANN001
    ax.set_facecolor(SURFACE)
    ax.set_xscale("log")
    words = [item.words for item in report.slices]
    ax.set_xticks(words)
    ax.set_xticklabels(
        [f"{item.words}\nn={item.authors}" for item in report.slices],
        color=INK_SECONDARY,
        fontsize=9,
    )
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xlim(min(words) / 1.35, max(words) * 1.35)
    ax.set_ylim(0.3, 1.02)
    ax.set_yticks([0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    ax.tick_params(axis="y", colors=INK_SECONDARY, labelsize=9, length=0)
    ax.tick_params(axis="x", length=3, color=AXIS)
    ax.set_ylabel(ylabel, color=INK_SECONDARY, fontsize=10)
    ax.set_xlabel("слов в каждом из двух текстов", color=INK_SECONDARY, fontsize=10)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
        ax.spines[side].set_linewidth(0.8)
    ax.axhline(0.5, color=AXIS, linewidth=0.8, zorder=1)
    ax.text(
        min(words) / 1.3,
        0.505,
        "случайное угадывание",
        color=INK_SECONDARY,
        fontsize=8,
        va="bottom",
    )


def _draw_series(ax, report: "VolumeReport", metric: str, bands: bool) -> None:  # noqa: ANN001
    for method, (title, _) in METHODS.items():
        points = _points(report, method, metric)
        if not points:
            continue
        xs, ys = zip(*points, strict=True)
        color = SERIES[method]
        if bands:
            band = _band(report, method)
            if len(band) >= 2:
                ax.fill_between(
                    [w for w, _, _ in band],
                    [low for _, low, _ in band],
                    [high for _, _, high in band],
                    color=color,
                    alpha=0.10,
                    linewidth=0,
                    zorder=2,
                )
            else:
                for w, low, high in band:
                    ax.vlines(w, low, high, color=color, linewidth=1.2, zorder=2)
        ax.plot(
            xs,
            ys,
            color=color,
            linewidth=1.3,
            marker=MARKERS[method],
            markersize=7,
            markerfacecolor=color,
            markeredgecolor=SURFACE,
            markeredgewidth=1.4,
            label=title,
            zorder=3,
        )


def _unavailable_note(report: "VolumeReport") -> str | None:
    gaps = []
    for method, (title, _) in METHODS.items():
        missing = [str(item.words) for item in report.slices if not item.metrics[method]["trials"]]
        if missing:
            gaps.append(f"{title}: {', '.join(missing)}")
    if not gaps:
        return None
    return "Нет точки — метод недоступен при таком объёме (слов). " + "; ".join(gaps) + "."


def build_figure(report: "VolumeReport") -> Figure:
    """Две панели: ROC AUC с 95% ДИ и точность с честным порогом."""
    figure = Figure(figsize=(11, 5.0), dpi=150, facecolor=SURFACE)
    left, right = figure.subplots(1, 2)
    figure.subplots_adjust(top=0.70, bottom=0.2, left=0.07, right=0.985, wspace=0.24)

    _style_axes(left, report, "ROC AUC")
    _style_axes(right, report, "Точность (порог по CV)")
    _draw_series(left, report, "auc", bands=True)
    _draw_series(right, report, "accuracy_cv", bands=False)

    title = TITLE + (" (синтетика)" if report.synthetic else "")
    figure.text(0.07, 0.945, title, color=INK, fontsize=14, fontweight="bold", ha="left", va="top")
    figure.text(
        0.07,
        0.885,
        SUBTITLE,
        color=INK_SECONDARY,
        fontsize=9.5,
        ha="left",
        va="top",
        linespacing=1.5,
    )
    handles, labels = left.get_legend_handles_labels()
    if handles:
        figure.legend(
            handles,
            labels,
            loc="upper left",
            bbox_to_anchor=(0.062, 0.80),
            ncol=len(handles),
            frameon=False,
            fontsize=10,
            labelcolor=INK,
            handlelength=2.2,
        )
    note = _unavailable_note(report)
    if note:
        figure.text(0.07, 0.045, note, color=INK_SECONDARY, fontsize=8.5, ha="left", va="bottom")
    if report.synthetic:
        figure.text(
            0.5,
            0.45,
            WATERMARK,
            color=INK,
            alpha=0.08,
            fontsize=42,
            fontweight="bold",
            rotation=18,
            ha="center",
            va="center",
        )
    return figure


def save_plot(report: "VolumeReport", path: Path) -> None:
    """Сохранить график в PNG."""
    figure = build_figure(report)
    figure.savefig(path, dpi=150, facecolor=figure.get_facecolor())
