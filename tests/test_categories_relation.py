"""Isolated SQLite tests for categories + relation (never use data/RoboArm.db)."""

from __future__ import annotations

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


class CategoriesRelationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmp.name) / "test_categories.db"
        if not str(self.db_path).strip():
            raise RuntimeError("Test database path missing")
        self.ui = UiService(sqlite_path=str(self.db_path))
        self.maint = MaintService(self.ui)
        self.layout = TableLayoutService(self.ui, self.maint)

    def tearDown(self) -> None:
        self.layout = None
        self.maint = None
        self.ui = None
        import gc

        gc.collect()
        self._tmp.cleanup()

    def test_supports_categories_required(self) -> None:
        tables = self.maint.get_tables_config()["tables"]
        for table_key, table_def in tables.items():
            self.assertIn("supports_categories", table_def)
            self.assertIsInstance(table_def["supports_categories"], bool)

    def test_categories_schema_has_no_sort_order(self) -> None:
        cols = {
            row["name"]
            for row in self.ui.store.fetchall("PRAGMA table_info(categories)")
        }
        self.assertNotIn("SortOrder", cols)
        fields = [
            column["field"]
            for column in self.maint.get_table_def("categories")["columns"]
        ]
        self.assertNotIn("SortOrder", fields)

    def test_category_group_options_only_supports_true(self) -> None:
        meta = self.maint.build_table_ui_meta("categories")
        column = next(
            item for item in meta["columns"] if item["field"] == "CategoryGroup"
        )
        values = [str(option["value"]) for option in column["options"]]
        self.assertEqual(values, ["inventory"])
        self.assertNotIn("ui_text", values)
        self.assertNotIn("categories", values)

    def test_create_category_and_unique_code(self) -> None:
        created = self.maint.create_row(
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
        self.assertEqual(created["CategoryGroup"], "inventory")
        self.assertEqual(created["CategoryGroup_label"], "存貨")
        self.assertNotIn("SortOrder", created)
        with self.assertRaises(ValueError):
            self.maint.create_row(
                "categories",
                {
                    "CategoryGroup": "inventory",
                    "CategoryCode": "robot_arm",
                    "zh_TW": "重複",
                    "en": "Dup",
                    "zh_CN": "重复",
                    "Remark": "",
                },
            )

    def test_create_and_update_without_sort_order(self) -> None:
        created = self.maint.create_row(
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
        updated = self.maint.update_row(
            "categories",
            created["TxId"],
            {
                "CategoryGroup": "inventory",
                "CategoryCode": "tool",
                "zh_TW": "工具A",
                "en": "Tool A",
                "zh_CN": "工具A",
                "Remark": "note",
            },
        )
        self.assertEqual(updated["zh_TW"], "工具A")
        self.assertNotIn("SortOrder", updated)

    def test_same_code_different_group_allowed_when_second_group_exists(self) -> None:
        self.maint.create_row(
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
        rows = self.maint.list_rows("categories", flag_filters={"isDisable": ""})
        self.assertEqual(len(rows), 1)

    def test_empty_name_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.maint.create_row(
                "categories",
                {
                    "CategoryGroup": "inventory",
                    "CategoryCode": "blank",
                    "zh_TW": "   ",
                    "en": "Blank",
                    "zh_CN": "空白",
                    "Remark": "",
                },
            )

    def test_fixed_field_order_by_unchanged_for_category_group(self) -> None:
        meta = self.maint.build_table_ui_meta("categories", "zh_TW")
        column = next(c for c in meta["columns"] if c["field"] == "CategoryGroup")
        self.assertEqual([o["value"] for o in column["options"]], ["inventory"])

    def test_layout_for_categories(self) -> None:
        layout = self.layout.ensure_table_layout("categories")
        self.assertEqual(layout["table_key"], "categories")
        self.assertTrue(len(layout["list_fields"]) > 0)
        self.assertNotIn("SortOrder", layout["list_fields"])

    def test_source_table_host_tabs(self) -> None:
        host = self.ui.get_table_ui_for_menu("source_table", "zh_TW")
        self.assertIsNotNone(host)
        assert host is not None
        self.assertEqual(host["tabs"][0]["label"], "分類表")
        self.assertEqual(host["tabs"][0]["table_key"], "categories")
        inventory_host = self.ui.get_table_ui_for_menu("inventory", "zh_TW")
        self.assertIsNotNone(inventory_host)
        assert inventory_host is not None
        self.assertEqual(inventory_host["table_key"], "inventory")
        self.assertEqual(inventory_host["tabs"], [])


if __name__ == "__main__":
    if "--db" in sys.argv:
        raise SystemExit(
            "Pass DB via UiService(sqlite_path=...); do not use CLI fallback"
        )
    unittest.main()
