# Confirmations

Read-only is the default. Every attachment requires approval, and every potentially mutating action requires approval when writes are enabled at startup with `--enable-writes`. The server asks the question itself, through your MCP client, and decides on your answer: what the assistant does or says cannot get past it.

## What asks

**A save asks.** This cannot be switched off. It covers the standard ways to save:

- `F11` / the Save key, and the Save button in the toolbar (`wnd[0]/tbar[0]/btn[11]`);
- on a popup: a Save button, Yes or OK on a popup about saving, and any answer except Cancel to a popup whose question the server cannot read (SAP shows some questions in a browser control that scripting cannot read: the question then tells you to check the SAP window).

**`attach`, `all_writes` and `save` are mandatory and cannot be disabled.** Optional named categories can be selected in the chat (*"ask me before every field write"*), or for every chat with the `--confirm` option:

| Point | What asks |
|---|---|
| `transactions` | Starting a transaction (`sap_execute_transaction`) |
| `batch_fields` | Filling several fields at once (`sap_set_batch_fields`) |
| `field_writes` | Each single write: a field, a table cell, a text editor, a checkbox, a radio button, a dropdown |
| `all_writes` | Always on: every action that can change something, including selecting, scrolling and navigation. A save asks twice, once for the point and once for the save |
| `attach` | Attaching to an allowed SAP session: RFC classification runs first, then you pick from the sessions that passed (system, session number, client, user, transaction, window title). Required even when the assistant names one session or supplies indexes; the question states the requested access level |

## What a question looks like

The server's text says what is about to happen and where (*"You are about to send 'F11' which triggers Save (F11) in SAP. [...] It goes to screen 'Maintain User Profile (SU3, SAPLSUU5, 100)' on system DEV/100."*), and the answer is labelled with what a yes does: *Yes, save*, *Yes, run it*, *Yes, press 'No'*. Each client draws it its own way: a checkbox and Accept (Claude Code CLI), Yes / No (GitHub Copilot CLI), True / False and Submit (VS Code, Codex). Only a yes goes ahead; anything else, including closing the question, is a no.

## After you answer

- **Yes:** the action runs, and its result carries `confirmed_by_user: true`, so the assistant, which never sees the question, knows that you approved it.
- **No:** nothing is done. The assistant gets an error that says you declined, and the server's rules tell it not to retry the call or reach the same result another way, but to tell you and wait for your next instruction.

Three more rules protect the answer:

- **An answer that comes back faster than a person can give one** (under 250 ms) came from the client, not from you. A no still counts, and the error says that no person saw the question; a yes is refused.
- **An answer counts only for what the question showed.** Every action is bound to its tool, arguments, approved session binding and screen fingerprint: right before it sends the save, the server reads the screen, system, client, user and SAP session again, and if any of them changed while the question was open (you moved on in SAP GUI, a popup opened), nothing is saved and the result says `action: changed`. On MCP 2026-07-28 the server also reads SAP again when your answer arrives, for a popup and the list of sessions too. The assistant then reads the screen again and asks again if still needed.
- **An answer counts once.** It cannot be replayed to repeat the action.

## Clients that cannot show the questions

The question has to reach you. Some clients never show it: the Claude desktop app declines at once without showing anything, and its Chat and Cowork tabs do not support the questions at all ([Clients](CLIENTS.md) has the list). There, attachment and every mutating action are refused, and the refusal tells the assistant to tell you and to use a client that shows the questions. A confirmation point cannot be switched off there either, since switching it off asks too.

## Switching points on and off

- **In the chat:** optional categories only; `attach`, `all_writes` and `save` stay on. Ask the assistant, which calls `sap_set_confirmation_points`. Adding a point takes effect at once. Removing one asks you first, and if you say no, it stays.
- **For every chat:** start the server with `--confirm`, for example `--confirm field_writes transactions`. These points cannot be removed in a chat.
- Points belong to the chat (the MCP session), not to the SAP connection: they stay after `sap_disconnect` and a later reconnect.

## See it before it happens

Ask the assistant to *"show me the values first"*: `sap_preview` shows the current screen, the session and the values about to be written, without writing anything. Most clients get a written summary and a screenshot; VS Code shows a card. A preview is no approval: the save still asks.

## In the audit log

With `--audit-log`, every question and answer gets a `confirmation` line: the point, the tool, the outcome (`asked`, `accepted`, `declined`, `changed`, `replayed`, `unsolicited_answer`, `invalid_answer`, `unsupported_client`), and `elapsed_ms`, how long the answer took. An answer faster than a person also has `no_dialog: true`, and a refused yes `client_answer: "accept"`. The other audit lines: [Security guide](SECURITY_GUIDE.md#audit-log).

## Known gaps

Menu items, application buttons, toolbar functions, double-clicks, keys and command-field writes all pass the mandatory action gate. Their labels do not have to identify them as Save. Save recognition remains an additional check for standard saves and risky popup responses.

Identity is rechecked on session access. Missing identity or a changed logon/session revokes authorization; even a return to the old identity requires a new attachment approval. The action fingerprint contains the active window, transaction, program, screen number and title. It does not compare every field value or lock a database transaction.

Table reads do not scroll by default. Request `allow_scroll=true` with writes enabled to approve scrolling. Classic-list `scroll_to` is also a mutating action. Read forms of popup and tree-child tools remain available without write approval.

With experimental `--code-mode`, a script cannot ask a question on MCP 2026-07-28: attachment or write actions that need one are refused inside the script, and the assistant must call the tool directly. The SAP user's authorizations remain the boundary for what can change.
