"""Virtual workflow runner — executes workflow_steps against VirtualDemoService.

No live cabinet, SDK, PLC, or field I/O. MOVE / GRIP / WAIT / END only.
Client may drive 3D animation segments; tests can enable animation auto-ack.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

from app.services.ui_service import UiService
from app.services.virtual_demo_service import (
    RESULT_SESSION_BUSY,
    SESSION_WORKFLOW,
    VirtualDemoService,
)
from app.storage.config_store import resolve_path
from app.storage.json_store import load_json

STATUS_READY = "ready"
STATUS_RUNNING = "running"
STATUS_STOPPED = "stopped"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# Backward-compatible alias used by older tests / callers.
STATUS_IDLE = STATUS_READY
STATUS_ERROR = STATUS_FAILED

STEP_PENDING = "pending"
STEP_RUNNING = "running"
STEP_COMPLETED = "completed"
STEP_STOPPED = "stopped"
STEP_ERROR = "error"
STEP_SKIPPED = "skipped"

ACTION_ALIASES = {
    "move": "MOVE",
    "MOVE": "MOVE",
    "gripper": "GRIP",
    "grip": "GRIP",
    "GRIP": "GRIP",
    "wait": "WAIT",
    "WAIT": "WAIT",
    "end": "END",
    "END": "END",
}


class WorkflowRunnerService:
    def __init__(
        self,
        ui_service: UiService,
        virtual_demo: VirtualDemoService,
    ) -> None:
        self.ui = ui_service
        self.store = ui_service.store
        self.virtual = virtual_demo
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._active_run_txid: int | None = None
        self._control_state = STATUS_READY
        self._targets = self._load_targets()
        self._anim_lock = threading.Lock()
        self._anim_ack = threading.Event()
        self._anim_cue: dict[str, Any] | None = None
        self._anim_result: dict[str, Any] | None = None
        self._anim_seq = 0
        self._animation_auto_ack = False
        self._animation_timeout_sec = 120.0

    def set_animation_auto_ack(self, enabled: bool) -> None:
        """Test helper: complete animation cues without a browser client."""
        self._animation_auto_ack = bool(enabled)

    def _load_targets(self) -> dict[str, Any]:
        path = resolve_path("data/virtual_demo/workflow_virtual_targets.json")
        data = load_json(path)
        if "targets" not in data or "demo_key" not in data:
            raise KeyError("Invalid workflow_virtual_targets.json")
        return data

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def normalize_action(self, action_type: str) -> str:
        key = str(action_type or "").strip()
        if key not in ACTION_ALIASES:
            raise ValueError(f"Unsupported ActionType: {action_type}")
        return ACTION_ALIASES[key]

    def get_labels(self, language: str | None = None) -> dict[str, str]:
        lang = language if language is not None else self.ui.get_prefs()["language"]
        keys = (
            "wf_run_panel_title",
            "wf_run_btn_start",
            "wf_run_btn_stop",
            "wf_run_btn_reset",
            "wf_run_label_status",
            "wf_run_label_progress",
            "wf_run_label_current_step",
            "wf_run_label_result",
            "wf_run_msg_select_workflow",
            "wf_run_msg_started",
            "wf_run_msg_stopped",
            "wf_run_msg_reset",
            "wf_run_msg_completed",
            "wf_run_msg_error",
            "wf_run_msg_need_reset",
            "wf_run_msg_session_busy",
            "wf_run_msg_duplicate_start",
            "wf_run_status_ready",
            "wf_run_status_idle",
            "wf_run_status_running",
            "wf_run_status_stopped",
            "wf_run_status_completed",
            "wf_run_status_failed",
            "wf_run_status_error",
            "wf_run_step_pending",
            "wf_run_step_running",
            "wf_run_step_completed",
            "wf_run_step_stopped",
            "wf_run_step_error",
            "wf_run_step_skipped",
        )
        out: dict[str, str] = {}
        for key in keys:
            try:
                out[key] = self.ui.t(key, lang)
            except KeyError:
                continue
        return out

    def _status_label(self, status: str, language: str) -> str:
        mapping = {
            STATUS_READY: "wf_run_status_ready",
            STATUS_RUNNING: "wf_run_status_running",
            STATUS_STOPPED: "wf_run_status_stopped",
            STATUS_COMPLETED: "wf_run_status_completed",
            STATUS_FAILED: "wf_run_status_failed",
        }
        key = mapping.get(status, f"wf_run_status_{status}")
        try:
            return self.ui.t(key, language)
        except KeyError:
            try:
                return self.ui.t("wf_run_status_error", language)
            except KeyError:
                return status

    def get_status(
        self, language: str | None = None, run_txid: int | None = None
    ) -> dict[str, Any]:
        lang = language if language is not None else self.ui.get_prefs()["language"]
        with self._lock:
            active = self._active_run_txid
            control = self._control_state
            target = run_txid if run_txid is not None else active
            run = None
            if target is not None:
                run = self.store.fetchone(
                    "SELECT * FROM workflow_runs WHERE TxId = ?",
                    (target,),
                )
            if run is None:
                # Show latest historical run for panel (ready / terminal states).
                run = self.store.fetchone(
                    """
                    SELECT * FROM workflow_runs
                    ORDER BY TxId DESC LIMIT 1
                    """
                )
            steps: list[dict[str, Any]] = []
            if run is not None:
                steps = [
                    dict(row)
                    for row in self.store.fetchall(
                        """
                        SELECT * FROM workflow_run_steps
                        WHERE RunTxId = ?
                        ORDER BY StepNo ASC, TxId ASC
                        """,
                        (run["TxId"],),
                    )
                ]
            display_status = control
            if run is not None and control == STATUS_READY:
                # After reset, still show last run history but control is ready.
                pass
            status_label = self._status_label(display_status, lang)
            can_start = control == STATUS_READY
            can_stop = control == STATUS_RUNNING
            can_reset = control in (
                STATUS_COMPLETED,
                STATUS_FAILED,
                STATUS_STOPPED,
            )
            with self._anim_lock:
                animation = dict(self._anim_cue) if self._anim_cue else None
            session = self.virtual.get_session_info()
            return {
                "active_run_txid": active,
                "control_state": control,
                "is_running": control == STATUS_RUNNING,
                "can_start": can_start,
                "can_stop": can_stop,
                "can_reset": can_reset,
                "run": dict(run) if run is not None else None,
                "steps": steps,
                "status_label": status_label,
                "labels": self.get_labels(lang),
                "virtual_demo_key": self._targets["demo_key"],
                "session": session,
                "animation": animation,
            }

    def start(self, workflow_txid: int) -> dict[str, Any]:
        with self._lock:
            if self._control_state == STATUS_RUNNING or (
                self._thread is not None and self._thread.is_alive()
            ):
                raise ValueError(
                    self.ui.t("wf_run_msg_duplicate_start")
                    if self._has_text("wf_run_msg_duplicate_start")
                    else "Workflow run already in progress"
                )
            if self._control_state in (
                STATUS_COMPLETED,
                STATUS_FAILED,
                STATUS_STOPPED,
            ):
                raise ValueError(
                    self.ui.t("wf_run_msg_need_reset")
                    if self._has_text("wf_run_msg_need_reset")
                    else "Reset required before starting again"
                )
            try:
                self.virtual.acquire_session(SESSION_WORKFLOW)
            except ValueError as exc:
                if str(exc) == RESULT_SESSION_BUSY:
                    raise ValueError(
                        self.ui.t("wf_run_msg_session_busy")
                        if self._has_text("wf_run_msg_session_busy")
                        else "Virtual session is busy"
                    ) from exc
                raise
            workflow = self.store.fetchone(
                """
                SELECT * FROM workflows
                WHERE TxId = ? AND isDisable = 0
                """,
                (workflow_txid,),
            )
            if workflow is None:
                self.virtual.release_session(SESSION_WORKFLOW)
                raise KeyError(f"Workflow not found or disabled: {workflow_txid}")
            steps = self.store.fetchall(
                """
                SELECT * FROM workflow_steps
                WHERE WorkflowTxId = ? AND isDisable = 0
                ORDER BY StepNo ASC, TxId ASC
                """,
                (workflow_txid,),
            )
            if not steps:
                self.virtual.release_session(SESSION_WORKFLOW)
                raise ValueError("Workflow has no enabled steps")
            for step in steps:
                self.normalize_action(step["ActionType"])
            now = self._now()
            run_txid = self.ui.next_txid("workflow_runs")
            self.store.execute(
                """
                INSERT INTO workflow_runs (
                    TxId, WorkflowTxId, WorkflowCode, Mode, Status,
                    CurrentStepNo, CurrentStepName, ProgressDone, ProgressTotal,
                    ErrorMessage, StartedAt, FinishedAt, Remark, CreatedAt, UpdatedAt
                ) VALUES (?, ?, ?, 'virtual', ?, NULL, NULL, 0, ?, NULL, ?, NULL, ?, ?, ?)
                """,
                (
                    run_txid,
                    workflow["TxId"],
                    workflow["WorkflowCode"],
                    STATUS_RUNNING,
                    len(steps),
                    now,
                    "virtual execution",
                    now,
                    now,
                ),
            )
            for step in steps:
                self.store.execute(
                    """
                    INSERT INTO workflow_run_steps (
                        TxId, RunTxId, WorkflowStepTxId, StepNo, StepName,
                        ActionType, TargetKey, Status, ResultMessage,
                        StartedAt, FinishedAt, Remark, CreatedAt, UpdatedAt
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, '', ?, ?)
                    """,
                    (
                        self.ui.next_txid("workflow_run_steps"),
                        run_txid,
                        step["TxId"],
                        step["StepNo"],
                        step["StepName"],
                        step["ActionType"],
                        step["TargetKey"],
                        STEP_PENDING,
                        now,
                        now,
                    ),
                )
            self._stop_event.clear()
            self._active_run_txid = run_txid
            self._control_state = STATUS_RUNNING
            with self._anim_lock:
                self._anim_cue = None
                self._anim_result = None
                self._anim_ack.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                args=(run_txid, workflow_txid),
                name=f"workflow-run-{run_txid}",
                daemon=True,
            )
            self._thread.start()
        return self.get_status(run_txid=run_txid)

    def _has_text(self, text_key: str) -> bool:
        row = self.store.fetchone(
            "SELECT text_key FROM ui_text WHERE text_key = ?",
            (text_key,),
        )
        return row is not None

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._control_state != STATUS_RUNNING:
                return self.get_status()
            self._stop_event.set()
            run_txid = self._active_run_txid
            with self._anim_lock:
                # Unblock waiter if waiting for animation.
                self._anim_result = {"ok": False, "error": "stopped"}
                self._anim_ack.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        return self.get_status(run_txid=run_txid)

    def reset(self) -> dict[str, Any]:
        with self._lock:
            if self._control_state == STATUS_RUNNING or (
                self._thread is not None and self._thread.is_alive()
            ):
                raise ValueError("Cannot reset while a run is in progress; stop first")
            self._stop_event.clear()
            self._active_run_txid = None
            self._control_state = STATUS_READY
            with self._anim_lock:
                self._anim_cue = None
                self._anim_result = None
                self._anim_ack.clear()
            try:
                self.virtual.reset_demo_forced()
            except Exception:
                self.virtual.release_session(SESSION_WORKFLOW)
        return self.get_status()

    def animation_ack(
        self,
        *,
        run_txid: int,
        step_txid: int,
        seq: int,
        ok: bool,
        error: str | None = None,
    ) -> dict[str, Any]:
        with self._anim_lock:
            cue = self._anim_cue
            if cue is None:
                raise ValueError("No animation cue pending")
            if int(cue.get("run_txid")) != int(run_txid):
                raise ValueError("Animation ack run_txid mismatch")
            if int(cue.get("step_txid")) != int(step_txid):
                raise ValueError("Animation ack step_txid mismatch")
            if int(cue.get("seq")) != int(seq):
                raise ValueError("Animation ack seq mismatch")
            self._anim_result = {"ok": bool(ok), "error": error}
            self._anim_ack.set()
        return self.get_status(run_txid=run_txid)

    def _update_run(self, run_txid: int, **fields: Any) -> None:
        fields["UpdatedAt"] = self._now()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [run_txid]
        self.store.execute(
            f"UPDATE workflow_runs SET {assignments} WHERE TxId = ?",
            tuple(values),
        )

    def _update_run_step(self, step_txid: int, **fields: Any) -> None:
        fields["UpdatedAt"] = self._now()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [step_txid]
        self.store.execute(
            f"UPDATE workflow_run_steps SET {assignments} WHERE TxId = ?",
            tuple(values),
        )

    def _hold(self, seconds: float) -> bool:
        end = time.monotonic() + max(0.0, float(seconds))
        while time.monotonic() < end:
            if self._stop_event.is_set():
                return False
            if self.virtual.state.get("e_stopped"):
                raise RuntimeError("Virtual E-stop active")
            if not self.virtual.state.get("connected"):
                raise RuntimeError("Virtual arm disconnected")
            time.sleep(min(0.1, max(0.0, end - time.monotonic())))
        return not self._stop_event.is_set()

    def _prepare_virtual(self) -> None:
        snap = self.virtual.connect()
        if not snap.get("connected"):
            raise RuntimeError("Virtual arm connect failed")
        if snap.get("e_stopped"):
            self.virtual.reset_estop()
        demo_key = self._targets["demo_key"]
        demo = self.virtual.demos.get(demo_key)
        if demo is None:
            raise KeyError(f"Unknown virtual demo_key: {demo_key}")
        supported = demo.get("supported_models") or []
        if self.virtual.state["model_key"] not in supported and supported:
            select = self.virtual.select_model(
                supported[0], session_owner=SESSION_WORKFLOW
            )
            if select.get("model_key") != supported[0]:
                raise RuntimeError(
                    f"Unable to select supported virtual model: {supported[0]}"
                )
        selected = self.virtual.select_demo(
            demo_key, session_owner=SESSION_WORKFLOW
        )
        if selected.get("last_result_key") == "vd_demo_model_unsupported":
            raise RuntimeError("Virtual demo model unsupported for workflow run")
        if selected.get("selected_demo_key") != demo_key:
            raise RuntimeError(f"Unable to select virtual demo: {demo_key}")
        started = self.virtual.start_demo(session_owner=SESSION_WORKFLOW)
        if not started.get("demo_started"):
            raise RuntimeError(
                started.get("last_message")
                or started.get("last_result_key")
                or "Unable to start virtual demo session"
            )
        self.virtual.mark_demo_preflight(True, "workflow virtual runner")

    def _finish_virtual(self, *, aborted: bool) -> None:
        try:
            if aborted:
                try:
                    self.virtual.update_demo_runtime(
                        {"aborted": True, "phase": "Aborted"}
                    )
                except Exception:
                    pass
            self.virtual.reset_demo_forced()
        except Exception:
            try:
                self.virtual.release_session(SESSION_WORKFLOW)
            except Exception:
                pass

    def _target_def(self, target_key: Any) -> dict[str, Any] | None:
        if target_key and str(target_key) in self._targets["targets"]:
            return self._targets["targets"][str(target_key)]
        return None

    def _phase_names(self, target_def: dict[str, Any] | None) -> list[str]:
        if not target_def:
            return []
        phases = target_def.get("phases")
        if isinstance(phases, list) and phases:
            return [str(p) for p in phases]
        phase = target_def.get("phase")
        if phase:
            return [str(phase)]
        return []

    def _wait_animation(
        self, step: dict[str, Any], target_def: dict[str, Any] | None
    ) -> str:
        phases = self._phase_names(target_def)
        with self._anim_lock:
            self._anim_seq += 1
            seq = self._anim_seq
            self._anim_result = None
            self._anim_ack.clear()
            self._anim_cue = {
                "run_txid": step.get("_run_txid"),
                "step_txid": step["TxId"],
                "seq": seq,
                "step_no": step["StepNo"],
                "step_name": step["StepName"],
                "action_type": step["ActionType"],
                "target_key": step.get("TargetKey"),
                "phases": phases,
                "demo_key": self._targets["demo_key"],
            }
        if self._animation_auto_ack:
            # Schematic fallback used by unit tests (no browser 3D client).
            phase = phases[0] if phases else None
            if phase:
                self.virtual.update_demo_runtime({"phase": phase})
            hold = 0.05
            if step.get("TimeoutSec") is not None and str(step["TimeoutSec"]).strip():
                hold = min(float(step["TimeoutSec"]), 0.2)
            if not self._hold(hold):
                return STEP_STOPPED
            with self._anim_lock:
                self._anim_cue = None
            return STEP_COMPLETED

        deadline = time.monotonic() + float(self._animation_timeout_sec)
        while True:
            if self._stop_event.is_set():
                with self._anim_lock:
                    self._anim_cue = None
                return STEP_STOPPED
            if self.virtual.state.get("e_stopped"):
                with self._anim_lock:
                    self._anim_cue = None
                raise RuntimeError("Virtual E-stop active")
            if not self.virtual.state.get("connected"):
                with self._anim_lock:
                    self._anim_cue = None
                raise RuntimeError("Virtual arm disconnected")
            if self._anim_ack.wait(0.1):
                with self._anim_lock:
                    result = dict(self._anim_result or {})
                    self._anim_cue = None
                if not result.get("ok"):
                    err = result.get("error") or "animation failed"
                    if err == "stopped":
                        return STEP_STOPPED
                    raise RuntimeError(str(err))
                return STEP_COMPLETED
            if time.monotonic() >= deadline:
                with self._anim_lock:
                    self._anim_cue = None
                raise RuntimeError("Animation ack timeout")

    def _apply_action(self, step: dict[str, Any]) -> str:
        action = self.normalize_action(step["ActionType"])
        target_def = self._target_def(step.get("TargetKey"))
        # All action types that map to demo phases wait for 3D client (or auto-ack).
        if action in ("MOVE", "GRIP", "END") and (
            self._phase_names(target_def) or not self._animation_auto_ack
        ):
            return self._wait_animation(step, target_def)
        if action == "WAIT":
            hold = 1.0
            if step.get("TimeoutSec") is not None and str(step["TimeoutSec"]).strip():
                hold = float(step["TimeoutSec"])
            elif target_def and target_def.get("hold_sec") is not None:
                hold = float(target_def["hold_sec"])
            if not self._hold(hold):
                return STEP_STOPPED
            return STEP_COMPLETED
        if action in ("MOVE", "GRIP", "END"):
            return self._wait_animation(step, target_def)
        raise ValueError(f"Unsupported action: {action}")

    def _skip_pending(
        self, step_rows: list[Any], *, message: str, status: str = STEP_SKIPPED
    ) -> None:
        for later in step_rows:
            cur = self.store.fetchone(
                "SELECT Status FROM workflow_run_steps WHERE TxId = ?",
                (later["TxId"],),
            )
            if cur and cur["Status"] == STEP_PENDING:
                self._update_run_step(
                    later["TxId"],
                    Status=status,
                    FinishedAt=self._now(),
                    ResultMessage=message,
                )

    def _run_loop(self, run_txid: int, workflow_txid: int) -> None:
        final_status = STATUS_COMPLETED
        error_message = None
        try:
            self._prepare_virtual()
            step_rows = self.store.fetchall(
                """
                SELECT rs.*, ws.TimeoutSec AS TimeoutSec
                FROM workflow_run_steps rs
                LEFT JOIN workflow_steps ws ON ws.TxId = rs.WorkflowStepTxId
                WHERE rs.RunTxId = ?
                ORDER BY rs.StepNo ASC, rs.TxId ASC
                """,
                (run_txid,),
            )
            done = 0
            for row in step_rows:
                if self._stop_event.is_set():
                    final_status = STATUS_STOPPED
                    self._update_run_step(
                        row["TxId"],
                        Status=STEP_STOPPED,
                        FinishedAt=self._now(),
                        ResultMessage="stopped",
                    )
                    self._skip_pending(
                        step_rows, message="skipped after stop"
                    )
                    break
                self._update_run(
                    run_txid,
                    CurrentStepNo=row["StepNo"],
                    CurrentStepName=row["StepName"],
                    ProgressDone=done,
                )
                self._update_run_step(
                    row["TxId"],
                    Status=STEP_RUNNING,
                    StartedAt=self._now(),
                )
                payload = dict(row)
                payload["_run_txid"] = run_txid
                try:
                    result = self._apply_action(payload)
                except Exception as exc:
                    final_status = STATUS_FAILED
                    error_message = str(exc)
                    self._update_run_step(
                        row["TxId"],
                        Status=STEP_ERROR,
                        FinishedAt=self._now(),
                        ResultMessage=error_message,
                    )
                    self._skip_pending(
                        step_rows, message="skipped after error"
                    )
                    break
                if result == STEP_STOPPED:
                    final_status = STATUS_STOPPED
                    self._update_run_step(
                        row["TxId"],
                        Status=STEP_STOPPED,
                        FinishedAt=self._now(),
                        ResultMessage="stopped",
                    )
                    self._skip_pending(
                        step_rows, message="skipped after stop"
                    )
                    break
                done += 1
                self._update_run_step(
                    row["TxId"],
                    Status=STEP_COMPLETED,
                    FinishedAt=self._now(),
                    ResultMessage="ok",
                )
                self._update_run(run_txid, ProgressDone=done)
                if self.normalize_action(row["ActionType"]) == "END":
                    self._skip_pending(
                        step_rows, message="skipped after END"
                    )
                    break
            else:
                final_status = STATUS_COMPLETED
        except Exception as exc:
            final_status = STATUS_FAILED
            error_message = str(exc)
        finally:
            aborted = final_status in (STATUS_STOPPED, STATUS_FAILED)
            try:
                self._finish_virtual(aborted=aborted)
            except Exception:
                pass
            self._update_run(
                run_txid,
                Status=final_status,
                ErrorMessage=error_message,
                FinishedAt=self._now(),
                ProgressDone=self.store.fetchone(
                    """
                    SELECT COUNT(*) AS n FROM workflow_run_steps
                    WHERE RunTxId = ? AND Status = ?
                    """,
                    (run_txid, STEP_COMPLETED),
                )["n"],
            )
            with self._lock:
                if self._active_run_txid == run_txid:
                    self._active_run_txid = None
                    self._thread = None
                self._control_state = final_status
                with self._anim_lock:
                    self._anim_cue = None
