"""Isolated tests for workflows Master-Detail (never use formal DB)."""

from __future__ import annotations

import gc
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.maint_service import MaintService
from app.services.table_layout_service import TableLayoutService
from app.services.ui_service import UiService
from app.storage.config_store import resolve_path


class WorkflowsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmp.name) / "workflows_test.db"
        formal = resolve_path("data/RoboArm.db").resolve()
        if self.db_path.resolve() == formal:
            raise RuntimeError("Refusing formal DB")
        self.ui = UiService(sqlite_path=str(self.db_path))
        self.maint = MaintService(self.ui)
        self.layout = TableLayoutService(self.ui, self.maint)
        self.cat = self.maint.create_row(
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
        self.inv1 = self._inv("w1", "設備一", "Eq One")
        self.inv2 = self._inv("w2", "設備二", "Eq Two")
        self.combo1 = self.maint.create_row(
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
                "CombinationTxId": self.combo1["TxId"],
                "EquipmentTxId": self.inv1["TxId"],
            },
        )
        self.item2 = self.maint.create_row(
            "product_combination_items",
            {
                "CombinationTxId": self.combo2["TxId"],
                "EquipmentTxId": self.inv2["TxId"],
            },
        )
        # Seed may have run before combinations existed; create demo now.
        self.ui.ensure_seed_workflow_demo()

    def tearDown(self) -> None:
        self.layout = None
        self.maint = None
        self.ui = None
        gc.collect()
        self._tmp.cleanup()

    def _inv(self, code: str, name: str, name_en: str) -> dict:
        return self.maint.create_row(
            "inventory",
            {
                "ItemCode": code,
                "ItemName": name,
                "ItemNameEn": name_en,
                "Category": self.cat["TxId"],
                "Brand": "b",
                "Model": "m",
                "SerialNo": "s-" + code,
                "Quantity": 1,
                "Unit": "台",
                "Location": "L",
                "dimensions": "",
                "Remark": "",
            },
        )

    def test_menu_host_and_i18n(self) -> None:
        menus = {
            row["menu_key"]: row
            for row in self.ui.store.fetchall(
                "SELECT menu_key, sort_order, route_path FROM menus"
            )
        }
        self.assertEqual(menus["workflows"]["sort_order"], 7)
        self.assertEqual(menus["workflows"]["route_path"], "/page/workflows")
        host = self.ui.get_table_ui_for_menu("workflows")
        self.assertEqual(host["table_key"], "workflows")
        self.assertEqual(self.ui.t("menu_workflows", "zh_TW"), "作業流程")
        self.assertEqual(self.ui.t("menu_workflows", "en"), "Workflow")
        self.assertEqual(self.ui.t("menu_workflows", "zh_CN"), "作业流程")
        self.assertEqual(
            self.ui.t("table_ui_btn_add_workflow_step", "zh_TW"), "＋新增步驟"
        )

    def test_schema_and_seed_demo(self) -> None:
        wf_cols = [
            row["name"]
            for row in self.ui.store.fetchall("PRAGMA table_info(workflows)")
        ]
        self.assertEqual(
            wf_cols,
            [
                "TxId",
                "WorkflowCode",
                "WorkflowName",
                "CombinationTxId",
                "Version",
                "Status",
                "Remark",
                "isDisable",
                "CreatedAt",
                "UpdatedAt",
            ],
        )
        step_cols = [
            row["name"]
            for row in self.ui.store.fetchall("PRAGMA table_info(workflow_steps)")
        ]
        self.assertIn("StepNo", step_cols)
        self.assertIn("CombinationItemTxId", step_cols)
        demo = self.ui.store.fetchone(
            "SELECT * FROM workflows WHERE WorkflowCode = ?",
            ("WF-DEMO-001",),
        )
        self.assertIsNotNone(demo)
        self.assertEqual(demo["WorkflowName"], "Demo 1 原位垂直取放")
        self.assertEqual(demo["Status"], "draft")
        self.assertEqual(demo["Version"], 1)
        steps = self.ui.store.fetchall(
            """
            SELECT StepNo, StepName, ActionType FROM workflow_steps
            WHERE WorkflowTxId = ?
            ORDER BY StepNo ASC
            """,
            (demo["TxId"],),
        )
        self.assertEqual(
            [(row["StepNo"], row["StepName"], row["ActionType"]) for row in steps],
            [
                (10.0, "下降取料", "move"),
                (20.0, "夾取工件", "gripper"),
                (30.0, "垂直提升", "move"),
                (40.0, "放回原位", "move"),
                (50.0, "向上退出", "move"),
                (60.0, "返回待機", "end"),
            ],
        )
        self.ui.ensure_seed_workflow_demo()
        count = self.ui.store.fetchone(
            "SELECT COUNT(*) AS n FROM workflows WHERE WorkflowCode = ?",
            ("WF-DEMO-001",),
        )["n"]
        self.assertEqual(count, 1)

    def test_header_crud_unique_and_cascade_disable(self) -> None:
        wf = self.maint.create_row(
            "workflows",
            {
                "WorkflowCode": "WF-A",
                "WorkflowName": "流程A",
                "CombinationTxId": self.combo1["TxId"],
                "Version": 1,
                "Status": "draft",
            },
        )
        self.assertGreaterEqual(wf["TxId"], 1)
        self.assertEqual(wf["Version"], 1)
        self.assertEqual(wf["Status"], "draft")
        with self.assertRaises(ValueError):
            self.maint.create_row(
                "workflows",
                {
                    "WorkflowCode": "WF-A",
                    "WorkflowName": "重複",
                    "CombinationTxId": self.combo1["TxId"],
                },
            )
        step = self.maint.create_row(
            "workflow_steps",
            {
                "WorkflowTxId": wf["TxId"],
                "StepName": "第一步",
                "ActionType": "move",
                "CombinationItemTxId": self.item1["TxId"],
            },
        )
        self.assertEqual(step["StepNo"], 10.0)
        updated = self.maint.update_row(
            "workflows",
            wf["TxId"],
            {
                "WorkflowCode": "WF-A",
                "WorkflowName": "流程A2",
                "CombinationTxId": self.combo1["TxId"],
                "Version": 2,
                "Status": "active",
            },
        )
        self.assertEqual(updated["WorkflowName"], "流程A2")
        self.assertEqual(updated["Version"], 2)
        toggled = self.maint.toggle_disable("workflows", wf["TxId"])
        self.assertTrue(toggled["isDisable"])
        child = self.maint.get_row("workflow_steps", step["TxId"])
        self.assertTrue(child["isDisable"])

    def test_steps_scope_sort_and_unique(self) -> None:
        wf = self.maint.create_row(
            "workflows",
            {
                "WorkflowCode": "WF-B",
                "WorkflowName": "流程B",
                "CombinationTxId": self.combo1["TxId"],
            },
        )
        s1 = self.maint.create_row(
            "workflow_steps",
            {
                "WorkflowTxId": wf["TxId"],
                "StepName": "下降取料",
                "ActionType": "move",
                "CombinationItemTxId": self.item1["TxId"],
            },
        )
        self.assertEqual(s1["StepNo"], 10.0)
        s2 = self.maint.create_row(
            "workflow_steps",
            {
                "WorkflowTxId": wf["TxId"],
                "StepName": "夾取工件",
                "ActionType": "gripper",
            },
        )
        self.assertEqual(s2["StepNo"], 20.0)
        with self.assertRaises(ValueError):
            self.maint.create_row(
                "workflow_steps",
                {
                    "WorkflowTxId": wf["TxId"],
                    "StepNo": 10,
                    "StepName": "重複次序",
                    "ActionType": "wait",
                },
            )
        with self.assertRaises(ValueError):
            self.maint.create_row(
                "workflow_steps",
                {
                    "WorkflowTxId": wf["TxId"],
                    "StepName": "跨組合設備",
                    "ActionType": "move",
                    "CombinationItemTxId": self.item2["TxId"],
                },
            )
        empty_item = self.maint.create_row(
            "workflow_steps",
            {
                "WorkflowTxId": wf["TxId"],
                "StepName": "無設備",
                "ActionType": "wait",
                "CombinationItemTxId": "",
            },
        )
        self.assertIsNone(empty_item["CombinationItemTxId"])
        rows = self.maint.list_rows(
            "workflow_steps",
            eq_filters={"WorkflowTxId": wf["TxId"]},
        )
        self.assertEqual([row["StepNo"] for row in rows], [10.0, 20.0, 30.0])
        peek = self.maint.peek_auto_gen_value(
            "workflow_steps", "StepNo", wf["TxId"]
        )
        self.assertEqual(peek, 40.0)

    def test_master_detail_meta_and_layout(self) -> None:
        meta = self.maint.build_table_ui_meta("workflows")
        self.assertEqual(meta["detail"]["table_key"], "workflow_steps")
        self.assertEqual(meta["detail"]["parent_field"], "WorkflowTxId")
        self.assertEqual(meta["detail"]["presentation"], "expand_row")
        self.assertEqual(meta["detail"]["parent_context_fields"], ["CombinationTxId"])
        toolbar = meta["detail"]["embedded_toolbar"]
        self.assertFalse(toolbar["show_search"])
        self.assertEqual(toolbar["layout_save_placement"], "chrome")
        step_meta = self.maint.build_table_ui_meta("workflow_steps")
        item_col = next(
            col
            for col in step_meta["columns"]
            if col["field"] == "CombinationItemTxId"
        )
        self.assertEqual(
            item_col["option_match_parent"],
            {
                "annotate_as": "combination_txid",
                "parent_field": "CombinationTxId",
            },
        )
        annotate_values = {
            str(opt["value"]): opt.get("combination_txid")
            for opt in item_col["options"]
        }
        self.assertEqual(
            str(annotate_values[str(self.item1["TxId"])]),
            str(self.combo1["TxId"]),
        )
        labels = {str(opt["value"]): opt["label"] for opt in item_col["options"]}
        self.assertIn(" / ", labels[str(self.item1["TxId"])])
        layout = self.layout.ensure_table_layout("workflow_steps")
        step_col = next(
            col for col in layout["columns"] if col["field_key"] == "StepNo"
        )
        self.assertEqual(step_col["sort_direction"], "asc")
        header_layout = self.layout.ensure_table_layout("workflows")
        self.assertEqual(header_layout["table_key"], "workflows")

    def test_existing_modules_untouched(self) -> None:
        inv_count = self.ui.store.fetchone(
            "SELECT COUNT(*) AS n FROM inventory"
        )["n"]
        combo_count = self.ui.store.fetchone(
            "SELECT COUNT(*) AS n FROM product_combinations"
        )["n"]
        self.maint.create_row(
            "workflows",
            {
                "WorkflowCode": "WF-X",
                "WorkflowName": "X",
                "CombinationTxId": self.combo1["TxId"],
            },
        )
        self.assertEqual(
            self.ui.store.fetchone("SELECT COUNT(*) AS n FROM inventory")["n"],
            inv_count,
        )
        self.assertEqual(
            self.ui.store.fetchone(
                "SELECT COUNT(*) AS n FROM product_combinations"
            )["n"],
            combo_count,
        )
        self.assertEqual(
            self.maint.get_table_def("product_combinations")["db_table"],
            "product_combinations",
        )


if __name__ == "__main__":
    unittest.main()
