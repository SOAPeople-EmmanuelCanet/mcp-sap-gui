"""Server-owned session and per-call write approvals. Never supplied by a tool argument."""

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from .models import SAPGUIError


def binding_identity(session: Any) -> dict:
    """Read a complete logon identity. Positional COM IDs alone can be reused."""
    try:
        info = session.Info
        values = {
            "id": session.Id,
            "system": info.SystemName,
            "client": info.Client,
            "user": info.User,
            "system_session_id": info.SystemSessionId,
            "session_number": info.SessionNumber,
        }
        return validate_identity(values)
    except Exception as exc:
        raise SAPGUIError(
            "Cannot verify the SAP session identity; attachment approval required."
        ) from exc


def validate_identity(values: dict) -> dict:
    identity = {}
    for name in ("id", "system", "client", "user", "system_session_id", "session_number"):
        value = values.get(name)
        if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
            raise SAPGUIError(f"Missing SAP session identity: {name}. Nothing authorized.")
        identity[name] = str(value)
    return identity


@dataclass
class WriteApproval:
    controller: Any
    target: dict
    used: bool = False


WRITE_APPROVAL: ContextVar[WriteApproval | None] = ContextVar("sap_write_approval", default=None)
