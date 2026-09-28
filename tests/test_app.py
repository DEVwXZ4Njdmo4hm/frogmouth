"""Exercise the application through Textual's headless driver."""

from argparse import Namespace
from pathlib import Path

import pytest
from textual.widgets import DirectoryTree, Input, Markdown, TabbedContent

from frogmouth.app.app import MarkdownViewer
from frogmouth.data import load_bookmarks, load_config, load_history
from frogmouth.dialogs import HelpDialog, InformationDialog, InputDialog
from frogmouth.screens import Main
from frogmouth.widgets import Navigation, Omnibox, Viewer


async def test_local_markdown_and_navigation(tmp_path: Path) -> None:
    document = tmp_path / "中文文档.md"
    document.write_text("# 中文标题\n\n正文 café\n\n## 第二节\n", encoding="utf-8")
    app = MarkdownViewer(Namespace(file=[str(document)]))

    async with app.run_test(size=(120, 40)) as pilot:
        for worker in list(app.workers):
            if isinstance(worker.node, Viewer):
                await worker.wait()
        await pilot.pause()
        viewer = app.screen.query_one(Viewer)
        navigation = app.screen.query_one(Navigation)
        tabs = navigation.query_one(TabbedContent)

        assert viewer.location == document
        assert "中文标题" in viewer.document.source
        assert "正文 café" in viewer.document.source
        assert len(viewer.document.table_of_contents) == 2
        assert app.screen.query_one(Omnibox).visiting == str(document)
        assert load_history() == [document]
        assert not navigation.popped_out

        for key, pane in (
            ("ctrl+t", navigation.table_of_contents),
            ("ctrl+l", navigation.local_files),
            ("ctrl+b", navigation.bookmarks),
            ("ctrl+y", navigation.history),
        ):
            await pilot.press(key)
            assert navigation.popped_out
            assert tabs.active == pane.id
            await pilot.press(key)
            assert not navigation.popped_out

        await pilot.press("ctrl+t")
        await pilot.press("full_stop")
        assert tabs.active == navigation.local_files.id
        assert navigation.local_files.query_one(DirectoryTree).has_focus

        await pilot.press("comma")
        assert tabs.active == navigation.table_of_contents.id
        await pilot.press("comma")
        assert tabs.active == navigation.history.id
        await pilot.press("full_stop")
        assert tabs.active == navigation.table_of_contents.id

        await pilot.press("ctrl+n")
        assert not navigation.popped_out
        await pilot.press("ctrl+n")
        assert navigation.popped_out


async def test_directory_command_preserves_case(tmp_path: Path) -> None:
    directory = tmp_path / "MixedCase目录"
    directory.mkdir()
    app = MarkdownViewer(Namespace(file=[]))

    async with app.run_test(size=(120, 40)) as pilot:
        omnibox = app.screen.query_one(Omnibox)
        omnibox.value = f"CD {directory}"
        omnibox.focus()
        await pilot.press("enter")
        for worker in list(app.workers):
            if isinstance(worker.node, Viewer):
                await worker.wait()
        await pilot.pause()

        navigation = app.screen.query_one(Navigation)
        assert navigation.popped_out
        assert navigation.query_one(TabbedContent).active == navigation.local_files.id
        assert navigation.local_files.query_one(DirectoryTree).path == directory


async def test_theme_toggle_is_persisted() -> None:
    app = MarkdownViewer(Namespace(file=[]))

    async with app.run_test() as pilot:
        assert app.theme == "textual-dark"
        await pilot.press("f10")
        assert app.theme == "textual-light"
        assert load_config().light_mode

    load_config.cache_clear()
    restored = MarkdownViewer(Namespace(file=[]))
    async with restored.run_test() as pilot:
        assert restored.theme == "textual-light"
        await pilot.press("f10")
        assert restored.theme == "textual-dark"
        assert not load_config().light_mode


async def test_help_and_about_dialogs() -> None:
    app = MarkdownViewer(Namespace(file=[]))

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("f1")
        assert isinstance(app.screen, HelpDialog)
        await pilot.press("escape")
        assert isinstance(app.screen, Main)

        await pilot.press("f2")
        assert isinstance(app.screen, InformationDialog)
        await pilot.press("enter")
        assert isinstance(app.screen, Main)


@pytest.mark.parametrize("cancel_with_button", [False, True])
async def test_bookmark_cancel_and_save(
    tmp_path: Path, cancel_with_button: bool
) -> None:
    document = tmp_path / "Notes.md"
    document.write_text("# Notes\n", encoding="utf-8")
    app = MarkdownViewer(Namespace(file=[str(document)]))

    async with app.run_test(size=(120, 40)) as pilot:
        for worker in list(app.workers):
            if isinstance(worker.node, Viewer):
                await worker.wait()
        await pilot.pause()
        await pilot.press("ctrl+d")
        assert isinstance(app.screen, InputDialog)
        app.screen.query_one(Input).value = "Cancelled"

        if cancel_with_button:
            await pilot.click("#cancel")
        else:
            await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, Main)
        assert load_bookmarks() == []

        await pilot.press("ctrl+d")
        assert isinstance(app.screen, InputDialog)
        app.screen.query_one(Input).value = "中文书签 Café"
        await pilot.press("enter")
        assert isinstance(app.screen, Main)
        bookmarks = load_bookmarks()
        assert len(bookmarks) == 1
        assert bookmarks[0].title == "中文书签 Café"
        assert bookmarks[0].location == document


async def test_history_edits_preserve_the_displayed_document(tmp_path: Path) -> None:
    previous_directory = tmp_path / "previous"
    current_directory = tmp_path / "current"
    previous_directory.mkdir()
    current_directory.mkdir()
    previous = previous_directory / "Previous.md"
    current = current_directory / "Current.md"
    linked = current_directory / "Next.md"
    previous.write_text("# Previous\n", encoding="utf-8")
    current.write_text("# Current\n\n[Next](Next.md)\n", encoding="utf-8")
    linked.write_text("# Linked document\n", encoding="utf-8")
    app = MarkdownViewer(Namespace(file=[str(previous)]))

    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.screen.query_one(Viewer)
        omnibox = app.screen.query_one(Omnibox)
        for worker in list(app.workers):
            if isinstance(worker.node, Viewer):
                await worker.wait()
        await pilot.pause()

        viewer.visit(current)
        for worker in list(app.workers):
            if isinstance(worker.node, Viewer):
                await worker.wait()
        await pilot.pause()
        assert viewer.history.locations == [previous, current]

        viewer.delete_history(1)
        await pilot.pause()
        assert viewer.history.locations == [previous]
        assert viewer.location == current
        assert viewer.document.source == current.read_text(encoding="utf-8")
        assert omnibox.visiting == str(current)

        viewer.clear_history()
        await pilot.pause()
        assert viewer.history.locations == []
        assert viewer.location == current
        assert viewer.document.source == current.read_text(encoding="utf-8")
        assert omnibox.visiting == str(current)

        viewer.document.post_message(Markdown.LinkClicked(viewer.document, "Next.md"))
        await pilot.pause()
        for worker in list(app.workers):
            if isinstance(worker.node, Viewer):
                await worker.wait()
        await pilot.pause()

        assert viewer.location == linked
        assert viewer.document.source == linked.read_text(encoding="utf-8")
        assert omnibox.visiting == str(linked)
        assert viewer.history.locations == [linked]
