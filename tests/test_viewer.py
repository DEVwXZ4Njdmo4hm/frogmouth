"""Cover viewer history boundaries and HTTP document loading."""

from argparse import Namespace
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import httpx
import pytest
from httpx import URL
from textual.widgets import Markdown

from frogmouth.app.app import MarkdownViewer
from frogmouth.dialogs import ErrorDialog
from frogmouth.utility.advertising import USER_AGENT
from frogmouth.widgets import Omnibox, Viewer
from frogmouth.widgets import viewer as viewer_module
from frogmouth.widgets.viewer import History


@pytest.mark.parametrize(
    ("back_steps", "deleted", "expected_location", "expected_index"),
    [
        (0, 2, None, None),
        (0, -1, None, None),
        (0, 0, "c.md", 1),
        (1, 0, "b.md", 0),
        (1, 1, None, None),
        (1, 2, "b.md", 1),
        (2, 0, None, None),
        (2, 2, "a.md", 0),
    ],
)
def test_history_delete_preserves_the_cursor_position(
    back_steps: int,
    deleted: int,
    expected_location: str | None,
    expected_index: int | None,
) -> None:
    history = History([Path("a.md"), Path("b.md"), Path("c.md")])
    for _ in range(back_steps):
        assert history.back()

    del history[deleted]

    if expected_location is None:
        assert history.location is None
    else:
        assert history.location == Path(expected_location)
    assert history.current == expected_index
    assert len(history.locations) == 2


@pytest.mark.parametrize(
    ("deleted", "direction", "expected_location"),
    [
        (2, "back", "b.md"),
        (1, "back", "a.md"),
        (1, "forward", "c.md"),
        (0, "forward", "b.md"),
    ],
)
def test_history_moves_from_a_deleted_current_item(
    deleted: int, direction: str, expected_location: str
) -> None:
    history = History([Path("a.md"), Path("b.md"), Path("c.md")])
    while history.current != deleted:
        assert history.back()

    del history[deleted]
    assert history.location is None
    assert history.current is None

    if direction == "back":
        assert history.back()
    else:
        assert history.forward()

    assert history.location == Path(expected_location)
    assert history.current == history.locations.index(Path(expected_location))


@pytest.mark.parametrize(("deleted", "direction"), [(0, "back"), (2, "forward")])
def test_history_keeps_the_deleted_position_at_an_end_boundary(
    deleted: int, direction: str
) -> None:
    history = History([Path("a.md"), Path("b.md"), Path("c.md")])
    while history.current != deleted:
        assert history.back()

    del history[deleted]
    if direction == "back":
        assert not history.back()
        assert history.location is None
        assert history.forward()
    else:
        assert not history.forward()
        assert history.location is None
        assert history.back()

    assert history.location == Path("b.md")


@pytest.mark.parametrize(
    ("deleted", "key", "expected"),
    [(2, "ctrl+left", 1), (1, "ctrl+left", 0), (1, "ctrl+right", 2)],
)
async def test_viewer_history_navigation_after_deleting_the_current_item(
    tmp_path: Path, deleted: int, key: str, expected: int
) -> None:
    documents = [tmp_path / "a.md", tmp_path / "b.md", tmp_path / "c.md"]
    for document in documents:
        document.write_text(f"# {document.stem}\n", encoding="utf-8")
    app = MarkdownViewer(Namespace(file=[]))

    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.screen.query_one(Viewer)
        omnibox = app.screen.query_one(Omnibox)
        for document in documents:
            viewer.visit(document)
            for worker in list(app.workers):
                if isinstance(worker.node, Viewer):
                    await worker.wait()
            await pilot.pause()

        if deleted == 1:
            await pilot.press("ctrl+left")
            for worker in list(app.workers):
                if isinstance(worker.node, Viewer):
                    await worker.wait()
            await pilot.pause()

        viewer.delete_history(deleted)
        await pilot.pause()
        assert viewer.history.location is None
        assert viewer.location == documents[deleted]
        assert omnibox.visiting == str(documents[deleted])

        await pilot.press(key)
        for worker in list(app.workers):
            if isinstance(worker.node, Viewer):
                await worker.wait()
        await pilot.pause()

        assert viewer.location == documents[expected]
        assert viewer.history.location == documents[expected]
        assert viewer.document.source == documents[expected].read_text(encoding="utf-8")
        assert omnibox.visiting == str(documents[expected])


