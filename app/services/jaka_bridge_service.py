"""
Host-side JAKA bridge: equipment settings + process channel.

Does not import jkrc in the host process. Does not open public HTTP APIs.
Does not write real "connected" device state. Never falls back from SDK
failure to simulated success.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.jaka.protocol import (
    ERR_CONFIG_INCOMPLETE,
    ERR_EQUIPMENT_NOT_APPLICABLE,
    ERR_EQUIPMENT_NOT_CONFIGURED,
    ERR_EQUIPMENT_NOT_FOUND,
    ERR_OP_NOT_ALLOWED,
    PROBE_GET_CONTROLLER_IP_TIMEOUT_SEC,
    make_response,
)
from app.services.equipment_connection_service import EquipmentConnectionService
from app.services.jaka_process_client import DEFAULT_TIMEOUT_SEC, JakaProcessClient
from app.services.ui_service import UiService
from app.storage.config_store import resolve_path

SIM_SCENARIO_TO_OP = {
    "connect_ok": "sim_connect_ok",
    "connect_fail": "sim_connect_fail",
    "connect_timeout": "sim_connect_timeout",
    "disconnect": "sim_disconnect",
    "invalid_response": "sim_bad_stdout",
}

SIM_PROBE_SCENARIO_TO_OP = {
    "ok": "sim_probe_controller_ip_ok",
    "type_error": "sim_probe_controller_ip_type_error",
    "nonzero": "sim_probe_controller_ip_nonzero",
}


class JakaBridgeService:
    def __init__(
        self,
        ui: UiService,
        equipment: EquipmentConnectionService | None = None,
        process_client: JakaProcessClient | None = None,
    ) -> None:
        self.ui = ui
        self.equipment = equipment or EquipmentConnectionService(ui)
        self._client_override = process_client

    def _jaka_cfg(self) -> dict[str, Any]:
        raw = self.ui.config.get("jaka")
        return raw if isinstance(raw, dict) else {}

    def build_process_client(
        self, *, timeout_sec: float | None = None
    ) -> JakaProcessClient | dict[str, Any]:
        if self._client_override is not None:
            return self._client_override
        cfg = self._jaka_cfg()
        python_exe = str(cfg.get("python_exe") or "").strip()
        if not python_exe:
            return make_response(
                ok=False,
                op="",
                simulated=False,
                error_code=ERR_CONFIG_INCOMPLETE,
                message="jaka.python_exe not configured",
            )
        to = (
            float(timeout_sec)
            if timeout_sec is not None
            else float(cfg.get("process_timeout_sec") or DEFAULT_TIMEOUT_SEC)
        )
        return JakaProcessClient(python_exe, timeout_sec=to)

    def resolve_sdk_dir(self) -> Path | dict[str, Any]:
        cfg = self._jaka_cfg()
        sdk_dir = str(cfg.get("sdk_dir") or "").strip()
        if not sdk_dir:
            return make_response(
                ok=False,
                op="sdk_diag",
                simulated=False,
                error_code=ERR_CONFIG_INCOMPLETE,
                message="jaka.sdk_dir not configured",
            )
        path = resolve_path(sdk_dir)
        if not path.is_dir():
            return make_response(
                ok=False,
                op="sdk_diag",
                simulated=False,
                error_code=ERR_CONFIG_INCOMPLETE,
                message=f"sdk_dir missing on disk: {path}",
            )
        return path

    def get_equipment_connection_snapshot(
        self, equipment_txid: int
    ) -> dict[str, Any]:
        """
        Load connection settings for a physical inventory TxId.
        Same TxId always yields the same stored settings regardless of
        which product combination references it.
        """
        try:
            view = self.equipment.build_view(equipment_txid)
        except KeyError:
            return make_response(
                ok=False,
                op="",
                simulated=False,
                error_code=ERR_EQUIPMENT_NOT_FOUND,
                message=f"Unknown equipment TxId: {equipment_txid}",
            )

        if not view["applicable"]:
            return make_response(
                ok=False,
                op="",
                simulated=False,
                error_code=ERR_EQUIPMENT_NOT_APPLICABLE,
                message="equipment not applicable for JAKA connection",
                data={"equipment_txid": equipment_txid},
            )

        if not view["configured"] or view["connection"] is None:
            return make_response(
                ok=False,
                op="",
                simulated=False,
                error_code=ERR_EQUIPMENT_NOT_CONFIGURED,
                message="equipment connection not configured",
                data={
                    "equipment_txid": equipment_txid,
                    "status": "not_configured",
                },
            )

        conn = view["connection"]
        return {
            "ok": True,
            "error_code": None,
            "equipment_txid": equipment_txid,
            "equipment": view["equipment"],
            "connection": {
                "driver_type": conn["driver_type"],
                "connection_mode": conn["connection_mode"],
                "host_address": conn["host_address"],
                "remark": conn.get("remark") or "",
                "updated_at": conn.get("updated_at"),
            },
            # Formal live-connection flags are never set by this bridge.
            "live_connected": False,
            "controller_connection_verified": False,
            "simulated": False,
        }

    def run_sdk_diag(
        self,
        *,
        timeout_sec: float | None = None,
        request_id: str | None = None,
        sdk_dir_override: str | Path | None = None,
    ) -> dict[str, Any]:
        """Explicit SDK diagnostic only; never used as sim fallback."""
        client = self.build_process_client(timeout_sec=timeout_sec)
        if isinstance(client, dict):
            client["op"] = "sdk_diag"
            return client

        if sdk_dir_override is not None:
            sdk_path = Path(sdk_dir_override)
        else:
            resolved = self.resolve_sdk_dir()
            if isinstance(resolved, dict):
                return resolved
            sdk_path = resolved

        return client.invoke(
            "sdk_diag",
            {"sdk_dir": str(sdk_path)},
            request_id=request_id,
            timeout_sec=timeout_sec,
        )

    def run_probe_get_controller_ip(
        self,
        *,
        timeout_sec: float | None = None,
        request_id: str | None = None,
        sdk_dir_override: str | Path | None = None,
    ) -> dict[str, Any]:
        """
        One-shot probe: worker calls jkrc.get_controller_ip() with no args.
        Does not require equipment_connection. Does not persist results.
        """
        to = (
            float(timeout_sec)
            if timeout_sec is not None
            else float(PROBE_GET_CONTROLLER_IP_TIMEOUT_SEC)
        )
        client = self.build_process_client(timeout_sec=to)
        if isinstance(client, dict):
            client["op"] = "probe_get_controller_ip"
            return client

        if sdk_dir_override is not None:
            sdk_path = Path(sdk_dir_override)
        else:
            resolved = self.resolve_sdk_dir()
            if isinstance(resolved, dict):
                resolved["op"] = "probe_get_controller_ip"
                return resolved
            sdk_path = resolved

        return client.invoke(
            "probe_get_controller_ip",
            {"sdk_dir": str(sdk_path)},
            request_id=request_id,
            timeout_sec=to,
        )

    def run_sim_probe_get_controller_ip(
        self,
        scenario: str,
        *,
        timeout_sec: float | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Offline probe simulation (no jkrc / no network)."""
        op = SIM_PROBE_SCENARIO_TO_OP.get(str(scenario).strip())
        if op is None:
            return make_response(
                ok=False,
                op=str(scenario),
                request_id=request_id,
                simulated=True,
                error_code=ERR_OP_NOT_ALLOWED,
                message=f"unknown sim probe scenario: {scenario}",
            )
        client = self.build_process_client(timeout_sec=timeout_sec)
        if isinstance(client, dict):
            client["op"] = op
            client["simulated"] = True
            return client
        return client.invoke(op, {}, request_id=request_id, timeout_sec=timeout_sec)

    def run_simulate(
        self,
        equipment_txid: int,
        scenario: str,
        *,
        timeout_sec: float | None = None,
        request_id: str | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Offline simulation. Never imports jkrc in host.
        Never writes live connected state. Never auto-called on SDK failure.
        """
        op = SIM_SCENARIO_TO_OP.get(str(scenario).strip())
        if op is None:
            return make_response(
                ok=False,
                op=str(scenario),
                request_id=request_id,
                simulated=True,
                error_code=ERR_OP_NOT_ALLOWED,
                message=f"unknown simulate scenario: {scenario}",
            )

        snap = self.get_equipment_connection_snapshot(equipment_txid)
        if not snap.get("ok"):
            # Preserve not_configured / not_applicable — do not start a real link.
            snap["simulated"] = True
            snap["op"] = op
            if "protocol_version" not in snap:
                return make_response(
                    ok=False,
                    op=op,
                    request_id=request_id,
                    simulated=True,
                    error_code=snap.get("error_code"),
                    message=str(snap.get("message") or ""),
                    data=snap.get("data") or {"equipment_txid": equipment_txid},
                )
            return snap

        client = self.build_process_client(timeout_sec=timeout_sec)
        if isinstance(client, dict):
            client["op"] = op
            client["simulated"] = True
            return client

        conn = snap["connection"]
        params: dict[str, Any] = {
            "equipment_txid": equipment_txid,
            "host_address": conn["host_address"],
            "driver_type": conn["driver_type"],
            "connection_mode": conn["connection_mode"],
        }
        if extra_params:
            params.update(extra_params)

        result = client.invoke(
            op, params, request_id=request_id, timeout_sec=timeout_sec
        )
        # Reinforce: simulation must never mark formal verification.
        result["simulated"] = True
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        data["live_connected"] = False
        data["controller_connection_verified"] = False
        data["equipment_txid"] = equipment_txid
        result["data"] = data
        return result

    def invoke_raw(
        self,
        op: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_sec: float | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Low-level allowlisted invoke (tests / manual tools)."""
        client = self.build_process_client(timeout_sec=timeout_sec)
        if isinstance(client, dict):
            client["op"] = op
            return client
        return client.invoke(
            op, params or {}, request_id=request_id, timeout_sec=timeout_sec
        )
