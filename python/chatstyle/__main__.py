import os
import sys


def main() -> None:
    from chatstyle.cli import app
    from chatstyle.launcher import (
        configure_streams,
        console_process_count,
        pause,
        should_pause,
    )

    configure_streams()
    try:
        app(prog_name="chatstyle")
    finally:
        # finally: окно не должно закрыться до прочтения и при ошибке; код выхода сохраняется
        if should_pause(
            sys.argv,
            frozen=bool(getattr(sys, "frozen", False)),
            process_count=console_process_count(),
            environ=os.environ,
        ):
            pause()


if __name__ == "__main__":
    main()
