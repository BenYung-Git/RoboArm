"""Isolated tests for inventory version_scb / version_controller / version_servo."""

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
from app.services.ui_service import UiService
from app.storage.config_store import resolve_path


class InventoryVersionFieldsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmp.name) / "inventory_version_test.db"
        formal = resolve_path("data/RoboArm.db").resolve()
        if self.db_path.resolve() == formal:
            raise RuntimeError("Refusing formal DB")
        self.ui = UiService(sqlite_path=str(self.db_path))
        self.maint = MaintService(self.ui)
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

    def tearDown(self) -> None:
        self.maint = None
        self.ui = None
        gc.collect()
        self._tmp.cleanup()

    def _base_payload(self) -> dict:
        return {
            "ItemCode": "v_arm",
            "ItemName": "版本測試臂",
            "ItemNameEn": "Version Test Arm",
            "Category": self.cat["TxId"],
            "Brand": "jaka",
            "Model": "zu7",
            "SerialNo": "S1",
            "Quantity": 1,
            "Unit": "台",
            "Location": "L",
            "dimensions": "",
            "Remark": "",
        }

    def test_schema_and_labels(self) -> None:
        cols = {
            row["name"]: row["type"]
            for row in self.ui.store.fetchall("PRAGMA table_info(inventory)")
        }
        self.assertEqual(cols["version_scb"], "TEXT")
        self.assertEqual(cols["version_controller"], "TEXT")
        self.assertEqual(cols["version_servo"], "TEXT")
        self.assertEqual(self.ui.t("field_version_scb", "zh_TW"), "SCB 版本")
        self.assertEqual(
            self.ui.t("field_version_controller", "zh_TW"), "控制器版本"
        )
        self.assertEqual(self.ui.t("field_version_servo", "zh_TW"), "伺服版本")
        fields = {
            col["field"]: col
            for col in self.maint.get_table_def("inventory")["columns"]
        }
        for name in ("version_scb", "version_controller", "version_servo"):
            self.assertEqual(fields[name]["field_type"], "text")
            self.assertFalse(fields[name]["required"])
            self.assertTrue(fields[name]["nullable"])

    def test_save_reopen_keeps_version_strings(self) -> None:
        created = self.maint.create_row(
            "inventory",
            {
                **self._base_payload(),
                "version_scb": "SCB-1.2.3-beta",
                "version_controller": "ctrl_4.0.1",
                "version_servo": "servo 9.8.7",
            },
        )
        self.assertEqual(created["version_scb"], "SCB-1.2.3-beta")
        self.assertEqual(created["version_controller"], "ctrl_4.0.1")
        self.assertEqual(created["version_servo"], "servo 9.8.7")
        loaded = self.maint.get_row("inventory", created["TxId"])
        self.assertEqual(loaded["version_scb"], "SCB-1.2.3-beta")
        self.assertEqual(loaded["version_controller"], "ctrl_4.0.1")
        self.assertEqual(loaded["version_servo"], "servo 9.8.7")
        raw = self.ui.store.fetchone(
            "SELECT version_scb, version_controller, version_servo "
            "FROM inventory WHERE TxId = ?",
            (created["TxId"],),
        )
        self.assertEqual(raw["version_scb"], "SCB-1.2.3-beta")
        self.assertNotIsInstance(raw["version_scb"], float)

    def test_empty_versions_allowed(self) -> None:
        created = self.maint.create_row(
            "inventory",
            {
                **self._base_payload(),
                "ItemCode": "v_empty",
                "version_scb": "",
                "version_controller": "   ",
                "version_servo": None,
            },
        )
        self.assertIsNone(created["version_scb"])
        self.assertIsNone(created["version_controller"])
        self.assertIsNone(created["version_servo"])
        updated = self.maint.update_row(
            "inventory",
            created["TxId"],
            {
                **self._base_payload(),
                "ItemCode": "v_empty",
                "version_scb": "1.0.0",
                "version_controller": "",
                "version_servo": "2.0.0-rc1",
            },
        )
        self.assertEqual(updated["version_scb"], "1.0.0")
        self.assertIsNone(updated["version_controller"])
        self.assertEqual(updated["version_servo"], "2.0.0-rc1")
        reopened = self.maint.get_row("inventory", created["TxId"])
        self.assertEqual(reopened["version_scb"], "1.0.0")
        self.assertIsNone(reopened["version_controller"])
        self.assertEqual(reopened["version_servo"], "2.0.0-rc1")

    def test_existing_row_defaults_empty_after_column_add(self) -> None:
        created = self.maint.create_row(
            "inventory",
            {**self._base_payload(), "ItemCode": "v_legacy"},
        )
        loaded = self.maint.get_row("inventory", created["TxId"])
        self.assertIsNone(loaded["version_scb"])
        self.assertIsNone(loaded["version_controller"])
        self.assertIsNone(loaded["version_servo"])


if __name__ == "__main__":
    unittest.main()
