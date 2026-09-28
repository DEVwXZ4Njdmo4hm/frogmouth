"""Regression tests for URL detection and forge lookups."""

import asyncio
from collections.abc import Callable

import pytest
from httpx import URL, AsyncClient, ConnectError, MockTransport, Request, Response

from frogmouth.utility import forge, is_likely_url
from frogmouth.utility.advertising import USER_AGENT


def install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[Request], Response],
) -> list[AsyncClient]:
    """Use a deterministic HTTP transport and retain clients to check closure."""
    clients: list[AsyncClient] = []

    def make_client() -> AsyncClient:
        client = AsyncClient(transport=MockTransport(handler))
        clients.append(client)
        return client

    monkeypatch.setattr(forge, "AsyncClient", make_client)
    return clients


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ("https://example.com/README.md", True),
        ("http://localhost:8080/doc.md", True),
        ("HTTPS://example.com/doc.md", True),
        ("README.md", False),
        ("/tmp/文档.md", False),
        ("ftp://example.com/doc.md", False),
        ("", False),
        ("http://example.com:not-a-port/doc.md", False),
        ("http://[not-an-ip]/doc.md", False),
        ("https://example.com/\x00", False),
    ],
)
def test_url_detection(candidate: str, expected: bool) -> None:
    """Treat malformed user input as a non-URL instead of crashing."""
    assert is_likely_url(candidate) is expected


def test_github_branch_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Try master after main is absent, preserving request metadata."""
    requests: list[Request] = []

    def respond(request: Request) -> Response:
        requests.append(request)
        status = 404 if "/main/" in request.url.path else 200
        return Response(status)

    clients = install_transport(monkeypatch, respond)
    result = asyncio.run(forge.build_raw_github_url("Owner", "Repo"))

    assert result == URL(
        "https://raw.githubusercontent.com/Owner/Repo/master/README.md"
    )
    assert len(requests) == 2
    assert all(request.method == "HEAD" for request in requests)
    assert all(request.headers["user-agent"] == USER_AGENT for request in requests)
    assert all(client.is_closed for client in clients)


def test_codeberg_explicit_location(monkeypatch: pytest.MonkeyPatch) -> None:
    """Request the valid Codeberg raw endpoint with the supplied branch and file."""
    requests: list[Request] = []

    def respond(request: Request) -> Response:
        requests.append(request)
        return Response(200)

    clients = install_transport(monkeypatch, respond)
    result = asyncio.run(
        forge.build_raw_codeberg_url("Owner", "Repo", "Feature", "docs/README.md")
    )

    expected = URL("https://codeberg.org/Owner/Repo/raw/branch/Feature/docs/README.md")
    assert result == expected
    assert [request.url for request in requests] == [expected]
    assert all(client.is_closed for client in clients)


def test_forge_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return no URL and close the client when connecting fails."""
    requests: list[Request] = []

    def respond(request: Request) -> Response:
        requests.append(request)
        raise ConnectError("Connection failed", request=request)

    clients = install_transport(monkeypatch, respond)
    assert asyncio.run(forge.build_raw_github_url("Owner", "Repo")) is None
    assert len(requests) == 1
    assert all(client.is_closed for client in clients)


def test_forge_missing_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return no URL when neither default branch contains the file."""
    requests: list[Request] = []

    def respond(request: Request) -> Response:
        requests.append(request)
        return Response(404)

    clients = install_transport(monkeypatch, respond)
    assert asyncio.run(forge.build_raw_github_url("Owner", "Repo")) is None
    assert len(requests) == 2
    assert all(client.is_closed for client in clients)
