"""Security boundaries through the MCP dispatcher and the real controller guards."""

import copy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult

from mcp_sap_gui import server
from mcp_sap_gui.models import SAPGUIError
from mcp_sap_gui.safety import WRITE_APPROVAL, WriteApproval, binding_identity
from mcp_sap_gui.sap_controller import SAPGUIController


async def accept(message, response_type, params, context):
    return ElicitResult(action="accept", content=response_type(value=True))


def session():
    info = SimpleNamespace(
        SystemName="DEV", Client="100", User="TESTUSER", SystemSessionId="test-logon",
        SessionNumber=1, SystemNumber="00", Language="EN", Transaction="SU3",
        Program="SAPLSUU5", ScreenNumber=100,
    )
    window = SimpleNamespace(Id="/app/con[0]/ses[0]/wnd[0]", Text="User profile")
    return SimpleNamespace(Info=info, Id="/app/con[0]/ses[0]", Busy=False,
                           ActiveWindow=window, findById=lambda _: window)


@pytest.fixture
def bound(monkeypatch):
    c = SAPGUIController()
    c._session = session()
    c.require_binding_approval = True
    c.approve_binding(binding_identity(c._session))
    monkeypatch.setattr(server, "_ctrl", lambda ctx: c)
    monkeypatch.setattr(server, "config", server.ServerConfig(read_only=False))

    async def inline(fn):
        return fn()

    monkeypatch.setattr(server, "_com", inline)
    return c


def test_default_is_read_only():
    assert server.ServerConfig().read_only is True


def test_exploration_cannot_enable_writes():
    assert server.ServerConfig(profile="exploration", read_only=False).read_only is True


@pytest.mark.parametrize("argv,readonly", [([], True), (["--read-only"], True),
                                         (["--enable-writes"], False)])
def test_startup_access_is_explicit(monkeypatch, argv, readonly):
    monkeypatch.setattr("sys.argv", ["zz-mcp-sap-gui", *argv])
    monkeypatch.setattr(server, "config", server.ServerConfig())
    monkeypatch.setattr(server, "load_dotenv", lambda: None)
    monkeypatch.setattr(server, "resolve_policy_file", lambda _: None)
    monkeypatch.setattr(server.mcp, "run", lambda: None)
    server.main()
    assert server.config.read_only is readonly


async def test_default_blocks_writes_without_prompt(bound, monkeypatch):
    monkeypatch.setattr(server, "config", server.ServerConfig())
    bound.select_menu = MagicMock()
    prompts = []

    async def handler(*args):
        prompts.append(args)
        return await accept(*args)

    async with Client(server.mcp, elicitation_handler=handler) as client:
        result = await client.call_tool("sap_select_menu", {"menu_id": "wnd[0]/mbar/menu[0]"},
                                        raise_on_error=False)
    assert result.is_error
    assert not prompts
    bound.select_menu.assert_not_called()


@pytest.mark.parametrize("tool,args,method", [
    ("sap_select_menu", {"menu_id": "wnd[0]/mbar/menu[0]"}, "select_menu"),
    ("sap_press_button", {"button_id": "wnd[0]/tbar[1]/btn[8]"}, "press_button"),
    ("sap_send_key", {"key": "Enter"}, "send_vkey"),
    ("sap_press_alv_toolbar_button", {"grid_id": "g", "button_id": "POST"},
     "press_alv_toolbar_button"),
    ("sap_double_click_tree_node", {"tree_id": "t", "node_key": "1"},
     "double_click_tree_node"),
    ("sap_double_click_cell", {"table_id": "t", "row": 0, "column": "C"},
     "double_click_table_cell"),
    ("sap_read_list", {"scroll_to": 20}, "read_list"),
    ("sap_read_table", {"table_id": "t", "allow_scroll": True}, "read_table"),
    ("sap_handle_popup", {"action": "auto"}, "apply_popup_plan"),
])
async def test_every_action_asks_and_decline_sends_nothing(bound, tool, args, method):
    operation = MagicMock(return_value={"status": "ok"})
    setattr(bound, method, operation)
    prompts = []

    async def decline(message, *args):
        prompts.append(message)
        return ElicitResult(action="decline")

    async with Client(server.mcp, elicitation_handler=decline) as client:
        result = await client.call_tool(tool, args, raise_on_error=False)
    assert result.is_error
    assert len(prompts) == 1
    assert "DEV / 100 / TESTUSER" in prompts[0]
    assert tool in prompts[0] and "Screen:" in prompts[0]
    operation.assert_not_called()


