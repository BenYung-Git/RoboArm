from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Any

from app.services.ui_service import UiService
from app.storage.config_store import resolve_path
from app.storage.json_store import load_json

RESULT_OK = "vd_result_ok"
RESULT_NOT_CONNECTED = "vd_result_not_connected"
RESULT_ESTOP = "vd_result_estop"
RESULT_INVALID_JOINTS = "vd_result_invalid_joints"
RESULT_NOT_IMPLEMENTED = "vd_result_not_implemented"
RESULT_ABORTED = "vd_result_aborted"
RESULT_LIMIT = "vd_result_joint_limit"
RESULT_DEMO_BLOCKED = "vd_demo_blocked"
RESULT_DEMO_NEEDS_RESET = "vd_demo_needs_reset"
RESULT_DEMO_UNSUPPORTED = "vd_demo_model_unsupported"
RESULT_UNREACHABLE = "vd_result_unreachable"
RESULT_PREFLIGHT_OK = "vd_result_preflight_ok"
RESULT_COMPLETE_REJECTED = "vd_result_complete_rejected"

DEMO_IDLE = "idle"
DEMO_RUNNING = "running"
DEMO_NEEDS_RESET = "needs_reset"
DEMO_COMPLETED = "completed"


class VirtualDemoService:
    """In-memory schematic virtual demo session (no SDK / no official CAD)."""

    def __init__(self, ui_service: UiService) -> None:
        self.ui = ui_service
        self.config_path = resolve_path(ui_service.config["virtual_demo_config_path"])
        self.config = self._load_root_config()
        self.models = self._load_models()
        self.demos = self._load_carry_demos()
        self.demo_order = list(self.demos.keys())
        self._apply_model(self.config["default_model_key"], reset_logs=True)

    def _load_root_config(self) -> dict[str, Any]:
        data = load_json(self.config_path)
        required = (
            "default_model_key",
            "dof",
            "dio_pin_count",
            "joint_validation",
            "models_path",
            "model_keys",
        )
        for key in required:
            if key not in data:
                raise KeyError(f"Missing virtual_demo config key: {key}")
        if "carry_demo_paths" not in data and "carry_demo_path" not in data:
            raise KeyError("Missing virtual_demo config key: carry_demo_paths")
        if int(data["dof"]) != 6:
            raise ValueError("virtual_demo dof must be 6 for this version")
        if data["joint_validation"] != "finite_six_only":
            raise ValueError(
                f"Unsupported joint_validation: {data['joint_validation']}"
            )
        return data

    def _carry_demo_paths(self) -> list[str]:
        paths = self.config.get("carry_demo_paths")
        if isinstance(paths, list) and paths:
            return [str(p) for p in paths]
        return [str(self.config["carry_demo_path"])]

    def _validate_table(self, table: dict[str, Any], label: str) -> None:
        for key in (
            "top_z_m",
            "thickness_m",
            "radius_m",
            "edge_margin_m",
            "center_xy_m",
            "legs",
        ):
            if key not in table or table[key] is None:
                raise ValueError(f"carry demo {label}.{key} must be set (non-null)")

    def _validate_carry_demo(self, data: dict[str, Any]) -> dict[str, Any]:
        for key in (
            "demo_key",
            "label_key",
            "supported_models",
            "object",
            "gripper",
            "motion",
            "derived",
        ):
            if key not in data:
                raise KeyError(f"Missing carry demo key: {key}")
        pattern = data.get("pattern") or "vertical_inplace"
        if pattern == "front_back_transfer":
            if "pick_table" not in data or "place_table" not in data:
                raise KeyError("front_back_transfer requires pick_table and place_table")
            self._validate_table(data["pick_table"], "pick_table")
            self._validate_table(data["place_table"], "place_table")
            # Keep demo.table as pick alias for shared helpers.
            if "table" not in data or data["table"] is None:
                data["table"] = dict(data["pick_table"])
            else:
                self._validate_table(data["table"], "table")
            if "place_xy_m" not in data["object"] or data["object"]["place_xy_m"] is None:
                data["object"]["place_xy_m"] = list(data["place_table"]["center_xy_m"])
        else:
            if "table" not in data:
                raise KeyError("Missing carry demo key: table")
            self._validate_table(data["table"], "table")
        table = data["table"]
        derived = data["derived"]
        for key in (
            "object_center_z_m",
            "object_bottom_z_m",
            "gap_contact_for_object_m",
            "table_top_area_m2",
            "table_usable_area_m2",
            "object_base_area_m2",
        ):
            if key not in derived or derived[key] is None:
                raise ValueError(f"carry demo derived.{key} must be set (non-null)")
        expected_center = float(table["top_z_m"]) + float(data["object"]["height_m"]) / 2.0
        if abs(float(derived["object_center_z_m"]) - expected_center) > 1e-9:
            raise ValueError("derived.object_center_z_m inconsistent with table/object")
        if abs(float(derived["object_bottom_z_m"]) - float(table["top_z_m"])) > 1e-9:
            raise ValueError("derived.object_bottom_z_m must equal table.top_z_m")
        return data

    def _load_carry_demos(self) -> dict[str, dict[str, Any]]:
        demos: dict[str, dict[str, Any]] = {}
        for rel in self._carry_demo_paths():
            path = resolve_path(rel)
            data = self._validate_carry_demo(load_json(path))
            key = data["demo_key"]
            if key in demos:
                raise ValueError(f"Duplicate demo_key: {key}")
            demos[key] = data
        if not demos:
            raise ValueError("No carry demos loaded")
        return demos

    @property
    def carry_demo(self) -> dict[str, Any]:
        """Active demo when selected; otherwise first catalog entry (gap defaults)."""
        key = self.state.get("selected_demo_key") if hasattr(self, "state") else None
        if key and key in self.demos:
            return self.demos[key]
        return self.demos[self.demo_order[0]]

    def _load_models(self) -> dict[str, dict[str, Any]]:
        models_dir = resolve_path(self.config["models_path"])
        models: dict[str, dict[str, Any]] = {}
        for key in self.config["model_keys"]:
            path = Path(models_dir) / f"{key}.json"
            model = load_json(path)
            for required in (
                "model_key",
                "brand",
                "model",
                "robot_id",
                "label_key",
                "home_joints_deg",
                "initial_joints_deg",
                "joint_limits_deg",
                "animation_deg_per_sec",
                "segments",
                "geometry_style",
                "platform_radius",
            ):
                if required not in model:
                    raise KeyError(f"Missing model key {required} in {path}")
            if model["model_key"] != key:
                raise ValueError(f"model_key mismatch in {path}")
            if not model.get("schematic", False):
                raise ValueError(f"Only schematic models allowed: {key}")
            models[key] = model
        return models

    def _apply_model(self, model_key: str, reset_logs: bool = False) -> None:
        if model_key not in self.models:
            raise KeyError(f"Unknown model_key: {model_key}")
        self.model = self.models[model_key]
        pin_count = int(self.config["dio_pin_count"])
        home = [float(v) for v in self.model["initial_joints_deg"]]
        self.state: dict[str, Any] = {
            "model_key": model_key,
            "robot_id": self.model["robot_id"],
            "brand": self.model["brand"],
            "model": self.model["model"],
            "connected": False,
            "e_stopped": False,
            "is_moving": False,
            "current_joints": list(home),
            "target_joints": list(home),
            "digital_outputs": {str(i): False for i in range(pin_count)},
            "digital_inputs": {str(i): False for i in range(pin_count)},
            "active_action_key": None,
            "motion_id": 0,
            "selected_demo_key": None,
            "demo_run_state": DEMO_IDLE,
            "demo_phase": None,
            "demo_grasped": False,
            "demo_gap_m": float(self.carry_demo["gripper"]["gap_fully_open_m"]),
            "demo_object_pose": None,
        }
        self._reset_demo_object_pose()
        if reset_logs or not hasattr(self, "logs"):
            self.logs = []

    def _reset_demo_object_pose(self) -> None:
        selected = self.state.get("selected_demo_key")
        if not selected or selected not in self.demos:
            self.state["demo_object_pose"] = None
            self.state["demo_grasped"] = False
            self.state["demo_gap_m"] = float(
                self.demos[self.demo_order[0]]["gripper"]["gap_fully_open_m"]
            )
            self.state["demo_phase"] = None
            return
        demo = self.demos[selected]
        obj = demo["object"]
        table = demo.get("pick_table") or demo["table"]
        self.state["demo_object_pose"] = {
            "center_xyz_m": [
                float(obj["center_xy_m"][0]),
                float(obj["center_xy_m"][1]),
                float(table["top_z_m"]) + float(obj["height_m"]) / 2.0,
            ],
            "axis_world": [float(v) for v in obj["axis_world"]],
        }
        self.state["demo_grasped"] = False
        self.state["demo_gap_m"] = float(demo["gripper"]["gap_fully_open_m"])
        self.state["demo_phase"] = None

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _append_log(self, action_key: str, result_key: str) -> None:
        self.logs.insert(
            0,
            {
                "time": self._now_iso(),
                "action_key": action_key,
                "result_key": result_key,
            },
        )
        if len(self.logs) > 100:
            self.logs = self.logs[:100]

    def _validate_joints(self, joints: list[Any]) -> list[float]:
        dof = int(self.config["dof"])
        if not isinstance(joints, list) or len(joints) != dof:
            raise ValueError(RESULT_INVALID_JOINTS)
        parsed: list[float] = []
        limits = self.model["joint_limits_deg"]
        for index, value in enumerate(joints):
            number = float(value)
            if not isfinite(number):
                raise ValueError(RESULT_INVALID_JOINTS)
            low, high = limits[index]
            if number < float(low) or number > float(high):
                raise ValueError(RESULT_LIMIT)
            parsed.append(number)
        return parsed

    def _require_motion_allowed(self) -> str | None:
        if not self.state["connected"]:
            return RESULT_NOT_CONNECTED
        if self.state["e_stopped"]:
            return RESULT_ESTOP
        return None

    def _require_manual_allowed(self) -> str | None:
        blocked = self._require_motion_allowed()
        if blocked is not None:
            return blocked
        if self.state["demo_run_state"] == DEMO_RUNNING:
            return RESULT_DEMO_BLOCKED
        if self.state["demo_run_state"] == DEMO_NEEDS_RESET:
            return RESULT_DEMO_NEEDS_RESET
        return None

    def _abort_motion_if_needed(self, reason_key: str) -> None:
        if self.state["is_moving"]:
            action = self.state["active_action_key"] or "vd_action_move_j"
            self.state["is_moving"] = False
            self.state["active_action_key"] = None
            self.state["target_joints"] = list(self.state["current_joints"])
            self._append_log(action, reason_key)

    def _abort_demo_if_running(self, reason_key: str) -> None:
        if self.state["demo_run_state"] == DEMO_RUNNING:
            self.state["demo_run_state"] = DEMO_NEEDS_RESET
            self.state["demo_phase"] = "Aborted"
            self._append_log("vd_action_run_demo", reason_key)

    def get_model_catalog(self, language: str | None = None) -> list[dict[str, str]]:
        lang = language if language is not None else self.ui.get_prefs()["language"]
        items = []
        for key in self.config["model_keys"]:
            model = self.models[key]
            items.append(
                {
                    "model_key": key,
                    "label": self.ui.t(model["label_key"], lang),
                    "brand": model["brand"],
                    "model": model["model"],
                }
            )
        return items

    def get_snapshot(self, language: str | None = None) -> dict[str, Any]:
        lang = language if language is not None else self.ui.get_prefs()["language"]
        labels = {
            "robot": self.ui.t("vd_label_robot", lang),
            "model_select": self.ui.t("vd_label_model_select", lang),
            "connected": self.ui.t("vd_label_connected", lang),
            "e_stopped": self.ui.t("vd_label_e_stopped", lang),
            "joints": self.ui.t("vd_label_joints", lang),
            "target_joints": self.ui.t("vd_label_target_joints", lang),
            "current_joints": self.ui.t("vd_label_current_joints", lang),
            "pose": self.ui.t("vd_label_pose", lang),
            "pose_pending": self.ui.t("vd_pose_pending_fk", lang),
            "do": self.ui.t("vd_label_do", lang),
            "di": self.ui.t("vd_label_di", lang),
            "connect": self.ui.t("vd_btn_connect", lang),
            "disconnect": self.ui.t("vd_btn_disconnect", lang),
            "estop": self.ui.t("vd_btn_estop", lang),
            "reset_estop": self.ui.t("vd_btn_reset_estop", lang),
            "move_home": self.ui.t("vd_btn_move_home", lang),
            "move_j": self.ui.t("vd_btn_move_j", lang),
            "move_l": self.ui.t("vd_btn_move_l", lang),
            "move_servo": self.ui.t("vd_btn_move_servo", lang),
            "move_line": self.ui.t("vd_btn_move_line", lang),
            "sync_move": self.ui.t("vd_btn_sync_move", lang),
            "weld": self.ui.t("vd_btn_weld", lang),
            "torch": self.ui.t("vd_btn_torch", lang),
            "log_title": self.ui.t("vd_label_log", lang),
            "log_time": self.ui.t("vd_label_log_time", lang),
            "log_action": self.ui.t("vd_label_log_action", lang),
            "log_result": self.ui.t("vd_label_log_result", lang),
            "status_yes": self.ui.t("vd_status_yes", lang),
            "status_no": self.ui.t("vd_status_no", lang),
            "section_robot": self.ui.t("vd_section_robot", lang),
            "section_status": self.ui.t("vd_section_status", lang),
            "section_motion": self.ui.t("vd_section_motion", lang),
            "section_io": self.ui.t("vd_section_io", lang),
            "section_unimplemented": self.ui.t("vd_section_unimplemented", lang),
            "section_3d": self.ui.t("vd_section_3d", lang),
            "joint_hint": self.ui.t("vd_joint_input_hint", lang),
            "not_implemented": self.ui.t(RESULT_NOT_IMPLEMENTED, lang),
            "schematic_disclaimer": self.ui.t("vd_schematic_disclaimer", lang),
            "demo_limits_note": self.ui.t("vd_demo_limits_note", lang),
            "is_moving": self.ui.t("vd_label_is_moving", lang),
            "demo_select": self.ui.t("vd_label_demo_select", lang),
            "demo_none": self.ui.t("vd_demo_none", lang),
            "run_demo": self.ui.t("vd_btn_run_demo", lang),
            "reset_demo": self.ui.t("vd_btn_reset_demo", lang),
            "demo_phase": self.ui.t("vd_demo_phase", lang),
            "demo_needs_reset": self.ui.t("vd_demo_needs_reset", lang),
            "show_joint_labels": self.ui.t("vd_label_show_joint_labels", lang),
            "demo_speed": self.ui.t("vd_demo_speed", lang),
            "demo_speed_x1": self.ui.t("vd_demo_speed_x1", lang),
            "demo_speed_x2": self.ui.t("vd_demo_speed_x2", lang),
            "demo_speed_x3": self.ui.t("vd_demo_speed_x3", lang),
        }
        logs = []
        for item in self.logs:
            logs.append(
                {
                    "time": item["time"],
                    "action": self.ui.t(item["action_key"], lang),
                    "result": self.ui.t(item["result_key"], lang),
                    "result_key": item["result_key"],
                }
            )
        return {
            "model_key": self.state["model_key"],
            "models": self.get_model_catalog(lang),
            "robot_id": self.state["robot_id"],
            "brand": self.state["brand"],
            "model": self.state["model"],
            "display_name": f"{self.state['brand']} {self.state['model']}",
            "connected": self.state["connected"],
            "e_stopped": self.state["e_stopped"],
            "is_moving": self.state["is_moving"],
            "current_joints": list(self.state["current_joints"]),
            "target_joints": list(self.state["target_joints"]),
            "joints": list(self.state["current_joints"]),
            "pose_text": labels["pose_pending"],
            "digital_outputs": dict(self.state["digital_outputs"]),
            "digital_inputs": dict(self.state["digital_inputs"]),
            "logs": logs,
            "labels": labels,
            "dof": int(self.config["dof"]),
            "dio_pin_count": int(self.config["dio_pin_count"]),
            "animation_deg_per_sec": float(self.model["animation_deg_per_sec"]),
            "joint_limits_deg": self.model["joint_limits_deg"],
            "viewer_model": {
                "model_key": self.model["model_key"],
                "geometry_style": self.model["geometry_style"],
                "base_color": self.model["base_color"],
                "link_color": self.model["link_color"],
                "joint_color": self.model["joint_color"],
                "accent_color": self.model["accent_color"],
                "platform_radius": float(self.model["platform_radius"]),
                "segments": self.model["segments"],
                "home_joints_deg": self.model["home_joints_deg"],
                "joint_limits_deg": self.model["joint_limits_deg"],
                "schematic": True,
                "unverified_demo": True,
            },
            "carry_demo": (
                self.demos[self.state["selected_demo_key"]]
                if self.state["selected_demo_key"] in self.demos
                else None
            ),
            "demos": [
                {
                    "demo_key": key,
                    "label": self.ui.t(self.demos[key]["label_key"], lang),
                    "supported_models": self.demos[key]["supported_models"],
                }
                for key in self.demo_order
            ],
            "selected_demo_key": self.state["selected_demo_key"],
            "demo_run_state": self.state["demo_run_state"],
            "demo_phase": self.state["demo_phase"],
            "demo_grasped": self.state["demo_grasped"],
            "demo_gap_m": self.state["demo_gap_m"],
            "demo_object_pose": (
                dict(self.state["demo_object_pose"])
                if self.state["demo_object_pose"] is not None
                else None
            ),
        }

    def select_model(self, model_key: str) -> dict[str, Any]:
        self._abort_motion_if_needed(RESULT_ABORTED)
        self._abort_demo_if_running(RESULT_ABORTED)
        prev_demo = self.state.get("selected_demo_key")
        self._apply_model(model_key, reset_logs=False)
        if prev_demo and prev_demo in self.demos:
            if self.state["model_key"] not in self.demos[prev_demo]["supported_models"]:
                self.state["selected_demo_key"] = None
                self.state["demo_run_state"] = DEMO_IDLE
            else:
                self.state["selected_demo_key"] = prev_demo
            self._reset_demo_object_pose()
        self._append_log("vd_action_select_model", RESULT_OK)
        return self.get_snapshot()

    def select_demo(self, demo_key: str | None) -> dict[str, Any]:
        self._abort_motion_if_needed(RESULT_ABORTED)
        self._abort_demo_if_running(RESULT_ABORTED)
        if demo_key in (None, "", "none"):
            self.state["selected_demo_key"] = None
            self.state["demo_run_state"] = DEMO_IDLE
            self._reset_demo_object_pose()
            self._append_log("vd_action_select_demo", RESULT_OK)
            return self.get_snapshot()
        if demo_key not in self.demos:
            raise KeyError(f"Unknown demo_key: {demo_key}")
        demo = self.demos[demo_key]
        if self.state["model_key"] not in demo["supported_models"]:
            self._append_log("vd_action_select_demo", RESULT_DEMO_UNSUPPORTED)
            snapshot = self.get_snapshot()
            snapshot["last_result_key"] = RESULT_DEMO_UNSUPPORTED
            try:
                snapshot["last_message"] = self.ui.t(RESULT_DEMO_UNSUPPORTED)
            except (KeyError, ValueError):
                snapshot["last_message"] = RESULT_DEMO_UNSUPPORTED
            return snapshot
        self.state["selected_demo_key"] = demo_key
        self.state["demo_run_state"] = DEMO_IDLE
        self._reset_demo_object_pose()
        self._append_log("vd_action_select_demo", RESULT_OK)
        return self.get_snapshot()

    def _demo_reject_snapshot(self, result_key: str, hint: str | None = None) -> dict[str, Any]:
        """Reject demo start with last_result_key + visible last_message (no silent fail)."""
        self._append_log("vd_action_run_demo", result_key)
        snapshot = self.get_snapshot()
        snapshot["demo_started"] = False
        snapshot["last_result_key"] = result_key
        try:
            base = self.ui.t(result_key)
        except (KeyError, ValueError):
            base = result_key
        snapshot["last_message"] = f"{base} {hint}".strip() if hint else base
        return snapshot

    def start_demo(self) -> dict[str, Any]:
        selected = self.state["selected_demo_key"]
        if not selected or selected not in self.demos:
            raise ValueError("No carry demo selected")
        if self.state["model_key"] not in self.demos[selected]["supported_models"]:
            return self._demo_reject_snapshot(
                RESULT_DEMO_UNSUPPORTED,
                "請切換至支援型號（如 ROKAE CR7）後再執行。",
            )
        if self.state["demo_run_state"] == DEMO_RUNNING:
            return self._demo_reject_snapshot(
                RESULT_DEMO_BLOCKED,
                "請等待結束，或按緊急停止／重置示範。",
            )
        if self.state["demo_run_state"] == DEMO_NEEDS_RESET:
            return self._demo_reject_snapshot(
                RESULT_DEMO_NEEDS_RESET,
                "請先按「重置示範」。",
            )
        blocked = self._require_motion_allowed()
        if blocked is not None:
            hint = None
            if blocked == RESULT_NOT_CONNECTED:
                hint = "請先按「連線」。"
            elif blocked == RESULT_ESTOP:
                hint = "請先按「解除緊急停止」。"
            return self._demo_reject_snapshot(blocked, hint)
        self.state["demo_run_state"] = DEMO_RUNNING
        self.state["demo_phase"] = "Preflight"
        self._append_log("vd_action_run_demo", RESULT_OK)
        snapshot = self.get_snapshot()
        snapshot["demo_started"] = True
        return snapshot

    def mark_demo_preflight(self, ok: bool, detail: str | None = None) -> dict[str, Any]:
        if self.state["demo_run_state"] != DEMO_RUNNING:
            return self.get_snapshot()
        if ok:
            self._append_log("vd_action_run_demo", RESULT_PREFLIGHT_OK)
            self.state["demo_phase"] = "Home"
        else:
            self.state["demo_run_state"] = DEMO_NEEDS_RESET
            self.state["demo_phase"] = "PreflightFailed"
            self._append_log("vd_action_run_demo", RESULT_UNREACHABLE)
            snapshot = self.get_snapshot()
            snapshot["last_result_key"] = RESULT_UNREACHABLE
            if detail:
                snapshot["last_message"] = detail
            return snapshot
        return self.get_snapshot()

    def update_demo_runtime(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_state = self.state["demo_run_state"]

        def _apply_pose_fields() -> None:
            if "grasped" in payload:
                self.state["demo_grasped"] = bool(payload["grasped"])
            if "gap_m" in payload:
                self.state["demo_gap_m"] = float(payload["gap_m"])
            if "object_pose" in payload and payload["object_pose"] is not None:
                pose = payload["object_pose"]
                self.state["demo_object_pose"] = {
                    "center_xyz_m": [float(v) for v in pose["center_xyz_m"]],
                    "axis_world": [float(v) for v in pose["axis_world"]],
                }

        # Delayed completed/phase must not overwrite abort/reset/completed.
        if run_state != DEMO_RUNNING:
            if payload.get("aborted") and run_state == DEMO_NEEDS_RESET:
                _apply_pose_fields()
                return self.get_snapshot()
            snapshot = self.get_snapshot()
            snapshot["runtime_ignored"] = True
            return snapshot

        if "phase" in payload and not payload.get("completed"):
            self.state["demo_phase"] = payload["phase"]
        _apply_pose_fields()

        if payload.get("aborted"):
            self._abort_motion_if_needed(RESULT_ABORTED)
            self.state["demo_run_state"] = DEMO_NEEDS_RESET
            self.state["demo_phase"] = payload.get("phase") or "Aborted"
            self._append_log("vd_action_run_demo", RESULT_ABORTED)
            return self.get_snapshot()
        if payload.get("completed"):
            rejected = self._reject_completed_if_invalid(payload)
            if rejected is not None:
                return rejected
            self.state["demo_run_state"] = DEMO_COMPLETED
            self.state["demo_phase"] = "Completed"
            self._append_log("vd_action_run_demo", RESULT_OK)
        return self.get_snapshot()

    def _reject_completed_if_invalid(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if self.state["demo_run_state"] != DEMO_RUNNING:
            snapshot = self.get_snapshot()
            snapshot["last_result_key"] = RESULT_COMPLETE_REJECTED
            snapshot["last_message"] = "completed rejected: not running"
            return snapshot
        if self.state["is_moving"]:
            snapshot = self.get_snapshot()
            snapshot["last_result_key"] = RESULT_COMPLETE_REJECTED
            snapshot["last_message"] = "completed rejected: still moving"
            return snapshot
        if self.state["demo_grasped"]:
            snapshot = self.get_snapshot()
            snapshot["last_result_key"] = RESULT_COMPLETE_REJECTED
            snapshot["last_message"] = "completed rejected: still grasped"
            return snapshot
        open_gap = float(self.carry_demo["gripper"]["gap_fully_open_m"])
        if abs(float(self.state["demo_gap_m"]) - open_gap) > 1e-6:
            snapshot = self.get_snapshot()
            snapshot["last_result_key"] = RESULT_COMPLETE_REJECTED
            snapshot["last_message"] = "completed rejected: gap not open"
            return snapshot
        home = [float(v) for v in self.model["home_joints_deg"]]
        tol = float(self.carry_demo["motion"].get("home_joint_tol_deg", 0.5))
        cur = self.state["current_joints"]
        home_err = max(abs(cur[i] - home[i]) for i in range(len(home)))
        if home_err > tol:
            snapshot = self.get_snapshot()
            snapshot["last_result_key"] = RESULT_COMPLETE_REJECTED
            snapshot["last_message"] = f"completed rejected: not home err={home_err:.4f}"
            return snapshot
        pose = self.state["demo_object_pose"]
        demo = self.carry_demo
        obj = demo["object"]
        table = demo.get("place_table") or demo["table"]
        motion = demo["motion"]
        bottom = float(pose["center_xyz_m"][2]) - float(obj["height_m"]) / 2.0
        if abs(bottom - float(table["top_z_m"])) > float(motion["place_bottom_tol_m"]):
            snapshot = self.get_snapshot()
            snapshot["last_result_key"] = RESULT_COMPLETE_REJECTED
            snapshot["last_message"] = "completed rejected: place bottom"
            return snapshot
        if obj.get("place_xy_m") is not None:
            place_xy = obj["place_xy_m"]
        elif demo.get("place_table") is not None:
            place_xy = demo["place_table"]["center_xy_m"]
        else:
            place_xy = obj["center_xy_m"]
        dx = float(pose["center_xyz_m"][0]) - float(place_xy[0])
        dy = float(pose["center_xyz_m"][1]) - float(place_xy[1])
        if (dx * dx + dy * dy) ** 0.5 > float(motion["place_xy_tol_m"]):
            snapshot = self.get_snapshot()
            snapshot["last_result_key"] = RESULT_COMPLETE_REJECTED
            snapshot["last_message"] = "completed rejected: place xy"
            return snapshot
        return None

    def reset_demo(self) -> dict[str, Any]:
        self._abort_motion_if_needed(RESULT_ABORTED)
        self.state["demo_run_state"] = DEMO_IDLE
        self._reset_demo_object_pose()
        home = [float(v) for v in self.model["initial_joints_deg"]]
        self.state["current_joints"] = list(home)
        self.state["target_joints"] = list(home)
        self._append_log("vd_action_reset_demo", RESULT_OK)
        return self.get_snapshot()

    def set_target_joints(self, joints: list[Any]) -> dict[str, Any]:
        blocked = self._require_manual_allowed()
        if blocked is not None:
            self._append_log("vd_action_set_target", blocked)
            snapshot = self.get_snapshot()
            snapshot["last_result_key"] = blocked
            return snapshot
        try:
            parsed = self._validate_joints(joints)
        except ValueError as exc:
            code = str(exc)
            self._append_log("vd_action_set_target", code)
            snapshot = self.get_snapshot()
            snapshot["last_result_key"] = code
            return snapshot
        self.state["target_joints"] = parsed
        return self.get_snapshot()

    def connect(self) -> dict[str, Any]:
        self.state["connected"] = True
        self._append_log("vd_action_connect", RESULT_OK)
        return self.get_snapshot()

    def disconnect(self) -> dict[str, Any]:
        self._abort_motion_if_needed(RESULT_ABORTED)
        self._abort_demo_if_running(RESULT_ABORTED)
        self.state["connected"] = False
        self._append_log("vd_action_disconnect", RESULT_OK)
        return self.get_snapshot()

    def emergency_stop(self) -> dict[str, Any]:
        self._abort_motion_if_needed(RESULT_ABORTED)
        self._abort_demo_if_running(RESULT_ABORTED)
        self.state["e_stopped"] = True
        self._append_log("vd_action_estop", RESULT_OK)
        return self.get_snapshot()

    def reset_estop(self) -> dict[str, Any]:
        self.state["e_stopped"] = False
        self._append_log("vd_action_reset_estop", RESULT_OK)
        return self.get_snapshot()

    def move_to_home(self) -> dict[str, Any]:
        blocked = self._require_manual_allowed()
        if blocked is not None:
            self._append_log("vd_action_move_home", blocked)
            snapshot = self.get_snapshot()
            snapshot["last_result_key"] = blocked
            return snapshot
        return self._start_move(
            "vd_action_move_home",
            [float(v) for v in self.model["home_joints_deg"]],
        )

    def move_j(
        self, joints: list[Any] | None = None, *, allow_during_demo: bool = False
    ) -> dict[str, Any]:
        if not allow_during_demo:
            blocked = self._require_manual_allowed()
            if blocked is not None:
                self._append_log("vd_action_move_j", blocked)
                snapshot = self.get_snapshot()
                snapshot["last_result_key"] = blocked
                return snapshot
        else:
            blocked = self._require_motion_allowed()
            if blocked is not None:
                self._append_log("vd_action_move_j", blocked)
                snapshot = self.get_snapshot()
                snapshot["last_result_key"] = blocked
                return snapshot
            if self.state["demo_run_state"] != DEMO_RUNNING:
                self._append_log("vd_action_move_j", RESULT_DEMO_BLOCKED)
                snapshot = self.get_snapshot()
                snapshot["last_result_key"] = RESULT_DEMO_BLOCKED
                return snapshot
        if joints is None:
            target = list(self.state["target_joints"])
        else:
            try:
                target = self._validate_joints(joints)
            except ValueError as exc:
                code = str(exc)
                self._append_log("vd_action_move_j", code)
                snapshot = self.get_snapshot()
                snapshot["last_result_key"] = code
                return snapshot
            self.state["target_joints"] = target
        return self._start_move("vd_action_move_j", target)

    def _start_move(self, action_key: str, target: list[float]) -> dict[str, Any]:
        if self.state["is_moving"]:
            self._abort_motion_if_needed(RESULT_ABORTED)
        self.state["target_joints"] = list(target)
        self.state["is_moving"] = True
        self.state["active_action_key"] = action_key
        self.state["motion_id"] = int(self.state.get("motion_id") or 0) + 1
        snapshot = self.get_snapshot()
        snapshot["motion_started"] = True
        snapshot["motion_id"] = self.state["motion_id"]
        snapshot["last_result_key"] = "vd_result_motion_started"
        return snapshot

    def update_current_joints(self, joints: list[Any]) -> dict[str, Any]:
        if not self.state["is_moving"]:
            return self.get_snapshot()
        try:
            parsed = self._validate_joints(joints)
        except ValueError:
            return self.get_snapshot()
        self.state["current_joints"] = parsed
        return self.get_snapshot()

    def complete_motion(self, motion_id: int | None = None) -> dict[str, Any]:
        if not self.state["is_moving"]:
            snapshot = self.get_snapshot()
            snapshot["motion_ignored"] = True
            return snapshot
        if motion_id is not None and int(motion_id) != int(self.state.get("motion_id") or 0):
            snapshot = self.get_snapshot()
            snapshot["motion_ignored"] = True
            return snapshot
        # Do not complete into a finished/aborted demo from a stale client.
        if self.state["demo_run_state"] == DEMO_NEEDS_RESET:
            self._abort_motion_if_needed(RESULT_ABORTED)
            snapshot = self.get_snapshot()
            snapshot["motion_ignored"] = True
            return snapshot
        action = self.state["active_action_key"] or "vd_action_move_j"
        self.state["current_joints"] = list(self.state["target_joints"])
        self.state["is_moving"] = False
        self.state["active_action_key"] = None
        self._append_log(action, RESULT_OK)
        return self.get_snapshot()

    def abort_motion(self) -> dict[str, Any]:
        self._abort_motion_if_needed(RESULT_ABORTED)
        return self.get_snapshot()

    def set_do(self, pin: int, value: bool) -> dict[str, Any]:
        blocked = self._require_manual_allowed()
        if blocked is not None:
            self._append_log("vd_action_set_do", blocked)
            return self.get_snapshot()
        key = str(pin)
        if key not in self.state["digital_outputs"]:
            raise ValueError(f"Invalid DO pin: {pin}")
        self.state["digital_outputs"][key] = bool(value)
        self._append_log("vd_action_set_do", RESULT_OK)
        return self.get_snapshot()

    def set_di(self, pin: int, value: bool) -> dict[str, Any]:
        blocked = self._require_manual_allowed()
        if blocked is not None:
            self._append_log("vd_action_set_di", blocked)
            return self.get_snapshot()
        key = str(pin)
        if key not in self.state["digital_inputs"]:
            raise ValueError(f"Invalid DI pin: {pin}")
        self.state["digital_inputs"][key] = bool(value)
        self._append_log("vd_action_set_di", RESULT_OK)
        return self.get_snapshot()

    def not_implemented(self, action_key: str) -> dict[str, Any]:
        allowed = {
            "vd_action_move_l",
            "vd_action_move_servo",
            "vd_action_move_line",
            "vd_action_sync_move",
            "vd_action_weld",
            "vd_action_torch",
        }
        if action_key not in allowed:
            raise ValueError(f"Unknown not-implemented action: {action_key}")
        self._append_log(action_key, RESULT_NOT_IMPLEMENTED)
        snapshot = self.get_snapshot()
        snapshot["last_message"] = snapshot["labels"]["not_implemented"]
        snapshot["last_result_key"] = RESULT_NOT_IMPLEMENTED
        return snapshot
