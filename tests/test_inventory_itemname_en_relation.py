"""Isolated tests for Inventory ItemNameEn + Category relation."""

from __future__ import annotations

import gc
import tempfile
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.maint_service import MaintService
from app.services.ui_service import UiService
from app.storage.config_store import resolve_path


class InventoryItemNameEnRelationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmp.name) / "inv_test.db"
        formal = resolve_path("data/RoboArm.db").resolve()
        if self.db_path.resolve() == formal:
            raise RuntimeError("Refusing formal DB")
        self.ui = UiService(sqlite_path=str(self.db_path))
        self.maint = MaintService(self.ui)
        # seed categories for inventory group
        self.arm = self.maint.create_row(
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
        self.box = self.maint.create_row(
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

    def tearDown(self) -> None:
        self.maint = None
        self.ui = None
        gc.collect()
        self._tmp.cleanup()

    def test_schema_itemname_en_and_category_integer(self) -> None:
        cols = {
            r["name"]: r["type"]
            for r in self.ui.store.fetchall("PRAGMA table_info(inventory)")
        }
        self.assertEqual(cols["ItemNameEn"], "TEXT")
        self.assertEqual(cols["Category"], "INTEGER")
        cat = next(
            c
            for c in self.maint.get_table_def("inventory")["columns"]
            if c["field"] == "Category"
        )
        self.assertEqual(cat["field_type"], "relation")
        self.assertEqual(cat["relation"]["order_by"], [{"field_from": "label_lang", "dir": "asc"}])

    def test_itemname_en_required_no_blank(self) -> None:
        with self.assertRaises(ValueError):
            self.maint.create_row(
                "inventory",
                {
                    "ItemCode": "x",
                    "ItemName": "名",
                    "ItemNameEn": "   ",
                    "Category": self.arm["TxId"],
                    "Brand": "a",
                    "Model": "b",
                    "SerialNo": "s",
                    "Quantity": 1,
                    "Unit": "台",
                    "Location": "L",
                    "dimensions": "",
                    "Remark": "",
                },
            )

    def test_create_arm_and_cab_mapping(self) -> None:
        arm = self.maint.create_row(
            "inventory",
            {
                "ItemCode": "robot5_arm",
                "ItemName": "jaka zu7 機械臂",
                "ItemNameEn": "jaka zu7 Robot Arm",
                "Category": self.arm["TxId"],
                "Brand": "jaka",
                "Model": "zu7",
                "SerialNo": "C5100218",
                "Quantity": 1,
                "Unit": "台",
                "Location": "坪輋第三倉",
                "dimensions": "",
                "Remark": "來源：MasterUi/robot_setting.yaml；來源項目：robot5",
            },
        )
        cab = self.maint.create_row(
            "inventory",
            {
                "ItemCode": "robot5_cab",
                "ItemName": "jaka 控制櫃",
                "ItemNameEn": "jaka Control Cabinet",
                "Category": self.box["TxId"],
                "Brand": "jaka",
                "Model": "",
                "SerialNo": "CAB7212451",
                "Quantity": 1,
                "Unit": "台",
                "Location": "坪輋第三倉",
                "dimensions": "",
                "Remark": "來源：MasterUi/robot_setting.yaml；來源項目：robot5",
            },
        )
        self.assertEqual(int(arm["Category"]), int(self.arm["TxId"]))
        self.assertEqual(arm["Category_label"], "機械臂")
        self.assertEqual(cab["Model"], "")
        self.assertEqual(cab["Category_label"], "控制櫃")

    def test_category_options_label_lang_asc_no_txid_tiebreak_config(self) -> None:
        meta_en = self.maint.build_meta("inventory", "en")
        cat = next(c for c in meta_en["columns"] if c["field"] == "Category")
        labels = [o["label"] for o in cat["options"]]
        self.assertEqual(labels, sorted(labels))
        self.assertEqual(labels, ["Control Cabinet", "Robot Arm"])
        order_by = cat.get("relation") or next(
            c for c in self.maint.get_table_def("inventory")["columns"] if c["field"] == "Category"
        )["relation"]["order_by"]
        self.assertEqual(len(order_by), 1)
        self.assertEqual(order_by[0]["field_from"], "label_lang")

    def test_itemname_en_labels_i18n(self) -> None:
        meta_tw = self.maint.build_meta("inventory", "zh_TW")
        meta_en = self.maint.build_meta("inventory", "en")
        meta_cn = self.maint.build_meta("inventory", "zh_CN")
        tw = next(c for c in meta_tw["columns"] if c["field"] == "ItemNameEn")
        en = next(c for c in meta_en["columns"] if c["field"] == "ItemNameEn")
        cn = next(c for c in meta_cn["columns"] if c["field"] == "ItemNameEn")
        self.assertEqual(tw["label"], "英文名稱")
        self.assertEqual(en["label"], "English Name")
        self.assertEqual(cn["label"], "英文名称")


if __name__ == "__main__":
    unittest.main()
