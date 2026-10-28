"""Isolated tests for equipment_connection (never use formal DB / no SDK)."""

from __future__ import annotations

import gc
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app
from app.services.equipment_connection_service import EquipmentConnectionService
from app.services.maint_service import MaintService
from app.services.ui_service import UiService
from app.storage.config_store import resolve_path


class EquipmentConnectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmp.name) / "eq_conn_test.db"
        formal = resolve_path("data/RoboArm.db").resolve()
        if self.db_path.resolve() == formal:
            raise RuntimeError("Refusing formal DB")
        self.ui = UiService(sqlite_path=str(self.db_path))
        self.maint = MaintService(self.ui)
        self.svc = EquipmentConnectionService(self.ui)
        self.arm_cat = self.maint.create_row(
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
        self.box_cat = self.maint.create_row(
            "categories",
            {
                "CategoryGroup": "inventory",
                "CategoryCode": "control_box",
                "zh_TW": "電控櫃",
                "en": "Control Box",
                "zh_CN": "电控柜",
                "Remark": "",
            },
        )
        self.tool_cat = self.maint.create_row(
            "categories",
            {
                "CategoryGroup": "inventory",
                "CategoryCode": "tool",
                "zh_TW": "工具",
                "en": "Tool",
                "zh_CN": "工具",
                "Remark": "",
            },
        )
        self.arm_a = self._inv("A1", "JAKA臂A", "Arm A", self.arm_cat, "jaka", "SA")
        self.arm_b = self._inv("B1", "JAKA臂B", "Arm B", self.arm_cat, "jaka", "SB")
        self.rokae = self._inv("R1", "Rokae臂", "Rokae Arm", self.arm_cat, "rokae", "SR")
        self.tool = self._inv("T1", "工具", "Tool", self.tool_cat, "jaka", "ST")
        self.box = self._inv("C1", "JAKA櫃", "Cab", self.box_cat, "jaka", "SC")

    def tearDown(self) -> None:
        self.svc = None
        self.maint = None
        self.ui = None
        gc.collect()
        self._tmp.cleanup()

    def _inv(self, code, name, name_en, cat, brand, serial):
        return self.maint.create_row(
            "inventory",
            {
                "ItemCode": code,
                "ItemName": name,
                "ItemNameEn": name_en,
                "Category": cat["TxId"],
                "Brand": brand,
                "Model": "m",
                "SerialNo": serial,
                "Quantity": 1,
                "Unit": "台",
                "Location": "L",
                "dimensions": "",
                "Remark": "",
            },
        )

    def test_schema_and_unconfigured(self) -> None:
        names = {
            row["name"]
            for row in self.ui.store.fetchall(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertIn("equipment_connection", names)
        self.assertNotIn("equipment_settings", names)
        view = self.svc.build_view(self.arm_a["TxId"])
        self.assertTrue(view["applicable"])
        self.assertFalse(view["configured"])
        self.assertIsNone(view["connection"])
        self.assertEqual(view["status_label"], self.ui.t("status_not_configured"))

    def test_applicability_by_category_and_brand(self) -> None:
        self.assertTrue(self.svc.build_view(self.arm_a["TxId"])["applicable"])
        self.assertTrue(self.svc.build_view(self.box["TxId"])["applicable"])
        self.assertFalse(self.svc.build_view(self.rokae["TxId"])["applicable"])
        self.assertFalse(self.svc.build_view(self.tool["TxId"])["applicable"])

    def test_save_reload_edit_and_shared(self) -> None:
        saved = self.svc.save_connection(
            self.arm_a["TxId"],
            {
                "driver_type": "jaka",
                "connection_mode": "network",
                "host_address": " 192.168.10.21 ",
                "remark": "line1",
            },
        )
        self.assertTrue(saved["configured"])
        self.assertEqual(saved["connection"]["host_address"], "192.168.10.21")
        self.assertEqual(saved["connection"]["driver_type"], "jaka")
        reloaded = self.svc.build_view(self.arm_a["TxId"])
        self.assertEqual(
            reloaded["connection"]["host_address"],
            saved["connection"]["host_address"],
        )
        header1 = self.maint.create_row(
            "product_combinations",
            {"CombinationCode": "P1", "CombinationName": "組合1"},
        )
        header2 = self.maint.create_row(
            "product_combinations",
            {"CombinationCode": "P2", "CombinationName": "組合2"},
        )
        self.maint.create_row(
            "product_combination_items",
            {
                "CombinationTxId": header1["TxId"],
                "EquipmentTxId": self.arm_a["TxId"],
            },
        )
        self.maint.create_row(
            "product_combination_items",
            {
                "CombinationTxId": header2["TxId"],
                "EquipmentTxId": self.arm_a["TxId"],
            },
        )
        self.maint.create_row(
            "product_combination_items",
            {
                "CombinationTxId": header1["TxId"],
                "EquipmentTxId": self.arm_b["TxId"],
            },
        )
        shared = self.svc.build_view(self.arm_a["TxId"])
        other = self.svc.build_view(self.arm_b["TxId"])
        self.assertEqual(shared["connection"]["host_address"], "192.168.10.21")
        self.assertFalse(other["configured"])
        self.svc.save_connection(
            self.arm_a["TxId"],
            {
                "driver_type": "jaka",
                "connection_mode": "network",
                "host_address": "10.0.0.8",
                "remark": "",
            },
        )
        self.assertEqual(
            self.svc.build_view(self.arm_a["TxId"])["connection"]["host_address"],
            "10.0.0.8",
        )
        self.assertFalse(self.svc.build_view(self.arm_b["TxId"])["configured"])

    def test_validation_and_clear(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.save_connection(
                self.arm_a["TxId"],
                {
                    "driver_type": "jaka",
                    "connection_mode": "network",
                    "host_address": "not-an-ip",
                },
            )
        with self.assertRaises(ValueError):
            self.svc.save_connection(
                self.arm_a["TxId"],
                {
                    "driver_type": "rokae",
                    "connection_mode": "network",
                    "host_address": "1.2.3.4",
                },
            )
        with self.assertRaises(ValueError):
            self.svc.save_connection(
                self.rokae["TxId"],
                {
                    "driver_type": "jaka",
                    "connection_mode": "network",
                    "host_address": "1.2.3.4",
                },
            )
        self.svc.save_connection(
            self.arm_a["TxId"],
            {
                "driver_type": "jaka",
                "connection_mode": "network",
                "host_address": "1.2.3.4",
            },
        )
        cleared = self.svc.clear_connection(self.arm_a["TxId"])
        self.assertFalse(cleared["configured"])
        self.assertIsNotNone(
            self.ui.store.fetchone(
                "SELECT TxId FROM inventory WHERE TxId = ?",
                (self.arm_a["TxId"],),
            )
        )

    def test_api_routes_registered_and_old_absent(self) -> None:
        paths = {getattr(route, "path", None) for route in app.routes}
        self.assertIn("/api/equipment/{equipment_txid}/connection", paths)
        self.assertNotIn("/api/network/ipv4-detect", paths)
        self.assertNotIn("/page/equipment_settings", paths)
        network_service = PROJECT_ROOT / "app" / "services" / "network_ip_service.py"
        self.assertFalse(network_service.exists())

    def test_item_annotate_includes_category_and_brand(self) -> None:
        header = self.maint.create_row(
            "product_combinations",
            {"CombinationCode": "X", "CombinationName": "X"},
        )
        item = self.maint.create_row(
            "product_combination_items",
            {
                "CombinationTxId": header["TxId"],
                "EquipmentTxId": self.arm_a["TxId"],
            },
        )
        loaded = self.maint.get_row("product_combination_items", item["TxId"])
        self.assertEqual(loaded["EquipmentTxId_category_code"], "robot_arm")
        self.assertEqual(loaded["EquipmentTxId_brand"], "jaka")
        meta = self.maint.build_table_ui_meta("product_combination_items")
        self.assertTrue(meta["equipment_connection"]["enabled"])


if __name__ == "__main__":
    unittest.main()
