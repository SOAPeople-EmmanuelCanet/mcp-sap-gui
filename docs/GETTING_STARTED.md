# Getting started

This page takes you from nothing to a first answer from SAP in your AI assistant. It takes about ten minutes once SAP GUI Scripting is allowed.

## What you need

- **Windows** with **SAP GUI for Windows** installed, and SAP Logon running (or a session in SAP Business Client, experimental).
- **SAP GUI Scripting allowed**, in your SAP GUI options and on the SAP system. The second one is up to your Basis team: [Preparing SAP](SAP_SETUP.md) has what to ask for.
- **SAP RFC client-role classification configured by Basis**, including the SAP NW RFC SDK, a direct destination and narrow access to `T000`: [RFC client classification](RFC_CLIENT_CLASSIFICATION.md).
- **An AI assistant that supports MCP servers**, ideally one that shows the server's confirmation questions, so that you can approve a save. The Claude Code CLI, GitHub Copilot (CLI and VS Code) and the Codex CLI do; the Claude desktop app does not. Details per client: [Clients](CLIENTS.md).

## 1. Install uv

The server is published on PyPI, and `uvx` (part of [uv](https://docs.astral.sh/uv/)) downloads and runs it, with nothing to clone or install by hand. In PowerShell:

```powershell
winget install --id=astral-sh.uv -e
```

Without winget, use uv's own installer: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`. Open a new terminal afterwards so `uvx` is on the path.

## 2. Add the server to your assistant

Every client needs the same three things:

```text
Command:   uvx
Arguments: mcp-sap-gui[rfc,screenshots] --rfc-destination DEV/100/00/dev.example.invalid=MCP_DEV_100
Transport: stdio
```

Replace the example backend and destination with values supplied by Basis. The `[screenshots]` part makes screenshots 70-90% smaller. Where each client keeps this, with a ready-made snippet for each: [Clients](CLIENTS.md). For example, in the Claude Code CLI:

```powershell
claude mcp add sap-gui --scope user -- uvx "mcp-sap-gui[rfc,screenshots]" --rfc-destination "DEV/100/00/dev.example.invalid=MCP_DEV_100"
```

Restart the client (or reload its MCP servers) after adding the server.

## 3. Log on to SAP

Have Basis configure the mandatory [RFC client-role check](RFC_CLIENT_CLASSIFICATION.md). Open SAP Logon and log on as usual. `sap_connect` is disabled because the role cannot be verified before logon; your GUI password never passes through the assistant.

## 4. Ask something

```text
Connect to my open SAP session and tell me what system I'm on
Show me the current screen info
List all editable fields on this screen
Read the first 20 rows of the visible table
```

Approve the actual system, client, user and access level in the session picker. Even one matching session needs approval. If several SAP sessions are open, name the system: *"connect to my DEV session"*.

More ideas of what to ask: [What it can do](OVERVIEW.md).

## When the assistant wants to change something

The server defaults to read-only. To permit changes, add `--enable-writes` to its startup arguments and restart it. Every mutating action then asks for approval, including navigation, menus, keys, scrolling and popup responses. Standard Save actions retain an additional save question. The assistant cannot enable writes or disable these mandatory gates. See [Confirmations](CONFIRMATIONS.md) and [Configuration](CONFIGURATION.md).

## Updating to a new release

`uvx` keeps the version it downloaded first, so a new release is not picked up by itself. Run this once, then restart your assistant:

```powershell
uvx "mcp-sap-gui[screenshots]@latest" --help
```

To stay on one release instead, put the version in the client's arguments: `mcp-sap-gui[screenshots]==<version>`. What changed in each release: [CHANGELOG](../CHANGELOG.md).

## If something does not work

[Troubleshooting](TROUBLESHOOTING.md) covers the usual causes: SAP Logon not running, scripting not allowed, the tools not showing up in the client, an action that is blocked.
