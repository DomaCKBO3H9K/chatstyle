"""Запуск окна: `python -m chatstyle.gui` и точка входа chatstyle-gui.exe (без консоли)."""

import os
import sys


def main() -> None:
    # в сборке без консоли (console=False) sys.stdout и sys.stderr равны None: пишем в никуда
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115
    if len(sys.argv) == 3 and sys.argv[1] == "--selftest":
        from pathlib import Path

        from chatstyle.gui.selftest import run as run_selftest

        raise SystemExit(run_selftest(Path(sys.argv[2])))
    from chatstyle.gui import main as run_gui

    raise SystemExit(run_gui())


if __name__ == "__main__":
    main()
