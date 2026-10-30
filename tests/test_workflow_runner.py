"""Isolated tests for virtual workflow runner (never use formal DB)."""

from __future__ import annotations

import gc
import sys
import tempfile
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.maint_service import MaintService
from app.services.ui_service import UiService
from app.services.virtual_demo_service import (
    RESULT_SESSION_BUSY,
    SESSION_VIRTUAL_DEMO,
    VirtualDemoService,
)
from app.services.workflow_runner_service import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_READY,
    STATUS_STOPPED,
    WorkflowRunnerService,
)
from app.storage.config_store import resolve_path


class WorkflowRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmp.name) / "workflow_runner_test.db"
        formal = resolve_path("data/RoboArm.db").resolve()
        if self.db_path.resolve() == formal:
            raise RuntimeError("Refusing formal DB")
        self.ui = UiService(sqlite_path=str(self.db_path))
        self.maint = MaintService(self.ui)
        self.virtual = VirtualDemoService(self.ui)
        self.runner = WorkflowRunnerService(self.ui, self.virtual)
        self.runner.set_animation_auto_ack(True)
        cat = self.maint.create_row(
            "categories",
            {
                "CategoryGroup": "inventory",
                "CategoryCode": "robot_arm",
                "zh_TW": "機械臂",
                "en": "Robot Arm",
                "zh_CN": "机械臂",
                "Remark": "",
            },
        )
        inv = self.maint.create_row(
            "inventory",
            {
                "ItemCode": "r1",
                "ItemName": "臂",
                "ItemNameEn": "Arm",
                "Category": cat["TxId"],
                "Brand": "b",
                "Model": "m",
                "SerialNo": "s1",
                "Quantity": 1,
                "Unit": "台",
                "Location": "L",
                "dimensions": "",
                "Remark": "",
            },
        )
        self.combo = self.maint.create_row(
            "product_combinations",
            {"CombinationCode": "C1", "CombinationName": "組合1"},
        )
        self.combo2 = self.maint.create_row(
            "product_combinations",
            {"CombinationCode": "C2", "CombinationName": "組合2"},
        )
        self.item1 = self.maint.create_row(
            "product_combination_items",
            {
                "CombinationTxId": self.combo["TxId"],
                "EquipmentTxId": inv["TxId"],
            },
        )
        inv2 = self.maint.create_row(
            "inventory",
            {
                "ItemCode": "r2",
                "ItemName": "臂2",
                "ItemNameEn": "Arm2",
                "Category": cat["TxId"],
                "Brand": "b",
                "Model": "m",
                "SerialNo": "s2",
                "Quantity": 1,
                "Unit": "台",
                "Location": "L",
                "dimensions": "",
                "Remark": "",
            },
        )
        self.item2 = self.maint.create_row(
            "product_combination_items",
            {
                "CombinationTxId": self.combo2["TxId"],
                "EquipmentTxId": inv2["TxId"],
            },
        )
        self.ui.ensure_seed_workflow_demo()
        self.demo = self.ui.store.fetchone(
            "SELECT * FROM workflows WHERE WorkflowCode = ?",
            ("WF-DEMO-001",),
        )

    def tearDown(self) -> None:
        try:
            self.runner.stop()
            self.runner.reset()
        except Exception:
            pass
        self.runner = None
        self.virtual = None
        self.maint = None
        self.ui = None
        gc.collect()
        self._tmp.cleanup()

    def _shorten(self) -> None:
        self.ui.store.execute(
            """
            UPDATE workflow_steps
            SET TimeoutSec = 0.05
            WHERE WorkflowTxId = ?
            """,
            (self.demo["TxId"],),
        )

    def _wait_done(self, timeout: float = 30.0) -> dict:
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            last = self.runner.get_status()
            if not last.get("is_running"):
                return last
            time.sleep(0.05)
        self.fail("workflow run did not finish: " + str(last))

    def test_seed_targets_and_combo_change_clears_items(self) -> None:
        self.assertIsNotNone(self.demo)
        steps = self.ui.store.fetchall(
            """
            SELECT StepNo, ActionType, TargetKey FROM workflow_steps
            WHERE WorkflowTxId = ? ORDER BY StepNo
            """,
            (self.demo["TxId"],),
        )
        self.assertEqual(
            [row["TargetKey"] for row in steps],
            [
                "demo1_descend",
                "demo1_grasp_close",
                "demo1_lift",
                "demo1_place",
                "demo1_retract",
                "demo1_standby",
            ],
        )
        wf = self.maint.create_row(
            "workflows",
            {
                "WorkflowCode": "WF-CLR",
                "WorkflowName": "清項",
                "CombinationTxId": self.combo["TxId"],
            },
        )
        step = self.maint.create_row(
            "workflow_steps",
            {
                "WorkflowTxId": wf["TxId"],
                "StepName": "s",
                "ActionType": "move",
                "CombinationItemTxId": self.item1["TxId"],
                "TargetKey": "demo1_descend",
            },
        )
        self.maint.update_row(
            "workflows",
            wf["TxId"],
            {
                "WorkflowCode": "WF-CLR",
                "WorkflowName": "清項",
                "CombinationTxId": self.combo2["TxId"],
                "Version": 1,
                "Status": "draft",
            },
        )
        refreshed = self.maint.get_row("workflow_steps", step["TxId"])
        self.assertIsNone(refreshed["CombinationItemTxId"])

    def test_virtual_run_completes_demo1(self) -> None:
        self._shorten()
        started = self.runner.start(int(self.demo["TxId"]))
        self.assertTrue(started["is_running"])
        self.assertFalse(started["can_start"])
        self.assertTrue(started["can_stop"])
        self.assertEqual(started["run"]["WorkflowCode"], "WF-DEMO-001")
        done = self._wait_done()
        self.assertEqual(done["run"]["Status"], STATUS_COMPLETED)
        self.assertEqual(done["control_state"], STATUS_COMPLETED)
        self.assertEqual(done["run"]["ProgressDone"], 6)
        self.assertEqual([s["Status"] for s in done["steps"]], ["completed"] * 6)
        self.assertFalse(done["is_running"])
        self.assertTrue(done["can_reset"])
        self.assertFalse(done["can_start"])

    def test_must_reset_before_restart(self) -> None:
        self._shorten()
        self.runner.start(int(self.demo["TxId"]))
        self._wait_done()
        with self.assertRaises(ValueError):
            self.runner.start(int(self.demo["TxId"]))
        reset = self.runner.reset()
        self.assertEqual(reset["control_state"], STATUS_READY)
        self.assertTrue(reset["can_start"])
        # History retained
        count = self.ui.store.fetchone(
            "SELECT COUNT(*) AS n FROM workflow_runs"
        )["n"]
        self.assertGreaterEqual(count, 1)
        self.runner.start(int(self.demo["TxId"]))
        done = self._wait_done()
        self.assertEqual(done["run"]["Status"], STATUS_COMPLETED)
        count2 = self.ui.store.fetchone(
            "SELECT COUNT(*) AS n FROM workflow_runs"
        )["n"]
        self.assertGreaterEqual(count2, 2)

    def test_duplicate_start_rejected(self) -> None:
        self.ui.store.execute(
            """
            UPDATE workflow_steps
            SET TimeoutSec = 0.5
            WHERE WorkflowTxId = ?
            """,
            (self.demo["TxId"],),
        )
        self.runner.start(int(self.demo["TxId"]))
        with self.assertRaises(ValueError):
            self.runner.start(int(self.demo["TxId"]))
        self.runner.stop()
        self._wait_done(timeout=10.0)

    def test_stop_then_reset(self) -> None:
        self.ui.store.execute(
            """
            UPDATE workflow_steps
            SET TimeoutSec = 0.8
            WHERE WorkflowTxId = ?
            """,
            (self.demo["TxId"],),
        )
        self.runner.start(int(self.demo["TxId"]))
        time.sleep(0.15)
        self.runner.stop()
        final = self._wait_done(timeout=10.0)
        self.assertIn(final["control_state"], (STATUS_STOPPED, STATUS_COMPLETED))
        if final["control_state"] == STATUS_STOPPED:
            for step in final["steps"]:
                self.assertNotEqual(step["Status"], "pending")
            self.assertFalse(final["can_start"])
            self.assertTrue(final["can_reset"])
        self.runner.reset()
        self.assertEqual(self.runner.get_status()["control_state"], STATUS_READY)

    def test_session_busy_rejects_workflow_start(self) -> None:
        self.virtual.connect()
        self.virtual.select_demo("carry_vertical_1_inplace")
        started = self.virtual.start_demo()
        self.assertTrue(started.get("demo_started"))
        self.assertEqual(
            self.virtual.get_session_info()["owner"], SESSION_VIRTUAL_DEMO
        )
        with self.assertRaises(ValueError) as ctx:
            self.runner.start(int(self.demo["TxId"]))
        self.assertIn("虛擬測試", str(ctx.exception))
        self.virtual.reset_demo()
        self.assertFalse(self.virtual.get_session_info()["busy"])

    def test_workflow_locks_out_virtual_demo_start(self) -> None:
        self._shorten()
        self.runner.start(int(self.demo["TxId"]))
        time.sleep(0.05)
        self.virtual.connect()
        self.virtual.select_demo("carry_vertical_1_inplace")
        # select_demo may fail while workflow owns session
        blocked = self.virtual.start_demo()
        self.assertFalse(blocked.get("demo_started", False))
        self.assertEqual(blocked.get("last_result_key"), RESULT_SESSION_BUSY)
        self.runner.stop()
        self._wait_done(timeout=10.0)
        self.runner.reset()

    def test_estop_fails_run(self) -> None:
        self.ui.store.execute(
            """
            UPDATE workflow_steps
            SET TimeoutSec = 0.4
            WHERE WorkflowTxId = ?
            """,
            (self.demo["TxId"],),
        )
        self.runner.start(int(self.demo["TxId"]))
        time.sleep(0.1)
        self.virtual.emergency_stop()
        done = self._wait_done(timeout=10.0)
        self.assertIn(done["control_state"], (STATUS_FAILED, STATUS_STOPPED))
        if done["control_state"] == STATUS_FAILED:
            self.assertTrue(done["run"]["ErrorMessage"])
        self.virtual.reset_estop()
        self.runner.reset()


if __name__ == "__main__":
    unittest.main()
