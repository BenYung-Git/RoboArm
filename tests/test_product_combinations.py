"""Isolated tests for product_combinations Master-Detail (never use formal DB)."""

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


class ProductCombinationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmp.name) / "product_combo_test.db"
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
        self.inv1 = self._inv("a1", "設備一", "Eq One")
        self.inv2 = self._inv("a2", "設備二", "Eq Two")
        self.inv3 = self._inv("a3", "設備三", "Eq Three")
        self.disabled = self._inv("off", "失效設備", "Disabled")
        self.maint.toggle_disable("inventory", self.disabled["TxId"])

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

    def test_menu_host_trilingual(self) -> None:
        menus = {
            row["menu_key"]: row
            for row in self.ui.store.fetchall(
                "SELECT menu_key, sort_order, route_path FROM menus"
            )
        }
        self.assertEqual(menus["product_combinations"]["sort_order"], 6)
        self.assertEqual(
            menus["product_combinations"]["route_path"],
            "/page/product_combinations",
        )
        self.assertNotIn("equipment_settings", menus)
        host = self.ui.get_table_ui_for_menu("product_combinations")
        self.assertEqual(host["table_key"], "product_combinations")
        self.assertEqual(
            self.ui.t("menu_product_combinations", "zh_TW"), "產品／組合設定"
        )
        self.assertEqual(
            self.ui.t("menu_product_combinations", "en"),
            "Product / Combination Settings",
        )
        self.assertEqual(
            self.ui.t("menu_product_combinations", "zh_CN"), "产品／组合设置"
        )

    def test_header_schema_unique_txid_desc(self) -> None:
        cols = [
            row["name"]
            for row in self.ui.store.fetchall(
                "PRAGMA table_info(product_combinations)"
            )
        ]
        self.assertEqual(
            cols,
            [
                "TxId",
                "CombinationCode",
                "CombinationName",
                "CombinationNameEn",
                "Description",
                "Remark",
                "isDisable",
                "CreatedAt",
                "UpdatedAt",
            ],
        )
        a = self.maint.create_row(
            "product_combinations",
            {"CombinationCode": "C1", "CombinationName": "組合1"},
        )
        b = self.maint.create_row(
            "product_combinations",
            {"CombinationCode": "C2", "CombinationName": "組合2"},
        )
        self.assertEqual(a["TxId"], 1)
        self.assertEqual(b["TxId"], 2)
        with self.assertRaises(ValueError):
            self.maint.create_row(
                "product_combinations",
                {"CombinationCode": "C1", "CombinationName": "重複"},
            )
        rows = self.maint.list_rows("product_combinations")
        self.assertEqual([row["TxId"] for row in rows], [2, 1])
        self.assertIsNone(
            self.ui.store.fetchone(
                "SELECT CombinationNameEn FROM product_combinations WHERE TxId=1"
            )["CombinationNameEn"]
        )

    def test_items_schema_and_itemid_rules(self) -> None:
        cols = [
            row["name"]
            for row in self.ui.store.fetchall(
                "PRAGMA table_info(product_combination_items)"
            )
        ]
        self.assertIn("ItemId", cols)
        self.assertIn("EquipmentTxId", cols)
        header = self.maint.create_row(
            "product_combinations",
            {"CombinationCode": "W1", "CombinationName": "焊槍組合"},
        )
        i1 = self.maint.create_row(
            "product_combination_items",
            {
                "CombinationTxId": header["TxId"],
                "EquipmentTxId": self.inv1["TxId"],
            },
        )
        self.assertEqual(i1["TxId"], 1)
        self.assertEqual(i1["ItemId"], 1.0)
        self.assertEqual(i1["ItemId_display"], "1.0")
        self.assertEqual(i1["Qty"], 1)
        self.assertFalse(i1["isDisable"])
        self.assertIsNone(
            self.ui.store.fetchone(
                "SELECT ItemRole FROM product_combination_items WHERE TxId=1"
            )["ItemRole"]
        )
        i2 = self.maint.create_row(
            "product_combination_items",
            {
                "CombinationTxId": header["TxId"],
                "EquipmentTxId": self.inv2["TxId"],
            },
        )
        self.assertEqual(i2["ItemId"], 2.0)
        self.maint.update_row(
            "product_combination_items",
            i2["TxId"],
            {
                "CombinationTxId": header["TxId"],
                "EquipmentTxId": self.inv2["TxId"],
                "ItemId": 1.1,
                "Qty": 1,
            },
        )
        i3 = self.maint.create_row(
            "product_combination_items",
            {
                "CombinationTxId": header["TxId"],
                "EquipmentTxId": self.inv3["TxId"],
            },
        )
        self.assertEqual(i3["ItemId"], 1.2)
        with self.assertRaises(ValueError):
            self.maint.create_row(
                "product_combination_items",
                {
                    "CombinationTxId": header["TxId"],
                    "EquipmentTxId": self.inv1["TxId"],
                },
            )
        rows = self.maint.list_rows(
            "product_combination_items",
            eq_filters={"CombinationTxId": header["TxId"]},
            sort_specs=[{"field": "ItemId", "dir": "asc"}],
        )
        self.assertEqual([row["ItemId"] for row in rows], [1.0, 1.1, 1.2])

    def test_equipment_relation_and_category_display(self) -> None:
        header = self.maint.create_row(
            "product_combinations",
            {"CombinationCode": "R1", "CombinationName": "測試"},
        )
        meta = self.maint.build_table_ui_meta("product_combination_items")
        eq_col = next(
            col for col in meta["columns"] if col["field"] == "EquipmentTxId"
        )
        values = {str(opt["value"]) for opt in eq_col["options"]}
        self.assertIn(str(self.inv1["TxId"]), values)
        self.assertNotIn(str(self.disabled["TxId"]), values)
        created = self.maint.create_row(
            "product_combination_items",
            {
                "CombinationTxId": header["TxId"],
                "EquipmentTxId": self.inv1["TxId"],
            },
        )
        self.assertEqual(created["EquipmentTxId"], self.inv1["TxId"])
        self.assertEqual(created["EquipmentCategory"], "機械臂")
        self.assertEqual(created["EquipmentTxId_category_label"], "機械臂")

    def test_master_detail_filter_and_layout(self) -> None:
        h1 = self.maint.create_row(
            "product_combinations",
            {"CombinationCode": "A", "CombinationName": "A"},
        )
        h2 = self.maint.create_row(
            "product_combinations",
            {"CombinationCode": "B", "CombinationName": "B"},
        )
        self.maint.create_row(
            "product_combination_items",
            {
                "CombinationTxId": h1["TxId"],
                "EquipmentTxId": self.inv1["TxId"],
            },
        )
        self.maint.create_row(
            "product_combination_items",
            {
                "CombinationTxId": h2["TxId"],
                "EquipmentTxId": self.inv2["TxId"],
            },
        )
        only_h1 = self.maint.list_rows(
            "product_combination_items",
            eq_filters={"CombinationTxId": h1["TxId"]},
        )
        self.assertEqual(len(only_h1), 1)
        self.assertEqual(only_h1[0]["EquipmentTxId"], self.inv1["TxId"])
        meta = self.maint.build_table_ui_meta("product_combinations")
        self.assertEqual(meta["detail"]["table_key"], "product_combination_items")
        self.assertEqual(meta["detail"]["parent_field"], "CombinationTxId")
        self.assertEqual(meta["detail"]["presentation"], "expand_row")
        self.assertEqual(meta["detail"]["title"], "組合設備")
        self.assertIn("add_label", meta["detail"])
        self.assertNotIn("tab_key", meta["detail"])
        toolbar = meta["detail"]["embedded_toolbar"]
        self.assertFalse(toolbar["show_search"])
        self.assertFalse(toolbar["show_flag_filter"])
        self.assertFalse(toolbar["show_multi_select_controls"])
        self.assertEqual(toolbar["layout_save_placement"], "chrome")
        self.assertEqual(toolbar["layout_settings_placement"], "chrome")
        self.assertEqual(
            self.ui.t("table_ui_tip_open_layout", "zh_TW"), "版面設定"
        )
        self.assertEqual(
            self.ui.t("table_ui_tip_open_layout", "en"), "Layout Settings"
        )
        self.assertEqual(
            self.ui.t("table_ui_tip_open_layout", "zh_CN"), "版面设置"
        )
        layout = self.layout.ensure_table_layout("product_combination_items")
        item_col = next(
            col for col in layout["columns"] if col["field_key"] == "ItemId"
        )
        self.assertEqual(item_col["sort_direction"], "asc")
        self.assertIn("__multi_select", {
            col["field_key"] for col in layout["columns"]
        })
        header_layout = self.layout.ensure_table_layout("product_combinations")
        self.assertNotEqual(header_layout["TxId"], layout["TxId"])
        self.assertEqual(header_layout["table_key"], "product_combinations")
        self.assertEqual(layout["table_key"], "product_combination_items")

    def test_item_edit_keeps_parent_binding(self) -> None:
        header = self.maint.create_row(
            "product_combinations",
            {"CombinationCode": "E1", "CombinationName": "編輯綁定"},
        )
        item = self.maint.create_row(
            "product_combination_items",
            {
                "CombinationTxId": header["TxId"],
                "EquipmentTxId": self.inv1["TxId"],
                "ItemRole": "primary_arm",
            },
        )
        loaded = self.maint.get_row(
            "product_combination_items", item["TxId"]
        )
        self.assertEqual(loaded["TxId"], item["TxId"])
        self.assertEqual(loaded["CombinationTxId"], header["TxId"])
        self.assertEqual(loaded["EquipmentTxId"], self.inv1["TxId"])
        self.assertEqual(loaded["ItemId"], 1.0)
        combo_col = next(
            col
            for col in self.maint.build_table_ui_meta(
                "product_combination_items"
            )["columns"]
            if col["field"] == "CombinationTxId"
        )
        self.assertFalse(combo_col["editable"])

    def test_toggle_and_timestamps(self) -> None:
        header = self.maint.create_row(
            "product_combinations",
            {"CombinationCode": "T1", "CombinationName": "時間"},
        )
        self.assertRegex(header["CreatedAt"], r"^\d{4}-\d{2}-\d{2}T")
        self.assertEqual(header["CreatedAt"], header["UpdatedAt"])
        updated = self.maint.update_row(
            "product_combinations",
            header["TxId"],
            {
                "CombinationCode": "T1",
                "CombinationName": "時間2",
            },
        )
        self.assertEqual(updated["CreatedAt"], header["CreatedAt"])
        toggled = self.maint.toggle_disable(
            "product_combinations", header["TxId"]
        )
        self.assertTrue(toggled["isDisable"])

    def test_inventory_untouched_by_combination_writes(self) -> None:
        inv_def = self.maint.get_table_def("inventory")
        self.assertEqual(inv_def["db_table"], "inventory")
        with self.assertRaises(KeyError):
            self.maint.get_table_def("equipment_settings")
        inv_count = self.ui.store.fetchone(
            "SELECT COUNT(*) AS n FROM inventory"
        )["n"]
        self.maint.create_row(
            "product_combinations",
            {"CombinationCode": "X", "CombinationName": "X"},
        )
        self.assertEqual(
            self.ui.store.fetchone("SELECT COUNT(*) AS n FROM inventory")["n"],
            inv_count,
        )


if __name__ == "__main__":
    unittest.main()
