"""Fresh SAP client-role classification through the standard RFC_READ_TABLE RFM."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .models import SAPGUIError

logger = logging.getLogger(__name__)

SAFE_CLIENT_ROLES = frozenset({"C", "T"})  # Customizing and Test
_SYSTEM_RE = re.compile(r"[A-Z0-9]{3}")
_CLIENT_RE = re.compile(r"[0-9]{3}")
_SYSNR_RE = re.compile(r"[0-9]{2}")
_SERVER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}")
_DEST_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


@dataclass(frozen=True)
class GuiBackend:
    system: str
    client: str
    system_number: str
    application_server: str

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.system, self.client, self.system_number, self.application_server.casefold())


def _gui_backend(session: Any) -> GuiBackend:
    try:
        info = session.Info
        values = GuiBackend(
            system=str(info.SystemName).strip().upper(),
            client=str(info.Client).strip(),
            system_number=str(info.SystemNumber).strip(),
            application_server=str(info.ApplicationServer).strip().rstrip("."),
        )
    except Exception as exc:
        raise SAPGUIError("Cannot read the complete SAP backend identity. Access denied.") from exc
    if (not _SYSTEM_RE.fullmatch(values.system)
            or not _CLIENT_RE.fullmatch(values.client)
            or not _SYSNR_RE.fullmatch(values.system_number)
            or not _SERVER_RE.fullmatch(values.application_server)):
        raise SAPGUIError("SAP backend identity is missing or invalid. Access denied.")
    return values


def parse_rfc_route(value: str) -> tuple[tuple[str, str, str, str], str]:
    """Parse SID/CLIENT/SYSNR/APPSERVER=DEST from a startup argument."""
    route, separator, destination = value.partition("=")
    parts = route.split("/")
    if not separator or len(parts) != 4:
        raise ValueError(
            "expected SID/CLIENT/SYSNR/APPLICATION_SERVER=RFC_DESTINATION"
        )
    backend = GuiBackend(parts[0].upper(), parts[1], parts[2], parts[3].rstrip("."))
    if (not _SYSTEM_RE.fullmatch(backend.system)
            or not _CLIENT_RE.fullmatch(backend.client)
            or not _SYSNR_RE.fullmatch(backend.system_number)
            or not _SERVER_RE.fullmatch(backend.application_server)
            or not _DEST_RE.fullmatch(destination)):
        raise ValueError("route contains an invalid backend identity or RFC destination")
    return backend.key, destination


def parse_rfc_routes(values: list[str] | None) -> dict[tuple[str, str, str, str], str]:
    routes: dict[tuple[str, str, str, str], str] = {}
    for value in values or []:
        key, destination = parse_rfc_route(value)
        if key in routes:
            raise ValueError("duplicate RFC route for the same GUI backend")
        routes[key] = destination
    return routes


def _pyrfc_connection(*, dest: str):
    try:
        from pyrfc import Connection
    except ImportError as exc:
        raise RuntimeError(
            "PyRFC and the SAP NetWeaver RFC SDK are required for client classification"
        ) from exc
    return Connection(dest=dest)


class RfcClientClassifier:
    """Prove that the current GUI client has an explicitly safe SCC4 role."""

    def __init__(
        self,
        routes: Mapping[tuple[str, str, str, str], str],
        connection_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._routes = dict(routes)
        self._connection_factory = connection_factory or _pyrfc_connection

    def check(self, session: Any) -> dict[str, str]:
        """Perform a new RFC check, with GUI identity checks around the round trip."""
        before = _gui_backend(session)
        destination = self._routes.get(before.key)
        if destination is None:
            raise SAPGUIError(
                "No RFC classification route is configured for this SAP backend. Access denied."
            )

        connection = None
        try:
            connection = self._connection_factory(dest=destination)
            attributes = connection.get_connection_attributes()
            self._verify_rfc_identity(before, attributes)
            response = connection.call(
                "RFC_READ_TABLE",
                QUERY_TABLE="T000",
                DELIMITER="|",
                FIELDS=[{"FIELDNAME": "MANDT"}, {"FIELDNAME": "CCCATEGORY"}],
                OPTIONS=[{"TEXT": f"MANDT = '{before.client}'"}],
                ROWCOUNT=2,
            )
            role = self._parse_role(response, before.client)
            after = _gui_backend(session)
            if after != before:
                raise SAPGUIError("SAP GUI backend changed during classification. Access denied.")
            if role not in SAFE_CLIENT_ROLES:
                label = "Production" if role == "P" else f"unsupported role {role!r}"
                raise SAPGUIError(f"SAP client is classified as {label}. Access denied.")
            return {
                "system": before.system,
                "client": before.client,
                "system_number": before.system_number,
                "application_server": before.application_server,
                "client_role": role,
            }
        except SAPGUIError:
            raise
        except Exception as exc:
            logger.warning("RFC client classification failed: %s", exc)
            raise SAPGUIError("SAP client classification failed. Access denied.") from exc
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    logger.warning("Could not close RFC classification connection", exc_info=True)

    @staticmethod
    def _verify_rfc_identity(gui: GuiBackend, attributes: Any) -> None:
        if not isinstance(attributes, Mapping):
            raise SAPGUIError("RFC connection identity is unavailable. Access denied.")
        actual = {
            "system": str(attributes.get("sysId", "")).strip().upper(),
            "client": str(attributes.get("client", "")).strip(),
            "system_number": str(attributes.get("sysNumber", "")).strip(),
            "application_server": str(attributes.get("partnerHost", "")).strip().rstrip("."),
        }
        expected = {
            "system": gui.system,
            "client": gui.client,
            "system_number": gui.system_number,
            "application_server": gui.application_server,
        }
        if (actual["system"] != expected["system"]
                or actual["client"] != expected["client"]
                or actual["system_number"] != expected["system_number"]
                or actual["application_server"].casefold()
                != expected["application_server"].casefold()):
            raise SAPGUIError("RFC destination does not match the SAP GUI backend. Access denied.")

    @staticmethod
    def _parse_role(response: Any, client: str) -> str:
        if not isinstance(response, Mapping) or not isinstance(response.get("DATA"), list):
            raise SAPGUIError("RFC_READ_TABLE returned an invalid response. Access denied.")
        rows = response["DATA"]
        if len(rows) != 1 or not isinstance(rows[0], Mapping):
            raise SAPGUIError("Client classification was missing or ambiguous. Access denied.")
        values = str(rows[0].get("WA", "")).split("|")
        if len(values) != 2 or values[0].strip() != client:
            raise SAPGUIError("Client classification did not match the GUI client. Access denied.")
        role = values[1].strip().upper()
        if len(role) != 1:
            raise SAPGUIError("Client classification role is invalid. Access denied.")
        return role
