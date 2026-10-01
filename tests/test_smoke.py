from chatstyle import _core


def test_core_version() -> None:
    assert _core.version() == "0.1.0"


def test_package_version_matches_core() -> None:
    import chatstyle

    assert chatstyle.__version__ == _core.version()
