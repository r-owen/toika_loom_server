def test_version() -> None:
    try:
        import toika_loom_server.version  # noqa: PLC0415
    except ImportError:
        raise AssertionError("version file not found") from None

    assert toika_loom_server.version.__all__ == ["__version__"]
    assert isinstance(toika_loom_server.version.__version__, str)
