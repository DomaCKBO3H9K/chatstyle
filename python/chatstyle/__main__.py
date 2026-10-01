def main() -> int:
    from chatstyle import _core
    print(f"chatstyle core {_core.version()}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