def test_history_empty_and_end_boundaries() -> None:
    history = History()
    assert history.location is None
    assert history.current is None
    assert not history.back()
    assert not history.forward()

    history.remember(Path("first.md"))
    assert not history.back()
    assert not history.forward()
    del history[0]
    assert history.location is None
    assert history.current is None
    assert not history.back()
    assert not history.forward()

    history.remember(Path("second.md"))
    history.remember(Path("third.md"))
    assert history.back()
    assert not history.back()
    assert history.forward()
    assert not history.forward()


def test_history_invalid_deletion_preserves_current_item() -> None:
    history = History([Path("first.md")])
    with pytest.raises(IndexError):
        del history[1]
    assert history.location == Path("first.md")
    assert history.current == 0


@pytest.mark.parametrize(
    "content_type", ["text/plain", "text/markdown", "text/x-markdown"]
)
async def test_remote_markdown_load(
    monkeypatch: pytest.MonkeyPatch, content_type: str
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": f"{content_type}; charset=utf-8"},
            text="# Remote 中文\n\nCafé\n",
        )

    def create_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(respond))

    monkeypatch.setattr(viewer_module, "AsyncClient", create_client)
    app = MarkdownViewer(Namespace(file=[]))
    location = URL("https://example.test/README.md")

    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.screen.query_one(Viewer)
        viewer.visit(location)
        for worker in list(app.workers):
            if isinstance(worker.node, Viewer):
                await worker.wait()
        await pilot.pause()

        assert viewer.location == location
        assert viewer.history.locations == [location]
        assert "Remote 中文" in viewer.document.source
        assert "Café" in viewer.document.source
        assert requests[0].headers["user-agent"] == USER_AGENT


@pytest.mark.parametrize("failure", ["http", "request"])
async def test_remote_errors_open_a_dialog(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if failure == "request":
            raise httpx.ConnectError("Connection refused", request=request)
        return httpx.Response(404)

    def create_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(respond))

    monkeypatch.setattr(viewer_module, "AsyncClient", create_client)
    app = MarkdownViewer(Namespace(file=[]))

    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.screen.query_one(Viewer)
        viewer.visit(URL("https://example.test/missing.md"))
        for worker in list(app.workers):
            if isinstance(worker.node, Viewer):
                await worker.wait()
        await pilot.pause()

        assert isinstance(app.screen, ErrorDialog)
        assert viewer.location is None
        assert viewer.history.locations == []
        await pilot.press("escape")


async def test_non_markdown_response_opens_externally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[str] = []

    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body>Rendered Markdown</body></html>",
        )

    def create_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(respond))

    def open_external(url: str) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr(viewer_module, "AsyncClient", create_client)
    monkeypatch.setattr(viewer_module, "open_url", open_external)
    app = MarkdownViewer(Namespace(file=[]))
    location = URL("https://example.test/rendered.md")

    async with app.run_test() as pilot:
        viewer = app.screen.query_one(Viewer)
        viewer.visit(location)
        for worker in list(app.workers):
            if isinstance(worker.node, Viewer):
                await worker.wait()
        await pilot.pause()

        assert opened == [str(location)]
        assert viewer.location is None
        assert viewer.history.locations == []


@pytest.fixture
def markdown_server() -> Iterator[URL]:
    """Serve UTF-8 Markdown and redirects over a real local HTTP connection."""

    class MarkdownHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/redirect.md":
                self.send_response(302)
                self.send_header("Location", "/docs/README.md")
                self.end_headers()
                return

            documents = {
                "/docs/README.md": "# 远程文档\n\n[Next](Next.md)\n",
                "/docs/Next.md": "# 下一页\n\n真实 HTTP 中文响应。\n",
            }
            content = documents.get(self.path)
            if content is None:
                self.send_error(404)
                return

            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), MarkdownHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield URL(f"http://127.0.0.1:{server.server_port}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


async def test_http_redirect_and_relative_link(markdown_server: URL) -> None:
    app = MarkdownViewer(Namespace(file=[]))

    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.screen.query_one(Viewer)
        viewer.visit(markdown_server.join("/redirect.md"), remember=False)
        for worker in list(app.workers):
            if isinstance(worker.node, Viewer):
                await worker.wait()
        await pilot.pause()

        assert viewer.location == markdown_server.join("/docs/README.md")
        assert "远程文档" in viewer.document.source
        assert viewer.history.locations == []

        viewer.document.post_message(Markdown.LinkClicked(viewer.document, "Next.md"))
        await pilot.pause()
        for worker in list(app.workers):
            if isinstance(worker.node, Viewer):
                await worker.wait()
        await pilot.pause()

        assert viewer.location == markdown_server.join("/docs/Next.md")
        assert "真实 HTTP 中文响应。" in viewer.document.source
        assert viewer.history.locations == [markdown_server.join("/docs/Next.md")]
