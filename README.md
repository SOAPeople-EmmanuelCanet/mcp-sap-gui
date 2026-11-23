# MCP SAP GUI Server

<!-- mcp-name: io.github.kts982/mcp-sap-gui -->

[![CI](https://github.com/kts982/mcp-sap-gui/actions/workflows/ci.yml/badge.svg)](https://github.com/kts982/mcp-sap-gui/actions/workflows/ci.yml)
[![Docs](https://github.com/kts982/mcp-sap-gui/actions/workflows/docs.yml/badge.svg)](https://github.com/kts982/mcp-sap-gui/actions/workflows/docs.yml)
[![Release](https://img.shields.io/github/v/release/kts982/mcp-sap-gui)](https://github.com/kts982/mcp-sap-gui/releases)

An [MCP](https://modelcontextprotocol.io/) server that lets AI assistants work in **SAP GUI for Windows**: ask in plain language, and the assistant reads screens and tables, fills in fields, runs transactions and handles popups, through SAP's own Scripting API. The source checkout defaults to read-only access; writes require startup opt-in, and every attachment and potentially mutating action requires approval ([what asks](https://github.com/kts982/mcp-sap-gui/blob/master/docs/CONFIRMATIONS.md)).

It works with any MCP client that can start a local server: Claude Code, GitHub Copilot, Codex, Google Antigravity and others.

<img src="https://raw.githubusercontent.com/kts982/mcp-sap-gui/master/docs/images/sap-preview-card.png" alt="sap_preview card in VS Code Copilot Chat: the SAP screen and the values about to be written" width="640">

## What it does

- **Looks things up:** inspect the current screen, fields, ALV grids, table controls, classic report lists and trees. Scrolling and navigation require write access and approval.
- **Fills in and changes:** fields, checkboxes, dropdowns, whole forms, table cells, F4 value help, table maintenance and IMG activities.
- **Navigates:** transactions, buttons, function keys, menus, tabs, SPRO and other trees.
- **Handles popups**, recognising questions, warnings, F4 lists and SAP messages in any logon language.
- **Shows before it saves:** a preview of the screen and the values about to be written, and screenshots on request.

More, with example prompts: [What it can do](https://github.com/kts982/mcp-sap-gui/blob/master/docs/OVERVIEW.md).

## Requirements

- Windows with SAP GUI for Windows (8.10 verified, 8.00 works; [SAP GUI versions](https://github.com/kts982/mcp-sap-gui/blob/master/docs/SAP_GUI_VERSIONS.md)), and SAP Logon running.
- SAP GUI Scripting allowed in SAP GUI and on the SAP system: [Preparing SAP](https://github.com/kts982/mcp-sap-gui/blob/master/docs/SAP_SETUP.md).
- [uv](https://docs.astral.sh/uv/), which runs the server from PyPI.
- An MCP client that shows the server's confirmation questions, including the initial attachment (listed below).

## Quick start

1. Install uv: `winget install --id=astral-sh.uv -e`
2. Add the server to your MCP client:

   ```text
   Command:   uvx
   Arguments: mcp-sap-gui[screenshots]
   Transport: stdio
   ```

   In the Claude Code CLI, for example: `claude mcp add sap-gui --scope user -- uvx "mcp-sap-gui[screenshots]"`. Every client: [Clients](https://github.com/kts982/mcp-sap-gui/blob/master/docs/CLIENTS.md).
3. Log on to SAP in SAP Logon, then ask: *"Connect to my open SAP session and tell me what system I'm on."*

Step by step, including updating to a new release: [Getting started](https://github.com/kts982/mcp-sap-gui/blob/master/docs/GETTING_STARTED.md).

## Safety

- **Read-only by default:** only `--enable-writes` at startup permits changes.
- **Every attachment and potentially mutating action requires approval**, including named sessions, menus, keys and toolbar actions: [Confirmations](https://github.com/kts982/mcp-sap-gui/blob/master/docs/CONFIRMATIONS.md).
- **A transaction policy** decides which transactions the assistant may start; read-only mode and profiles limit it further.
- **An audit log** records every call, question and answer.
- **Everything runs as the logged-on SAP user**, under that user's authorizations, which remain the real boundary.

Details for admins, Basis and security teams: [Security guide](https://github.com/kts982/mcp-sap-gui/blob/master/docs/SECURITY_GUIDE.md).

## Security changes and migration (unreleased)

These changes describe the unreleased source checkout; check your installed release before relying on them. From the repository root, start with read-only access:

```powershell
uv run python -m mcp_sap_gui.server
```

To permit writes, explicitly change the MCP client's startup arguments and restart the server:

```powershell
uv run python -m mcp_sap_gui.server --enable-writes
```

`--read-only` remains an explicit alias for the default and cannot be combined with `--enable-writes`. No tool call can enable writes. Enabling writes does **not** disable approval prompts. The `attach`, `all_writes` and `save` confirmation points are mandatory and cannot be removed by the assistant or through `sap_set_confirmation_points`.

| Area | New behavior |
|---|---|
| Session selection | `sap_connect_existing` always shows an approval picker, even for one named or indexed session. It identifies the actual system, client, SAP user and requested access level. No usable dialog means no attachment. |
| Session identity | Approval records the system, client, user, GUI session ID, backend `SystemSessionId` and session number. Identity is rechecked on session access. Closure, replacement, missing identity or a new logon invalidates authorization and requires reattachment. |
| Action approval | Approval is tied to the tool, arguments, session binding and screen fingerprint: active window, transaction, program, screen number and title. The target is checked again in the same COM job as execution. Approval cannot be reused for another action. |
| Write coverage | Buttons, menus, keys, toolbar actions, double-clicks, field writes, selections, scrolling and popup responses require approval when writes are enabled. This does not depend on recognizing a Save label. |
| Save and popup actions | The existing Save and save-risk popup checks remain in addition to mandatory action approval. F11 and the standard Save button therefore prompt twice. |
| Table and list reads | `sap_read_table` does not scroll by default. Set `allow_scroll=true` to request approved scrolling with writes enabled. `sap_read_list(scroll_to=...)` also requires write access and approval. |
| Opening a connection | `sap_connect` requires writes enabled and approval to open/log on. It then detaches and returns `binding_pending`; use `sap_connect_existing` to approve access to the actual session. |
| New SAP windows | A window opened with `/o` is not automatically adopted. Attach to it explicitly and approve the new binding. |
| Disconnect and shutdown | Revoke/detach only; leave SAP windows open. Close them manually in SAP GUI. `--detach-on-exit` remains a compatibility flag. |

Optional `--confirm field_writes transactions` settings still select named approval categories. Removing an optional category cannot remove the mandatory `all_writes` gate. A declined, unsupported, stale or unverifiable approval prevents the action.

The screen fingerprint detects a changed target; it is not a database transaction lock or a complete comparison of every field value. SAP authorizations and business validations remain necessary. This change does not implement the separate screenshot destination restriction reported in the security review.

### Production detection: follow-up design

**Automatic production blocking is not implemented in this change.** Read-only access and approval requirements apply to every system; they do not classify it as production or nonproduction.

SAP maintains the client role in **SCC4**, stored in `T000-CCCATEGORY` (`P` for Production). This classifies a **client**, not necessarily every client in a system. SAP's documented `GuiSessionInfo` properties expose identity information but no production-role property. A system name, SAP Logon description, window title or GUI colour is not a reliable production indicator. See [SAP client roles](https://learning.sap.com/courses/technical-implementation-and-operation-ii-of-sap-s-4hana-and-sap-business-suite/client-concept-1) and the [SAP GUI Scripting API](https://help.sap.com/doc/9215986e54174174854b0af6bb14305a/800.06/en-US/sap_gui_scripting_api.pdf).

The proposed follow-up is a narrow, authenticated backend lookup that returns the actual system, client and configured client role. Its endpoint and credentials must come from trusted startup configuration, not tool arguments or SAP screen content. Match its response to the GUI session identity; block production, missing/unknown roles, lookup failures and identity mismatches. Only metadata needed for classification should be read before the decision; business reads, screenshots and writes must remain blocked. If policy forbids **all clients** on a production system, supplement the client role with an administrator-maintained system classification.

Until that integration exists, use a dedicated account with minimal SAP authorizations and restrict scripting on production through SAP administration. Client-role configuration must itself be maintained correctly; it is not proof that a system contains no production data.

## Which clients show the confirmation questions

Tested on 2026-10-28: the **Claude Code CLI**, the **GitHub Copilot CLI**, **VS Code with GitHub Copilot** and the **Codex CLI** show them. The **Claude desktop app** does not (its Code tab declines without showing anything, its Chat and Cowork tabs do not support them), so the unreleased changes also refuse attachment there, including for read-only work. The full table: [Clients](https://github.com/kts982/mcp-sap-gui/blob/master/docs/CLIENTS.md#which-clients-show-the-confirmation-questions).

## Documentation

| Page | For |
|---|---|
| [Getting started](https://github.com/kts982/mcp-sap-gui/blob/master/docs/GETTING_STARTED.md) | Installing it and the first questions |
| [What it can do](https://github.com/kts982/mcp-sap-gui/blob/master/docs/OVERVIEW.md) | What to ask, and what is covered |
| [Clients](https://github.com/kts982/mcp-sap-gui/blob/master/docs/CLIENTS.md) | Setup per MCP client, and which ones show the confirmation questions |
| [Confirmations](https://github.com/kts982/mcp-sap-gui/blob/master/docs/CONFIRMATIONS.md) | What asks, and what each answer does |
| [Troubleshooting](https://github.com/kts982/mcp-sap-gui/blob/master/docs/TROUBLESHOOTING.md) | When something does not work |
| [Preparing SAP](https://github.com/kts982/mcp-sap-gui/blob/master/docs/SAP_SETUP.md) | Enabling scripting, also for named users or read-only; SAP Business Client |
| [Configuration](https://github.com/kts982/mcp-sap-gui/blob/master/docs/CONFIGURATION.md) | Every option and environment variable; profiles, HTTP, code mode |
| [Security guide](https://github.com/kts982/mcp-sap-gui/blob/master/docs/SECURITY_GUIDE.md) | Safeguards, the transaction policy, the audit log, a recommended setup |
| [SAP GUI versions](https://github.com/kts982/mcp-sap-gui/blob/master/docs/SAP_GUI_VERSIONS.md) | Which SAP GUI releases work, and how |
| [Tools](https://github.com/kts982/mcp-sap-gui/blob/master/docs/TOOLS.md) | Every tool the assistant can call |
| [CHANGELOG](https://github.com/kts982/mcp-sap-gui/blob/master/CHANGELOG.md) | What changed in each release |

## What's new

**0.6.1** sends a save only to the screen you approved it for: if the screen, the system or the SAP session changed while the question was open, nothing is saved. Reads say more: the buttons on a screen, the title and selection of an ALV grid, and the columns or cells a table read could not return. Tree double-clicks now work in SE19 and in view clusters, and an updated `opentelemetry-api` closes a slowdown that a crafted request could cause. Every change: [CHANGELOG](https://github.com/kts982/mcp-sap-gui/blob/master/CHANGELOG.md).

## Contributing

Bug reports and pull requests are welcome: [CONTRIBUTING](https://github.com/kts982/mcp-sap-gui/blob/master/CONTRIBUTING.md). Security issues: [SECURITY](https://github.com/kts982/mcp-sap-gui/blob/master/SECURITY.md).

## License

MIT. See [LICENSE](https://github.com/kts982/mcp-sap-gui/blob/master/LICENSE).

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by SAP SE. SAP, SAP GUI, and other SAP products mentioned are trademarks of SAP SE.

Use of this software with SAP systems should comply with your SAP licensing agreement and your organization's security policies.
