"""Regression test: the confirmation gate must fire over a REAL stdio server.

Pins the ``python -m`` double-module trap found live: the middleware used to
``from . import server`` per call, which under ``python -m mcp_sap_gui.server``
(how .mcp.json, VS Code and the README all launch it) loads a SECOND copy of
server.py whose globals are empty (``_session_mgr = None``) — the gate then
read confirmation points from the phantom module and silently never fired.
In-memory clients share one module object, so only a subprocess over stdio
can catch this class of bug.

No SAP needed: replace the controller's target read with a complete fake.
The running __main__ must use --enable-writes and the configured floor;
a second module with default read-only globals would refuse before asking.
"""

import sys

import pytest
from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult
from fastmcp.client.transports import StdioTransport


async def test_confirmation_gate_fires_over_stdio():
    prompts: list[str] = []

    async def decline_handler(message, response_type, params, context):
        prompts.append(str(message))
        return ElicitResult(action="decline")

    script = """
import runpy
import sys
from mcp_sap_gui.controller import SAPGUIControllerBase
from tests.fakes import action_target
SAPGUIControllerBase._check_dependencies = lambda self: None
SAPGUIControllerBase.action_target = lambda self: action_target()
sys.argv = ["mcp-sap-gui", "--enable-writes"]
runpy.run_module("mcp_sap_gui.server", run_name="__main__")
"""
    transport = StdioTransport(command=sys.executable, args=["-c", script])
    async with Client(transport, elicitation_handler=decline_handler) as client:
        await client.call_tool(
            "sap_set_confirmation_points", {"points": ["field_writes"]}
        )
        with pytest.raises(Exception) as excinfo:
            await client.call_tool(
                "sap_set_field",
                {"field_id": "wnd[0]/tbar[0]/okcd", "value": ""},
            )

    assert len(prompts) == 1, "confirmation gate did not elicit over stdio"
    assert "field_writes" in prompts[0]
    text = str(excinfo.value)
    assert "declined by user" in text
    # The old bug's signature: the tool body ran and failed on SAP instead.
    assert "Not connected" not in text
