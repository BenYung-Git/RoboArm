"""Isolated tests for equipment_settings (never use data/RoboArm.db)."""

from __future__ import annotations

import gc
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from app.services.maint_service import MaintService
from app.services.network_ip_service import detect_network_ips
from app.services.table_layout_service import TableLayoutService
from app.services.ui_service import UiService
from app.storage.config_store import resolve_path


class EquipmentSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmp.name) / "eq_settings_test.db"
        formal = resolve_path("data/RoboArm.db").resolve()
        if self.db_path.resolve() == formal:
            raise RuntimeError("Refusing formal DB")
        self.ui = UiService(sqlite_path=str(self.db_path))
        self.maint = MaintService(self.ui)
        self.layout = TableLayoutService(self.ui, self.maint)
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
                "zh_TW": "控制櫃",
                "en": "Control Cabinet",
                "zh_CN": "控制柜",
                "Remark": "",
            },
        )
        self.other_cat = self.maint.create_row(
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
        self.arm_inv = self._create_inventory(
            "arm1", "機械臂A", "Arm A", self.arm_cat["TxId"]
        )
        self.box_inv = self._create_inventory(
            "box1", "電控櫃A", "Box A", self.box_cat["TxId"]
        )
        self.tool_inv = self._create_inventory(
            "tool1", "工具A", "Tool A", self.other_cat["TxId"]
        )
        self.disabled_arm = self._create_inventory(
            "arm_off", "失效臂", "Disabled Arm", self.arm_cat["TxId"]
        )
        self.maint.toggle_disable("inventory", self.disabled_arm["TxId"])

    def tearDown(self) -> None:
        self.layout = None
        self.maint = None
        self.ui = None
        gc.collect()
        self._tmp.cleanup()

    def _create_inventory(
        self, code: str, name: str, name_en: str, category_txid: int
    ) -> dict:
        return self.maint.create_row(
            "inventory",
            {
                "ItemCode": code,
                "ItemName": name,
                "ItemNameEn": name_en,
                "Category": category_txid,
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

    def test_menu_host_and_trilingual_title(self) -> None:
        menus = {
            row["menu_key"]: row
            for row in self.ui.store.fetchall(
                "SELECT menu_key, route_path, sort_order, label_key FROM menus"
            )
        }
        self.assertIn("equipment_settings", menus)
        self.assertEqual(menus["equipment_settings"]["sort_order"], 6)
        self.assertEqual(
            menus["equipment_settings"]["route_path"], "/page/equipment_settings"
        )
        inv_order = menus["inventory"]["sort_order"]
        self.assertEqual(menus["equipment_settings"]["sort_order"], inv_order + 1)
        host = self.ui.get_table_ui_for_menu("equipment_settings")
        self.assertIsNotNone(host)
        self.assertEqual(host["table_key"], "equipment_settings")
        self.assertEqual(
            self.ui.t("menu_equipment_settings", "zh_TW"), "機械臂及電控櫃設定"
        )
        self.assertEqual(
            self.ui.t("menu_equipment_settings", "en"),
            "Robot Arm & Control Cabinet Settings",
        )
        self.assertEqual(
            self.ui.t("menu_equipment_settings", "zh_CN"), "机械臂及电控柜设置"
        )

    def test_schema(self) -> None:
        cols = {
            row["name"]: row
            for row in self.ui.store.fetchall("PRAGMA table_info(equipment_settings)")
        }
        expected = [
            "TxId",
            "EquipmentTxId",
            "SiteNo",
            "SiteName",
            "IpAddress",
            "Port",
            "ConnectionMode",
            "ControllerVersion",
            "ServoVersion",
            "ScbVersion",
            "PayloadKg",
            "Remark",
            "isDisable",
            "CreatedAt",
            "UpdatedAt",
        ]
        self.assertEqual(list(cols.keys()), expected)
        self.assertEqual(cols["EquipmentTxId"]["notnull"], 1)
        self.assertEqual(cols["isDisable"]["notnull"], 1)
        self.assertEqual(cols["isDisable"]["dflt_value"], "0")

    def test_txid_increment_and_default_desc(self) -> None:
        first = self.maint.create_row(
            "equipment_settings", {"EquipmentTxId": self.arm_inv["TxId"]}
        )
        second = self.maint.create_row(
            "equipment_settings", {"EquipmentTxId": self.box_inv["TxId"]}
        )
        self.assertEqual(first["TxId"], 1)
        self.assertEqual(second["TxId"], 2)
        layout = self.layout.ensure_table_layout("equipment_settings")
        txid_col = next(
            col for col in layout["columns"] if col["field_key"] == "TxId"
        )
        self.assertEqual(txid_col["sort_direction"], "desc")
        rows = self.maint.list_rows("equipment_settings")
        self.assertEqual([row["TxId"] for row in rows], [2, 1])

    def test_equipment_txid_unique_and_required(self) -> None:
        self.maint.create_row(
            "equipment_settings", {"EquipmentTxId": self.arm_inv["TxId"]}
        )
        with self.assertRaises(ValueError):
            self.maint.create_row(
                "equipment_settings", {"EquipmentTxId": self.arm_inv["TxId"]}
            )
        with self.assertRaises(ValueError):
            self.maint.create_row("equipment_settings", {})

    def test_optional_fields_store_null(self) -> None:
        created = self.maint.create_row(
            "equipment_settings",
            {
                "EquipmentTxId": self.arm_inv["TxId"],
                "SiteNo": "",
                "SiteName": "",
                "IpAddress": "",
                "Port": "",
                "ControllerVersion": "",
                "ServoVersion": "",
                "ScbVersion": "",
                "PayloadKg": "",
                "Remark": "",
            },
        )
        raw = self.ui.store.fetchone(
            "SELECT * FROM equipment_settings WHERE TxId = ?",
            (created["TxId"],),
        )
        for field in (
            "SiteNo",
            "SiteName",
            "IpAddress",
            "Port",
            "ControllerVersion",
            "ServoVersion",
            "ScbVersion",
            "PayloadKg",
            "Remark",
        ):
            self.assertIsNone(raw[field])

    def test_relation_filters_and_stores_inventory_txid(self) -> None:
        meta = self.maint.build_table_ui_meta("equipment_settings")
        column = next(
            item for item in meta["columns"] if item["field"] == "EquipmentTxId"
        )
        values = {str(option["value"]) for option in column["options"]}
        self.assertIn(str(self.arm_inv["TxId"]), values)
        self.assertIn(str(self.box_inv["TxId"]), values)
        self.assertNotIn(str(self.tool_inv["TxId"]), values)
        self.assertNotIn(str(self.disabled_arm["TxId"]), values)
        arm_opt = next(
            option
            for option in column["options"]
            if str(option["value"]) == str(self.arm_inv["TxId"])
        )
        self.assertEqual(arm_opt["category_code"], "robot_arm")
        created = self.maint.create_row(
            "equipment_settings", {"EquipmentTxId": self.arm_inv["TxId"]}
        )
        self.assertEqual(created["EquipmentTxId"], self.arm_inv["TxId"])
        raw = self.ui.store.fetchone(
            "SELECT EquipmentTxId FROM equipment_settings WHERE TxId = ?",
            (created["TxId"],),
        )
        self.assertEqual(raw["EquipmentTxId"], self.arm_inv["TxId"])

    def test_connection_mode_always_real(self) -> None:
        created = self.maint.create_row(
            "equipment_settings",
            {
                "EquipmentTxId": self.arm_inv["TxId"],
                "ConnectionMode": "simulator",
            },
        )
        self.assertEqual(created["ConnectionMode"], "real")
        raw = self.ui.store.fetchone(
            "SELECT ConnectionMode FROM equipment_settings WHERE TxId = ?",
            (created["TxId"],),
        )
        self.assertEqual(raw["ConnectionMode"], "real")
        updated = self.maint.update_row(
            "equipment_settings",
            created["TxId"],
            {
                "EquipmentTxId": self.arm_inv["TxId"],
                "ConnectionMode": "other",
                "SiteNo": "S1",
            },
        )
        self.assertEqual(updated["ConnectionMode"], "real")

    def test_field_visibility_rules_config(self) -> None:
        table_def = self.maint.get_table_def("equipment_settings")
        vis = table_def["field_visibility"]
        self.assertEqual(vis["depends_on_field"], "EquipmentTxId")
        self.assertEqual(vis["annotate_key"], "category_code")
        rules = {rule["category_code"]: rule for rule in vis["rules"]}
        self.assertEqual(
            rules["robot_arm"]["show_fields"],
            ["ServoVersion", "ScbVersion", "PayloadKg"],
        )
        self.assertEqual(
            rules["control_box"]["hide_fields"],
            ["ServoVersion", "ScbVersion", "PayloadKg"],
        )
        cols = {
            row["name"]
            for row in self.ui.store.fetchall("PRAGMA table_info(equipment_settings)")
        }
        self.assertIn("ServoVersion", cols)
        self.assertIn("ScbVersion", cols)
        self.assertIn("PayloadKg", cols)

    def test_shared_crud_search_filter_toggle(self) -> None:
        row = self.maint.create_row(
            "equipment_settings",
            {
                "EquipmentTxId": self.arm_inv["TxId"],
                "SiteName": "站A",
                "IpAddress": "10.0.0.8",
            },
        )
        found = self.maint.list_rows("equipment_settings", search="站A")
        self.assertEqual(len(found), 1)
        enabled = self.maint.list_rows(
            "equipment_settings", flag_filters={"isDisable": "0"}
        )
        self.assertEqual(len(enabled), 1)
        toggled = self.maint.toggle_disable("equipment_settings", row["TxId"])
        self.assertTrue(toggled["isDisable"])
        enabled_after = self.maint.list_rows(
            "equipment_settings", flag_filters={"isDisable": "0"}
        )
        self.assertEqual(len(enabled_after), 0)
        disabled = self.maint.list_rows(
            "equipment_settings", flag_filters={"isDisable": "1"}
        )
        self.assertEqual(len(disabled), 1)

    def test_column_width_default_100(self) -> None:
        layout = self.layout.ensure_table_layout("equipment_settings")
        for col in layout["columns"]:
            if col["field_key"] == "__multi_select":
                self.assertEqual(col["column_width"], 48)
            else:
                self.assertEqual(col["column_width"], 100)
        payload = {
            "zebra_enabled": layout["zebra_enabled"],
            "zebra_color": layout["zebra_color"],
            "columns": [
                {
                    "field_key": col["field_key"],
                    "visible": col["visible"],
                    "sort_direction": col["sort_direction"],
                    "column_width": (
                        140
                        if col["field_key"] == "IpAddress"
                        else col["column_width"]
                    ),
                }
                for col in layout["columns"]
            ],
        }
        saved = self.layout.save_layout("equipment_settings", payload)
        ip_col = next(
            col for col in saved["columns"] if col["field_key"] == "IpAddress"
        )
        self.assertEqual(ip_col["column_width"], 140)

    def test_ip_detect_readonly_no_db_write(self) -> None:
        before = self.ui.store.fetchone(
            "SELECT COUNT(*) AS n FROM equipment_settings"
        )["n"]
        items = detect_network_ips()
        self.assertIsInstance(items, list)
        for item in items:
            self.assertIn("ip", item)
            self.assertIn(item["source"], ("local", "neighbor"))
        after = self.ui.store.fetchone(
            "SELECT COUNT(*) AS n FROM equipment_settings"
        )["n"]
        self.assertEqual(before, after)

    def test_created_updated_iso8601(self) -> None:
        created = self.maint.create_row(
            "equipment_settings", {"EquipmentTxId": self.arm_inv["TxId"]}
        )
        self.assertRegex(
            created["CreatedAt"],
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
        )
        self.assertEqual(created["CreatedAt"], created["UpdatedAt"])
        updated = self.maint.update_row(
            "equipment_settings",
            created["TxId"],
            {"EquipmentTxId": self.arm_inv["TxId"], "SiteNo": "1"},
        )
        self.assertEqual(updated["CreatedAt"], created["CreatedAt"])
        self.assertGreaterEqual(updated["UpdatedAt"], created["UpdatedAt"])

    def test_inventory_untouched_by_equipment_create(self) -> None:
        inv_before = self.ui.store.fetchone(
            "SELECT COUNT(*) AS n FROM inventory"
        )["n"]
        self.maint.create_row(
            "equipment_settings", {"EquipmentTxId": self.arm_inv["TxId"]}
        )
        inv_after = self.ui.store.fetchone(
            "SELECT COUNT(*) AS n FROM inventory"
        )["n"]
        self.assertEqual(inv_before, inv_after)


class EquipmentSettingsApiTests(unittest.TestCase):
    def test_ipv4_detect_api_shape(self) -> None:
        from app.main import app

        client = TestClient(app)
        response = client.get("/api/network/ipv4-detect")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("items", body)
        self.assertIsInstance(body["items"], list)
        for item in body["items"]:
            self.assertIn("ip", item)
            self.assertIn("source", item)


if __name__ == "__main__":
    unittest.main()
