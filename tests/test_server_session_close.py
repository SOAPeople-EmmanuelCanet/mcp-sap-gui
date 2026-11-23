"""Server side of session ownership: sap_disconnect and shutdown."""

import asyncio
from types import SimpleNamespace

import pytest
from fastmcp import Client

from mcp_sap_gui import server
from mcp_sap_gui.session_manager import ManagedSession, SessionManager


class FakeController:
    def __init__(self, owned: int) -> None:
        self.is_connected = True
        self._owns_session = owned > 0
        self._owned_sessions = [object()] * owned
        self.scripting_read_only = False
        self.calls: list[bool] = []

    def disconnect(self, close_owned: bool = True) -> list:
        self.calls.append(close_owned)
        return ["/app/con[1]/ses[0]"] if close_owned and self._owned_sessions else []


@pytest.fixture
def bound(monkeypatch):
    """A server with one MCP session bound to an owned SAP session."""
    manager = SessionManager()
    monkeypatch.setattr(server, "_session_mgr", manager)
    monkeypatch.setattr(server, "config", server.ServerConfig())
    ctx = SimpleNamespace(session=object(), session_id="chat-1")
    controller = FakeController(owned=1)
    manager._sessions[server._session_key(ctx)] = ManagedSession(controller=controller)
    yield SimpleNamespace(manager=manager, ctx=ctx, controller=controller)
    manager.shutdown()


def _tool(name: str):
    return asyncio.run(server.mcp.get_tool(name))


def test_disconnect_is_read_only_and_stays_visible():
    tool = _tool("sap_disconnect")
    assert tool.tags == {"read"}
    assert tool.annotations.read_only_hint is True
    assert tool.annotations.destructive_hint is False


def test_connect_is_not_read_only():
    tool = _tool("sap_connect")
    assert tool.tags == {"write"}
    assert tool.annotations.read_only_hint is False
    assert tool.annotations.destructive_hint is False


def test_disconnect_leaves_owned_sessions_open(bound):
    result = asyncio.run(server.sap_disconnect(bound.ctx))
    assert result["action"] == "detached"
    assert "closed_sessions" not in result
    assert bound.controller.calls == [False]


@pytest.mark.parametrize("floor", ["exploration", "operator"])
def test_disconnect_does_not_depend_on_the_profile(bound, monkeypatch, floor):
    # Closing by profile belongs to the per-system modes planned for 0.6;
    # until then a profile hides tools but does not change what is closed.
    monkeypatch.setattr(server, "config", server.ServerConfig(profile=floor))
    asyncio.run(server.sap_disconnect(bound.ctx))
    assert bound.controller.calls == [False]


def _shutdown_close_owned(monkeypatch, config) -> list:
    """Run the server's lifespan once and return what release_all was given."""
    calls = []
    monkeypatch.setattr(server, "config", config)
    monkeypatch.setattr(
        SessionManager, "release_all",
        lambda self, close_owned=True: calls.append(close_owned),
    )

    async def run():
        async with Client(server.mcp):
            pass

    asyncio.run(run())
    return calls


def test_shutdown_detaches_by_default(monkeypatch):
    assert _shutdown_close_owned(monkeypatch, server.ServerConfig()) == [False]


def test_shutdown_with_detach_on_exit_closes_nothing(monkeypatch):
    config = server.ServerConfig(detach_on_exit=True)
    assert _shutdown_close_owned(monkeypatch, config) == [False]
