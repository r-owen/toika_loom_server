def test_version() -> None:
    try:
        import toika_loom_server.version
    except ImportError:
        raise AssertionError("version file not found")

    assert toika_loom_server.version.__all__ == ["__version__"]
    assert isinstance(toika_loom_server.version.__version__, str)