async def test_approved_action_executes_once(bound):
    bound.select_menu = MagicMock(return_value={"status": "ok"})
    async with Client(server.mcp, elicitation_handler=accept) as client:
        result = await client.call_tool("sap_select_menu", {"menu_id": "wnd[0]/mbar/menu[0]"})
    assert result.structured_content["confirmed_by_user"]
    bound.select_menu.assert_called_once()


@pytest.mark.parametrize("change", ["screen", "user", "logon", "replacement", "reapproval"])
async def test_changed_target_after_question_executes_nothing(bound, change):
    bound.select_menu = MagicMock(return_value={"status": "ok"})

    async def handler(*args):
        if change == "screen":
            bound._session.Info.ScreenNumber = 200
        elif change == "user":
            bound._session.Info.User = "OTHERUSER"
        elif change == "logon":
            bound._session.Info.SystemSessionId = "new-logon"
        elif change == "replacement":
            bound._session = session()
        else:
            bound.approve_binding(binding_identity(bound._session))
        return await accept(*args)

    async with Client(server.mcp, elicitation_handler=handler) as client:
        result = await client.call_tool("sap_select_menu", {"menu_id": "wnd[0]/mbar/menu[0]"},
                                        raise_on_error=False)
    assert result.is_error
    bound.select_menu.assert_not_called()


async def test_recheck_occurs_in_job_that_executes_action(bound, monkeypatch):
    bound.select_menu = MagicMock()
    original = server._com

    async def interleave(fn):
        if getattr(fn, "__name__", "") == "checked":
            bound._session.Info.ScreenNumber = 200
        return await original(fn)

    monkeypatch.setattr(server, "_com", interleave)
    async with Client(server.mcp, elicitation_handler=accept) as client:
        result = await client.call_tool("sap_select_menu", {"menu_id": "wnd[0]/mbar/menu[0]"},
                                        raise_on_error=False)
    assert result.is_error
    bound.select_menu.assert_not_called()


@pytest.mark.parametrize("missing", ["SystemName", "Client", "User", "SystemSessionId",
                                    "SessionNumber"])
def test_missing_identity_revokes_and_cannot_recover_silently(bound, missing):
    previous = getattr(bound._session.Info, missing)
    setattr(bound._session.Info, missing, "")
    with pytest.raises(SAPGUIError):
        bound.get_session_info()
    setattr(bound._session.Info, missing, previous)
    with pytest.raises(SAPGUIError):
        bound.get_session_info()


def test_closed_session_loses_approval(bound):
    previous = bound._session
    bound._session = None
    with pytest.raises(SAPGUIError):
        bound.get_session_info()
    bound._session = previous
    with pytest.raises(SAPGUIError):
        bound.get_session_info()


async def test_client_without_dialog_cannot_write(bound):
    bound.select_menu = MagicMock()
    async with Client(server.mcp) as client:
        result = await client.call_tool("sap_select_menu", {"menu_id": "wnd[0]/mbar/menu[0]"},
                                        raise_on_error=False)
    assert result.is_error
    bound.select_menu.assert_not_called()


async def test_approval_is_single_use_and_not_inherited_by_next_call(bound):
    target = copy.deepcopy(bound.action_target())
    action = MagicMock()
    token = WRITE_APPROVAL.set(WriteApproval(bound, target))
    try:
        await server._com_write(bound, action)
        with pytest.raises(Exception, match="already used"):
            await server._com_write(bound, action)
    finally:
        WRITE_APPROVAL.reset(token)
    with pytest.raises(Exception, match="No user approval"):
        await server._com_write(bound, action)
    action.assert_called_once()


async def test_runtime_settings_cannot_disable_mandatory_gates(bound):
    async with Client(server.mcp) as client:
        result = await client.call_tool("sap_set_confirmation_points", {"points": []})
    assert set(result.structured_content["always_on"]) == {"save", "attach", "all_writes"}
    assert set(result.structured_content["active"]) == {"save", "attach", "all_writes"}
