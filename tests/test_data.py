"""Regression tests for application data storage."""

from pathlib import Path

from httpx import URL

from frogmouth.data import (
    Bookmark,
    Config,
    load_bookmarks,
    load_config,
    load_history,
    save_bookmarks,
    save_config,
    save_history,
)
from frogmouth.data.bookmarks import bookmarks_file
from frogmouth.data.config import config_file
from frogmouth.data.history import history_file


def test_config_defaults_and_cache_refresh() -> None:
    """Create defaults and reload changed settings without a stale cache."""
    assert load_config() == Config()
    assert config_file().is_file()

    configured = Config(
        light_mode=True,
        markdown_extensions=[".md", ".markdown", ".中文"],
        navigation_left=False,
    )
    assert save_config(configured) == configured
    assert load_config() == configured


def test_utf8_config_from_disk() -> None:
    """Accept UTF-8 configuration files edited outside the application."""
    config_file().write_text(
        '{"markdown_extensions": [".md", ".中文"]}', encoding="utf-8"
    )
    assert load_config().markdown_extensions == [".md", ".中文"]


def test_history_round_trip() -> None:
    """Preserve paths and URLs when saving and reloading browser history."""
    assert load_history() == []
    locations: list[Path | URL] = [
        Path("/tmp/文档.md"),
        URL("https://example.com/README.md?lang=zh"),
    ]

    save_history(locations)

    assert load_history() == locations
    assert history_file().is_file()
    save_history([])
    assert load_history() == []


def test_bookmarks_round_trip() -> None:
    """Preserve bookmark titles and local or remote locations."""
    assert load_bookmarks() == []
    bookmarks = [
        Bookmark("中文文档", Path("/tmp/文档.md")),
        Bookmark("Remote README", URL("https://example.com/README.md")),
    ]

    save_bookmarks(bookmarks)

    assert load_bookmarks() == bookmarks
    assert bookmarks_file().is_file()
    save_bookmarks([])
    assert load_bookmarks() == []
