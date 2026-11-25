# Blocking productive SAP clients with standard RFC

The unreleased server requires a fresh backend classification before it authorizes
an attachment and before every operation on an attached SAP session. It calls the
standard remote-enabled function `RFC_READ_TABLE` to read the selected client's
`T000-CCCATEGORY`. No custom ABAP code or transport is required.

Only the SCC4 roles `T` (Test) and `C` (Customizing) are accepted. Production (`P`),
Demo (`D`), Training/Education (`E`), SAP Reference (`S`), blank or unknown roles
are denied. Missing routes, unavailable RFC, authorization errors, malformed or
multiple rows, and identity mismatches also deny access. User approval cannot
override the result.

## Runtime and connection setup

Install the RFC extra and SAP NetWeaver RFC SDK. PyRFC requires the SDK libraries
to be available to the server process. The public PyRFC package is archived and its
3.3.1 release is yanked; this project exact-pins that version in the optional extra.
Organizations that cannot accept an archived connector must supply a maintained
compatible connector before using this feature.
The published Windows wheels cover CPython 3.11 and 3.12; run the RFC-enabled server
on one of those versions unless your organization builds and validates another target.

```text
Command:   uvx
Arguments: soa-mcp-sap-gui[rfc,screenshots] --rfc-destination DEV/100/00/dev.example.invalid=MCP_DEV_100
```

Create `sapnwrfc.ini` outside the assistant's workspace. Configure one **direct**
destination per GUI application server. The server passes only the destination name
to PyRFC; credentials, SNC and network settings stay in SAP's RFC configuration.
For example:

```ini
DEST=MCP_DEV_100
ASHOST=dev.example.invalid
SYSNR=00
CLIENT=100
USER=MCP_CLASSIFY
PASSWD=use-your-managed-secret-mechanism
LANG=EN
```

Use SNC where available and protect the file because the SDK's INI format can contain
credentials. Follow your SAP NW RFC SDK version's `sapnwrfc.ini` and secure-storage
guidance. The MCP does not accept RFC passwords as tool arguments and does not return
them in errors or logs.

Repeat `--rfc-destination` for each permitted backend route. Its format is:

```text
SID/CLIENT/SYSTEM_NUMBER/APPLICATION_SERVER=RFC_DESTINATION
```

These values must match `GuiSessionInfo.SystemName`, `Client`, `SystemNumber` and
`ApplicationServer`. The RFC connection must independently report the same system,
client, system number and partner host. Exact host matching is deliberate: load-balanced
destinations are rejected because the RFC call could land on a different server. Give
each application server its own direct route and destination.

There is no default route, wildcard, tool-call override, cache or offline grace period.
Changing startup arguments requires restarting the MCP server.

## Backend authorizations

Use a dedicated classification user with only the authorizations Basis determines are
needed for:

- RFC execution of `RFC_READ_TABLE` (function group `SDTX`), restricted at function
  level where the SAP release supports it.
- Display (`03`) of table `T000`, preferably through `S_TABU_NAM` with table name
  `T000`. Check overlapping `S_TABU_DIS` grants.

Do not grant generic table-read access. Confirm the effective authorization checks on
the target SAP release with an authorization trace. SAP warns that `RFC_READ_TABLE`
can expose many tables when broadly authorized, so the technical user's table access
must be restricted to `T000`.

The server always submits this fixed request; the assistant cannot supply a table,
field, condition or row count:

```text
RFC_READ_TABLE
  QUERY_TABLE = T000
  FIELDS       = MANDT, CCCATEGORY
  OPTIONS      = MANDT = '<verified GUI client>'
  ROWCOUNT     = 2
```

It requires exactly one row whose client equals the verified GUI client.

## Enforcement sequence

At attachment, the server reads the actual GUI system/client/server identity, selects
the startup route, opens RFC and verifies the connection attributes. It reads the role,
then rereads the GUI identity after the RFC round trip. Only then is attachment allowed.
Connection discovery performs this check before a session becomes an attachment
candidate. For a denied session it returns only minimal identity and refusal status;
it does not read the current transaction or window title.

Every attached-session operation repeats that process through the controller's common
session guard. Write approval reads the target before prompting and repeats the guard
inside the same serialized COM job immediately before mutation. A role or identity
change revokes the binding and requires attachment approval again. `sap_connect` is
disabled because opening or logging on occurs before a client role can be verified;
log on manually and use `sap_connect_existing`.

The check classifies an SAP **client**, not every client in its SAP system. It also
depends on correct SCC4/T000 administration and is not atomic with the later GUI call.
SAP-side authorizations and scripting restrictions remain the stronger boundary.
