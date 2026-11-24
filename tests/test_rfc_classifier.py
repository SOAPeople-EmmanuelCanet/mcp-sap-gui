"""Fail-closed client-role checks through standard RFC_READ_TABLE."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from mcp_sap_gui import server
from mcp_sap_gui.models import SAPGUIError
from mcp_sap_gui.rfc_classifier import (
    RfcClientClassifier,
    parse_rfc_route,
    parse_rfc_routes,
)
from mcp_sap_gui.safety import WRITE_APPROVAL, WriteApproval, binding_identity
from mcp_sap_gui.sap_controller import SAPGUIController
from mcp_sap_gui.session_manager import SessionManager
from tests.test_security_defaults import session

ROUTE = ("DEV", "100", "00", "dev.example.invalid")


class FakeConnection:
    def __init__(self, role="T", attributes=None, rows=None, during_call=None):
        self.attributes = attributes or {
            "sysId": "DEV", "client": "100", "sysNumber": "00",
            "partnerHost": "DEV.EXAMPLE.INVALID",
        }
        self.rows = rows if rows is not None else [{"WA": f"100|{role}"}]
        self.during_call = during_call
        self.closed = False
        self.calls = []

    def get_connection_attributes(self):
        return self.attributes

    def call(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if self.during_call:
            self.during_call()
        return {"DATA": self.rows}

    def close(self):
        self.closed = True


def gui_session():
    result = session()
    result.Info.ApplicationServer = "dev.example.invalid"
    return result


def classifier(connection):
    factory = MagicMock(return_value=connection)
    return RfcClientClassifier({ROUTE: "MCP_DEV_100"}, factory), factory


@pytest.mark.parametrize("value", [
    "DEV/100/00/dev.example.invalid=MCP_DEV_100",
    "dev/100/00/dev.example.invalid=MCP_DEV_100",
])
def test_route_parser(value):
    assert parse_rfc_route(value) == (ROUTE, "MCP_DEV_100")


@pytest.mark.parametrize("value", [
    "DEV/100=DEST", "DEV/100/0/host=DEST", "DEV/10A/00/host=DEST",
    "DEV/100/00/host", "DEV/100/00/host=bad dest", "*/100/00/host=DEST",
])
def test_invalid_route_fails_startup(value):
    with pytest.raises(ValueError):
        parse_rfc_route(value)


def test_duplicate_route_fails_startup():
    with pytest.raises(ValueError, match="duplicate"):
        parse_rfc_routes([
            "DEV/100/00/dev.example.invalid=ONE",
            "DEV/100/00/DEV.EXAMPLE.INVALID=TWO",
        ])


def test_startup_route_is_not_tool_controlled(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["zz-mcp-sap-gui", "--rfc-destination",
         "DEV/100/00/dev.example.invalid=MCP_DEV_100"],
    )
    monkeypatch.setattr(server, "load_dotenv", lambda: None)
    monkeypatch.setattr(server, "config", server.ServerConfig())
    monkeypatch.setattr(server, "resolve_policy_file", lambda _: None)
    monkeypatch.setattr(server.mcp, "run", lambda: None)
    server.main()
    assert server.config.rfc_routes == {ROUTE: "MCP_DEV_100"}


@pytest.mark.parametrize("role", ["T", "C"])
def test_safe_role_is_checked_with_fixed_query(role):
    connection = FakeConnection(role=role)
    guard, factory = classifier(connection)
    result = guard.check(gui_session())
    assert result["client_role"] == role
    factory.assert_called_once_with(dest="MCP_DEV_100")
    assert connection.calls == [("RFC_READ_TABLE", {
        "QUERY_TABLE": "T000", "DELIMITER": "|",
        "FIELDS": [{"FIELDNAME": "MANDT"}, {"FIELDNAME": "CCCATEGORY"}],
        "OPTIONS": [{"TEXT": "MANDT = '100'"}], "ROWCOUNT": 2,
    })]
    assert connection.closed


@pytest.mark.parametrize("role", ["P", "D", "E", "S", "", "X"])
def test_production_and_nonapproved_roles_are_blocked(role):
    connection = FakeConnection(role=role)
    guard, _ = classifier(connection)
    with pytest.raises(SAPGUIError, match="Access denied"):
        guard.check(gui_session())
    assert connection.closed


@pytest.mark.parametrize("rows", [[], [{"WA": "100|T"}, {"WA": "100|T"}],
                                      [{"WA": "200|T"}], [{"WA": "100"}], [{}]])
def test_missing_ambiguous_or_mismatched_rows_are_blocked(rows):
    connection = FakeConnection(rows=rows)
    guard, _ = classifier(connection)
    with pytest.raises(SAPGUIError):
        guard.check(gui_session())


@pytest.mark.parametrize("field,value", [
    ("sysId", "QAS"), ("client", "200"), ("sysNumber", "01"),
    ("partnerHost", "other.example.invalid"),
])
def test_rfc_identity_must_match_gui(field, value):
    attributes = FakeConnection().attributes.copy()
    attributes[field] = value
    connection = FakeConnection(attributes=attributes)
    guard, _ = classifier(connection)
    with pytest.raises(SAPGUIError, match="does not match"):
        guard.check(gui_session())
    assert connection.calls == []


def test_missing_route_and_connection_error_fail_closed():
    with pytest.raises(SAPGUIError, match="No RFC classification route"):
        RfcClientClassifier({}).check(gui_session())
    guard = RfcClientClassifier({ROUTE: "DEST"}, MagicMock(side_effect=RuntimeError("offline")))
    with pytest.raises(SAPGUIError, match="classification failed"):
        guard.check(gui_session())


def test_gui_backend_change_during_rfc_is_blocked():
    gui = gui_session()
    connection = FakeConnection(during_call=lambda: setattr(gui.Info, "Client", "200"))
    guard, _ = classifier(connection)
    with pytest.raises(SAPGUIError, match="changed during"):
        guard.check(gui)


def test_manager_installs_guard_and_rechecks_every_access():
    connection = FakeConnection()
    guard, factory = classifier(connection)
    manager = SessionManager(guard)
    controller = manager.get_or_create("test").controller
    controller._session = gui_session()
    controller.approve_binding(binding_identity(controller._session))
    controller.get_session_info()
    controller.get_session_info()
    assert factory.call_count == 3  # attachment plus each user-facing read
    manager.executor.shutdown()


@pytest.mark.parametrize("role,allowed", [("T", True), ("P", False)])
def test_discovery_classifies_before_reading_screen_details(role, allowed):
    gui = gui_session()
    gui.findById = MagicMock(return_value=SimpleNamespace(Text="User profile"))
    children = MagicMock(return_value=gui)
    children.Count = 1
    connection = SimpleNamespace(Children=children, Description="DEV", Id="/app/con[0]")
    guard, _ = classifier(FakeConnection(role=role))
    controller = SAPGUIController()
    controller.client_classifier = guard
    controller._discover_connections = lambda: [("saplogon", "SAPGUI", None, connection)]
    controller._is_scripting_disabled = lambda conn: False
    result = controller.list_connections()[0]["sessions"][0]
    assert result["client_role_allowed"] is allowed
    if allowed:
        assert result["transaction"] == "SU3"
        gui.findById.assert_called_once()
    else:
        assert "transaction" not in result and "title" not in result
        gui.findById.assert_not_called()


def test_changed_role_revokes_binding():
    connections = [FakeConnection(role="T"), FakeConnection(role="P")]
    guard = RfcClientClassifier({ROUTE: "DEST"}, lambda **kwargs: connections.pop(0))
    controller = SAPGUIController()
    controller.require_binding_approval = True
    controller.client_classifier = guard
    controller._session = gui_session()
    controller.approve_binding(binding_identity(controller._session))
    with pytest.raises(SAPGUIError, match="authorization failed"):
        controller.get_session_info()
    assert controller._approved_identity is None
    assert controller._approved_classification is None


async def test_role_is_rechecked_in_same_job_immediately_before_write(monkeypatch):
    connections = [FakeConnection(role="T"), FakeConnection(role="T"),
                   FakeConnection(role="P")]
    guard = RfcClientClassifier({ROUTE: "DEST"}, lambda **kwargs: connections.pop(0))
    controller = SAPGUIController()
    controller.require_binding_approval = True
    controller.client_classifier = guard
    controller._session = gui_session()
    controller.approve_binding(binding_identity(controller._session))
    target = controller.action_target()
    action = MagicMock()

    async def inline(fn):
        return fn()

    monkeypatch.setattr(server, "_com", inline)
    token = WRITE_APPROVAL.set(WriteApproval(controller, target))
    try:
        with pytest.raises(SAPGUIError, match="Production"):
            await server._com_write(controller, action)
    finally:
        WRITE_APPROVAL.reset(token)
    action.assert_not_called()


async def test_sap_connect_is_disabled_before_controller_access(monkeypatch):
    monkeypatch.setattr(server, "_ctrl", MagicMock(side_effect=AssertionError("must not run")))
    with pytest.raises(Exception, match="disabled"):
        await server.sap_connect(system_description="DEV", ctx=MagicMock())
