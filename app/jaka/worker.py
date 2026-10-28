"""
JAKA independent worker process.

Stdout: exactly one JSON result object (except intentional fault ops).
Stderr: diagnostics only.
Does not keep a live controller; each process is one-shot.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any


def _bootstrap_imports() -> None:
    root = Path(__file__).resolve().parents[2]
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


_bootstrap_imports()

from app.jaka.probe_observe import observe_value  # noqa: E402
from app.jaka.protocol import (  # noqa: E402
    ALLOWED_OPS,
    ERR_CONNECT_FAIL,
    ERR_CONNECT_TIMEOUT,
    ERR_DISCONNECTED,
    ERR_INVALID_REQUEST,
    ERR_OP_NOT_ALLOWED,
    ERR_PROBE_TYPE_ERROR,  # used by probe + sim_probe handlers
    ERR_SDK_LOAD_FAILED,
    SIM_OPS,
    make_response,
)


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _read_request() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw or not str(raw).strip():
        raise ValueError("empty_stdin")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("request_not_object")
    return data


def _emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _maybe_sleep(params: dict[str, Any]) -> None:
    sleep_ms = params.get("sleep_ms", 0)
    try:
        ms = int(sleep_ms)
    except (TypeError, ValueError):
        return
    if ms > 0:
        time.sleep(ms / 1000.0)


def _py_version() -> str:
    return (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )


def _prepare_sdk_dir(sdk_dir: str) -> Path | dict[str, Any]:
    text = str(sdk_dir or "").strip()
    if not text:
        return make_response(
            ok=False,
            op="",
            simulated=False,
            error_code=ERR_SDK_LOAD_FAILED,
            message="sdk_dir missing",
        )
    sdk_path = Path(text)
    if not sdk_path.is_dir():
        return make_response(
            ok=False,
            op="",
            simulated=False,
            error_code=ERR_SDK_LOAD_FAILED,
            message=f"sdk_dir not found: {text}",
        )
    path_parts = [
        p
        for p in os.environ.get("PATH", "").split(os.pathsep)
        if p and ("ZiYan" not in p.replace("/", "\\"))
    ]
    os.environ["PATH"] = str(sdk_path) + os.pathsep + os.pathsep.join(path_parts)
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(sdk_path))
    sys.path = [
        p for p in sys.path if p and ("ZiYan" not in p.replace("/", "\\"))
    ]
    sys.path.insert(0, str(sdk_path))
    return sdk_path


def handle_sdk_diag(request_id: str | None, params: dict[str, Any]) -> dict[str, Any]:
    prepared = _prepare_sdk_dir(str(params.get("sdk_dir") or ""))
    if isinstance(prepared, dict):
        prepared["op"] = "sdk_diag"
        prepared["request_id"] = request_id
        return prepared
    sdk_path = prepared

    try:
        import jkrc  # type: ignore
    except Exception as exc:  # noqa: BLE001 — surface any load failure
        _eprint(f"jkrc import failed: {exc!r}")
        _eprint(traceback.format_exc())
        return make_response(
            ok=False,
            op="sdk_diag",
            request_id=request_id,
            simulated=False,
            error_code=ERR_SDK_LOAD_FAILED,
            message=str(exc),
            data={
                "python_version": _py_version(),
                "python_executable": sys.executable,
                "sdk_dir": str(sdk_path),
                "jkrc_imported": False,
            },
        )

    mod_file = getattr(jkrc, "__file__", None)
    mod_file_s = str(mod_file) if mod_file else ""
    from_vendor = mod_file_s.replace("/", "\\").lower().startswith(
        str(sdk_path).replace("/", "\\").lower()
    )
    from_ziyan = "ziyan" in mod_file_s.replace("/", "\\").lower()
    # Do NOT construct controller / login / network.
    return make_response(
        ok=True,
        op="sdk_diag",
        request_id=request_id,
        simulated=False,
        message="jkrc imported",
        data={
            "python_version": _py_version(),
            "python_executable": sys.executable,
            "sdk_dir": str(sdk_path),
            "jkrc_imported": True,
            "jkrc_file": mod_file_s,
            "jkrc_from_vendor": from_vendor,
            "jkrc_from_ziyan": from_ziyan,
        },
    )


def handle_probe_get_controller_ip(
    request_id: str | None, params: dict[str, Any]
) -> dict[str, Any]:
    """
    Call exactly: jkrc.get_controller_ip()
    No name args, no RC(), no login, no retries with alternate signatures.
    """
    op = "probe_get_controller_ip"
    prepared = _prepare_sdk_dir(str(params.get("sdk_dir") or ""))
    if isinstance(prepared, dict):
        prepared["op"] = op
        prepared["request_id"] = request_id
        return prepared
    sdk_path = prepared

    base = {
        "python_version": _py_version(),
        "python_executable": sys.executable,
        "sdk_dir": str(sdk_path),
        "call": "jkrc.get_controller_ip()",
        "call_args": [],
        "rc_constructed": False,
        "login_called": False,
        "retried_with_other_signature": False,
    }

    try:
        import jkrc  # type: ignore
    except Exception as exc:  # noqa: BLE001
        _eprint(f"jkrc import failed: {exc!r}")
        _eprint(traceback.format_exc())
        return make_response(
            ok=False,
            op=op,
            request_id=request_id,
            simulated=False,
            error_code=ERR_SDK_LOAD_FAILED,
            message=str(exc),
            data={**base, "jkrc_imported": False},
        )

    mod_file = getattr(jkrc, "__file__", None)
    mod_file_s = str(mod_file) if mod_file else ""
    base["jkrc_imported"] = True
    base["jkrc_file"] = mod_file_s
    base["jkrc_from_vendor"] = mod_file_s.replace("/", "\\").lower().startswith(
        str(sdk_path).replace("/", "\\").lower()
    )
    base["jkrc_from_ziyan"] = "ziyan" in mod_file_s.replace("/", "\\").lower()

    fn = getattr(jkrc, "get_controller_ip", None)
    if fn is None or not callable(fn):
        return make_response(
            ok=False,
            op=op,
            request_id=request_id,
            simulated=False,
            error_code=ERR_SDK_LOAD_FAILED,
            message="jkrc.get_controller_ip missing or not callable",
            data=base,
        )

    t0 = time.perf_counter()
    try:
        # Exact no-arg call only. Do not catch broadly and retry.
        raw = fn()
    except TypeError as exc:
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        _eprint(f"get_controller_ip() TypeError: {exc!r}")
        _eprint(traceback.format_exc())
        return make_response(
            ok=False,
            op=op,
            request_id=request_id,
            simulated=False,
            error_code=ERR_PROBE_TYPE_ERROR,
            message=str(exc),
            data={
                **base,
                "elapsed_ms": elapsed_ms,
                "exception_type": "TypeError",
                "exception_repr": repr(exc),
                "traceback": traceback.format_exc(),
                "return_observed": False,
            },
        )
    except Exception as exc:  # noqa: BLE001 — record other failures; still no retry
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        _eprint(f"get_controller_ip() raised: {exc!r}")
        _eprint(traceback.format_exc())
        return make_response(
            ok=False,
            op=op,
            request_id=request_id,
            simulated=False,
            error_code=ERR_INVALID_REQUEST,
            message=str(exc),
            data={
                **base,
                "elapsed_ms": elapsed_ms,
                "exception_type": type(exc).__name__,
                "exception_repr": repr(exc),
                "traceback": traceback.format_exc(),
                "return_observed": False,
            },
        )

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
    observation = observe_value(raw)
    # Do not map non-zero codes or unknown shapes to 'no devices'.
    return make_response(
        ok=True,
        op=op,
        request_id=request_id,
        simulated=False,
        message="get_controller_ip() returned",
        data={
            **base,
            "elapsed_ms": elapsed_ms,
            "return_observed": True,
            "return_value": observation,
        },
    )


def handle_sim(op: str, request_id: str | None, params: dict[str, Any]) -> dict[str, Any]:
    # Simulation must never import jkrc.
    if "jkrc" in sys.modules:
        _eprint("refusing sim op while jkrc already imported")
        return make_response(
            ok=False,
            op=op,
            request_id=request_id,
            simulated=True,
            error_code=ERR_INVALID_REQUEST,
            message="jkrc already imported; sim refused",
        )

    _maybe_sleep(params)
    echo = {
        "equipment_txid": params.get("equipment_txid"),
        "host_address": params.get("host_address"),
        "driver_type": params.get("driver_type"),
    }

    if op == "sim_bad_stdout":
        # Intentional protocol violation for host invalid_response tests.
        sys.stdout.write("NOT_JSON_PROTOCOL_VIOLATION\n")
        sys.stdout.flush()
        return {}  # unused; caller must not emit again

    if op == "sim_crash":
        _eprint("sim_crash requested")
        sys.exit(2)

    if op == "sim_connect_ok":
        return make_response(
            ok=True,
            op=op,
            request_id=request_id,
            simulated=True,
            message="simulated connect ok",
            data={**echo, "connection_state": "connected"},
        )
    if op == "sim_connect_fail":
        return make_response(
            ok=False,
            op=op,
            request_id=request_id,
            simulated=True,
            error_code=ERR_CONNECT_FAIL,
            message="simulated connect fail",
            data={**echo, "connection_state": "failed"},
        )
    if op == "sim_connect_timeout":
        return make_response(
            ok=False,
            op=op,
            request_id=request_id,
            simulated=True,
            error_code=ERR_CONNECT_TIMEOUT,
            message="simulated connect timeout",
            data={**echo, "connection_state": "timeout"},
        )
    if op == "sim_disconnect":
        return make_response(
            ok=False,
            op=op,
            request_id=request_id,
            simulated=True,
            error_code=ERR_DISCONNECTED,
            message="simulated disconnect after connected",
            data={**echo, "connection_state": "disconnected"},
        )
    if op == "sim_probe_controller_ip_ok":
        fake = (0, ["192.0.2.10", "192.0.2.11"])
        return make_response(
            ok=True,
            op=op,
            request_id=request_id,
            simulated=True,
            message="simulated get_controller_ip() return",
            data={
                "call": "jkrc.get_controller_ip()",
                "call_args": [],
                "rc_constructed": False,
                "login_called": False,
                "retried_with_other_signature": False,
                "elapsed_ms": 1.0,
                "return_observed": True,
                "return_value": observe_value(fake),
            },
        )
    if op == "sim_probe_controller_ip_type_error":
        return make_response(
            ok=False,
            op=op,
            request_id=request_id,
            simulated=True,
            error_code=ERR_PROBE_TYPE_ERROR,
            message="get_controller_ip() missing required argument (simulated)",
            data={
                "call": "jkrc.get_controller_ip()",
                "call_args": [],
                "rc_constructed": False,
                "login_called": False,
                "retried_with_other_signature": False,
                "elapsed_ms": 0.5,
                "exception_type": "TypeError",
                "exception_repr": "TypeError('simulated')",
                "return_observed": False,
            },
        )
    if op == "sim_probe_controller_ip_nonzero":
        fake = (-3, None)
        return make_response(
            ok=True,
            op=op,
            request_id=request_id,
            simulated=True,
            message="simulated get_controller_ip() non-zero errcode (raw only)",
            data={
                "call": "jkrc.get_controller_ip()",
                "call_args": [],
                "elapsed_ms": 1.0,
                "return_observed": True,
                "return_value": observe_value(fake),
                "interpreted_as_no_devices": False,
            },
        )
    return make_response(
        ok=False,
        op=op,
        request_id=request_id,
        simulated=True,
        error_code=ERR_OP_NOT_ALLOWED,
        message=f"unhandled sim op: {op}",
    )


def main() -> int:
    request_id: str | None = None
    op = ""
    try:
        req = _read_request()
    except Exception as exc:  # noqa: BLE001
        _eprint(f"invalid request: {exc!r}")
        _emit(
            make_response(
                ok=False,
                op="",
                simulated=False,
                error_code=ERR_INVALID_REQUEST,
                message=str(exc),
            )
        )
        return 1

    op = str(req.get("op") or "").strip()
    request_id = req.get("request_id")
    if request_id is not None:
        request_id = str(request_id)
    params = req.get("params") if isinstance(req.get("params"), dict) else {}

    if op not in ALLOWED_OPS:
        _emit(
            make_response(
                ok=False,
                op=op,
                request_id=request_id,
                simulated=False,
                error_code=ERR_OP_NOT_ALLOWED,
                message=f"op not allowed: {op}",
            )
        )
        return 1

    try:
        if op == "sdk_diag":
            result = handle_sdk_diag(request_id, params)
            _emit(result)
            return 0 if result.get("ok") else 1

        if op == "probe_get_controller_ip":
            result = handle_probe_get_controller_ip(request_id, params)
            _emit(result)
            return 0 if result.get("ok") else 1

        if op in SIM_OPS:
            if op == "sim_bad_stdout":
                handle_sim(op, request_id, params)
                return 0
            if op == "sim_crash":
                handle_sim(op, request_id, params)
                return 2
            result = handle_sim(op, request_id, params)
            _emit(result)
            return 0 if result.get("ok") else 1

        _emit(
            make_response(
                ok=False,
                op=op,
                request_id=request_id,
                simulated=False,
                error_code=ERR_OP_NOT_ALLOWED,
                message=f"op not allowed: {op}",
            )
        )
        return 1
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        _eprint(traceback.format_exc())
        _emit(
            make_response(
                ok=False,
                op=op,
                request_id=request_id,
                simulated=op in SIM_OPS,
                error_code=ERR_INVALID_REQUEST,
                message=str(exc),
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
