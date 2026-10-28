"""Launch one-shot JAKA worker subprocesses (no shell, allowlisted ops)."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from app.jaka.protocol import (
    ALLOWED_OPS,
    ERR_INVALID_RESPONSE,
    ERR_OP_NOT_ALLOWED,
    ERR_PROCESS_CRASHED,
    ERR_PYTHON_EXE_MISSING,
    ERR_TIMEOUT,
    PROTOCOL_VERSION,
    make_response,
)
from app.paths import PROJECT_ROOT

WORKER_PATH = PROJECT_ROOT / "app" / "jaka" / "worker.py"
DEFAULT_TIMEOUT_SEC = 20.0


class JakaProcessClient:
    """Single request/response channel to the JAKA Python worker."""

    def __init__(
        self,
        python_exe: str | Path,
        *,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        project_root: Path | None = None,
        worker_path: Path | None = None,
    ) -> None:
        self.python_exe = Path(python_exe)
        self.timeout_sec = float(timeout_sec)
        self.project_root = project_root or PROJECT_ROOT
        self.worker_path = worker_path or WORKER_PATH

    def invoke(
        self,
        op: str,
        params: dict[str, Any] | None = None,
        *,
        request_id: str | None = None,
        timeout_sec: float | None = None,
    ) -> dict[str, Any]:
        op_name = str(op or "").strip()
        if op_name not in ALLOWED_OPS:
            return make_response(
                ok=False,
                op=op_name,
                request_id=request_id,
                simulated=False,
                error_code=ERR_OP_NOT_ALLOWED,
                message=f"op not allowed: {op_name}",
            )

        if not self.python_exe.is_file():
            return make_response(
                ok=False,
                op=op_name,
                request_id=request_id,
                simulated=False,
                error_code=ERR_PYTHON_EXE_MISSING,
                message=f"python_exe not found: {self.python_exe}",
            )

        if not self.worker_path.is_file():
            return make_response(
                ok=False,
                op=op_name,
                request_id=request_id,
                simulated=False,
                error_code=ERR_PROCESS_CRASHED,
                message=f"worker missing: {self.worker_path}",
            )

        rid = request_id or uuid.uuid4().hex
        payload = {
            "protocol_version": PROTOCOL_VERSION,
            "op": op_name,
            "request_id": rid,
            "params": params or {},
        }
        body = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        timeout = self.timeout_sec if timeout_sec is None else float(timeout_sec)

        env = os.environ.copy()
        # Ensure worker can import app.jaka.*; do not shell-interpolate user input.
        root_s = str(self.project_root)
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            root_s if not existing else root_s + os.pathsep + existing
        )

        # argv list only — never shell=True.
        cmd = [str(self.python_exe), str(self.worker_path)]
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.project_root),
                env=env,
                shell=False,
            )
        except OSError as exc:
            return make_response(
                ok=False,
                op=op_name,
                request_id=rid,
                simulated=False,
                error_code=ERR_PROCESS_CRASHED,
                message=str(exc),
            )

        try:
            stdout_b, stderr_b = proc.communicate(input=body, timeout=timeout)
        except subprocess.TimeoutExpired:
            self._kill(proc)
            try:
                stdout_b, stderr_b = proc.communicate(timeout=5)
            except Exception:  # noqa: BLE001
                stdout_b, stderr_b = b"", b""
            return make_response(
                ok=False,
                op=op_name,
                request_id=rid,
                simulated=False,
                error_code=ERR_TIMEOUT,
                message=f"worker timed out after {timeout}s",
                data={
                    "stderr_tail": self._tail(stderr_b),
                    "exit_code": proc.returncode,
                },
            )

        stdout = stdout_b.decode("utf-8", errors="replace").strip()
        stderr_tail = self._tail(stderr_b)
        exit_code = proc.returncode

        if not stdout:
            return make_response(
                ok=False,
                op=op_name,
                request_id=rid,
                simulated=op_name.startswith("sim_"),
                error_code=ERR_PROCESS_CRASHED
                if exit_code not in (0, None)
                else ERR_INVALID_RESPONSE,
                message=f"empty stdout; exit_code={exit_code}",
                data={"stderr_tail": stderr_tail, "exit_code": exit_code},
            )

        try:
            parsed = json.loads(stdout.splitlines()[-1])
        except json.JSONDecodeError:
            return make_response(
                ok=False,
                op=op_name,
                request_id=rid,
                simulated=op_name.startswith("sim_"),
                error_code=ERR_INVALID_RESPONSE,
                message="stdout is not valid JSON",
                data={
                    "stdout_tail": stdout[-500:],
                    "stderr_tail": stderr_tail,
                    "exit_code": exit_code,
                },
            )

        if not isinstance(parsed, dict):
            return make_response(
                ok=False,
                op=op_name,
                request_id=rid,
                simulated=op_name.startswith("sim_"),
                error_code=ERR_INVALID_RESPONSE,
                message="response JSON is not an object",
                data={"exit_code": exit_code, "stderr_tail": stderr_tail},
            )

        # Normalize required keys if worker omitted any.
        parsed.setdefault("protocol_version", PROTOCOL_VERSION)
        parsed.setdefault("ok", False)
        parsed.setdefault("op", op_name)
        parsed.setdefault("request_id", rid)
        parsed.setdefault("simulated", op_name.startswith("sim_"))
        parsed.setdefault("error_code", None)
        parsed.setdefault("message", "")
        parsed.setdefault("data", {})
        if isinstance(parsed.get("data"), dict):
            parsed["data"] = {
                **parsed["data"],
                "exit_code": exit_code,
                "stderr_tail": stderr_tail,
            }
        return parsed

    @staticmethod
    def _kill(proc: subprocess.Popen[bytes]) -> None:
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _tail(data: bytes, limit: int = 800) -> str:
        text = data.decode("utf-8", errors="replace")
        return text[-limit:] if len(text) > limit else text
