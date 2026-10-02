"""Тяжёлые вызовы ядра отпускают GIL: графическое окно не замирает на время расчёта."""

import threading
import time

import pytest
from chatstyle.delta import burrows_delta
from chatstyle.impostors import general_impostors
from synthetic import casual, formal, other


def count_ticks_while_running(function) -> tuple[float, int]:  # noqa: ANN001
    """Сколько раз главный поток успел «проснуться», пока в другом потоке идёт расчёт."""
    thread = threading.Thread(target=function)
    ticks = 0
    started = time.perf_counter()
    thread.start()
    while thread.is_alive():
        time.sleep(0.005)
        ticks += 1
    thread.join()
    return time.perf_counter() - started, ticks


def test_general_impostors_does_not_hold_the_gil() -> None:
    unknown = casual(1, 3000)
    candidates = {"a": casual(2, 3000), "b": formal(3, 3000)}
    impostors = {f"o{i}": other(i, 10 + i, 3000) for i in range(12)}

    elapsed, ticks = count_ticks_while_running(
        lambda: general_impostors(unknown, candidates, impostors, chunk_words=200)
    )
    if elapsed < 0.3:
        pytest.skip("расчёт слишком короткий для проверки на этой машине")
    # без отпускания GIL главный поток почти не получал бы управление (единицы тиков)
    assert ticks > elapsed / 0.05, f"{ticks} тиков за {elapsed:.2f} с"


def test_burrows_delta_does_not_hold_the_gil() -> None:
    unknown = casual(1, 12000)
    candidates = {f"c{i}": casual(2 + i, 12000) for i in range(6)}

    elapsed, ticks = count_ticks_while_running(lambda: burrows_delta(unknown, candidates))
    if elapsed < 0.3:
        pytest.skip("расчёт слишком короткий для проверки на этой машине")
    assert ticks > elapsed / 0.05, f"{ticks} тиков за {elapsed:.2f} с"
