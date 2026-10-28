"""Shared JAKA worker request/response constants (pure Python, no jkrc)."""

from __future__ import annotations

from typing import Any

PROTOCOL_VERSION = 1

# Host and worker share this allowlist; unknown ops are rejected.
ALLOWED_OPS = frozenset(
    {
        "sdk_diag",
        "probe_get_controller_ip",
        "sim_connect_ok",
        "sim_connect_fail",
        "sim_connect_timeout",
        "sim_disconnect",
        "sim_bad_stdout",
        "sim_crash",
        "sim_probe_controller_ip_ok",
        "sim_probe_controller_ip_type_error",
        "sim_probe_controller_ip_nonzero",
    }
)

SIM_OPS = frozenset(
    {
        "sim_connect_ok",
        "sim_connect_fail",
        "sim_connect_timeout",
        "sim_disconnect",
        "sim_bad_stdout",
        "sim_crash",
        "sim_probe_controller_ip_ok",
        "sim_probe_controller_ip_type_error",
        "sim_probe_controller_ip_nonzero",
    }
)

# Machine-readable error codes for host + worker.
ERR_OP_NOT_ALLOWED = "op_not_allowed"
ERR_INVALID_REQUEST = "invalid_request"
ERR_PYTHON_EXE_MISSING = "python_exe_missing"
ERR_SDK_LOAD_FAILED = "sdk_load_failed"
ERR_PROCESS_CRASHED = "process_crashed"
ERR_INVALID_RESPONSE = "invalid_response"
ERR_TIMEOUT = "timeout"
ERR_EQUIPMENT_NOT_FOUND = "equipment_not_found"
ERR_EQUIPMENT_NOT_APPLICABLE = "equipment_not_applicable"
ERR_EQUIPMENT_NOT_CONFIGURED = "equipment_not_configured"
ERR_CONFIG_INCOMPLETE = "config_incomplete"
ERR_CONNECT_FAIL = "connect_fail"
ERR_CONNECT_TIMEOUT = "connect_timeout"
ERR_DISCONNECTED = "disconnected"
ERR_PROBE_TYPE_ERROR = "probe_type_error"

# Manual probe default (parent kills worker after this many seconds).
PROBE_GET_CONTROLLER_IP_TIMEOUT_SEC = 30.0


def make_response(
    *,
    ok: bool,
    op: str,
    request_id: str | None = None,
    simulated: bool = False,
    error_code: str | None = None,
    message: str = "",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "ok": bool(ok),
        "op": op,
        "request_id": request_id,
        "simulated": bool(simulated),
        "error_code": error_code,
        "message": message or "",
        "data": data if data is not None else {},
    }
