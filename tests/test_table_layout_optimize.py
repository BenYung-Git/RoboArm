"""Isolated tests for shared table_ui layout optimize (never use formal DB)."""

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


class TableLayoutOptimizeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmp.name) / "layout_opt_test.db"
        formal = resolve_path("data/RoboArm.db").resolve()
        if self.db_path.resolve() == formal:
            raise RuntimeError("Refusing formal DB")
        self.ui = UiService(sqlite_path=str(self.db_path))
        self.maint = MaintService(self.ui)
        self.layout = TableLayoutService(self.ui, self.maint)

    def tearDown(self) -> None:
        self.layout = None
        self.maint = None
        self.ui = None
        gc.collect()
        self._tmp.cleanup()

    def _payload_from_layout(self, layout: dict, **overrides: object) -> dict:
        columns = []
        for col in layout["columns"]:
            item = {
                "field_key": col["field_key"],
                "visible": col["visible"],
                "sort_direction": col["sort_direction"],
                "column_width": col["column_width"],
            }
            field = col["field_key"]
            if field in overrides:
                item.update(overrides[field])  # type: ignore[arg-type]
            columns.append(item)
        return {
            "zebra_enabled": layout["zebra_enabled"],
            "zebra_color": layout["zebra_color"],
            "columns": columns,
        }

    def test_save_icon_tooltip_trilingual(self) -> None:
        self.assertEqual(
            self.ui.t("table_ui_tip_layout", "zh_TW"), "儲存版面設定"
        )
        self.assertEqual(
            self.ui.t("table_ui_tip_layout", "en"), "Save Layout Settings"
        )
        self.assertEqual(
            self.ui.t("table_ui_tip_layout", "zh_CN"), "保存版面设置"
        )
        self.assertEqual(self.ui.t("table_ui_icon_layout", "zh_TW"), "▦")
        self.assertEqual(
            self.ui.t("table_ui_icon_layout_save_badge", "zh_TW"), "💾"
        )
        meta = self.maint.build_table_ui_meta("inventory")
        self.assertEqual(meta["labels"]["tip_layout"], "儲存版面設定")
        self.assertEqual(meta["labels"]["layout_column_width"], "欄寬")
        self.assertEqual(meta["labels"]["icon_layout_save_badge"], "💾")

    def test_multi_select_defaults_and_width_range(self) -> None:
        for table_key in ("inventory", "categories", "equipment_settings"):
            layout = self.layout.ensure_table_layout(table_key)
            ms = next(
                col
                for col in layout["columns"]
                if col["field_key"] == "__multi_select"
            )
            self.assertTrue(ms["is_system"])
            self.assertEqual(ms["column_width"], 48)
            self.assertEqual(ms["width_min"], 40)
            self.assertEqual(ms["width_max"], 80)
            self.assertNotIn("__multi_select", layout["list_fields"])
            self.assertEqual(layout["width_rules"]["data"]["min"], 60)
            self.assertEqual(layout["width_rules"]["data"]["max"], 600)
            self.assertEqual(layout["width_rules"]["data"]["default"], 100)

    def test_save_column_widths_including_txid_and_multi_select(self) -> None:
        layout = self.layout.ensure_table_layout("inventory")
        payload = self._payload_from_layout(
            layout,
            __multi_select={"column_width": 56},
            TxId={"column_width": 120},
            ItemName={"column_width": 220},
        )
        saved = self.layout.save_layout("inventory", payload)
        by_key = {col["field_key"]: col for col in saved["columns"]}
        self.assertEqual(by_key["__multi_select"]["column_width"], 56)
        self.assertEqual(by_key["TxId"]["column_width"], 120)
        self.assertEqual(by_key["ItemName"]["column_width"], 220)
        reloaded = self.layout.get_layout("inventory")
        by_reload = {col["field_key"]: col for col in reloaded["columns"]}
        self.assertEqual(by_reload["__multi_select"]["column_width"], 56)
        self.assertEqual(by_reload["TxId"]["column_width"], 120)

    def test_width_range_validation(self) -> None:
        layout = self.layout.ensure_table_layout("equipment_settings")
        with self.assertRaises(ValueError):
            self.layout.save_layout(
                "equipment_settings",
                self._payload_from_layout(
                    layout, __multi_select={"column_width": 20}
                ),
            )
        with self.assertRaises(ValueError):
            self.layout.save_layout(
                "equipment_settings",
                self._payload_from_layout(layout, TxId={"column_width": 50}),
            )
        with self.assertRaises(ValueError):
            self.layout.save_layout(
                "equipment_settings",
                self._payload_from_layout(layout, TxId={"column_width": 700}),
            )

    def test_sort_and_zebra_saved_together(self) -> None:
        layout = self.layout.ensure_table_layout("categories")
        color = layout["zebra_color_options"][1]["color_key"]
        payload = self._payload_from_layout(
            layout,
            CategoryCode={
                "visible": True,
                "sort_direction": "asc",
                "column_width": 160,
            },
            TxId={"sort_direction": "", "column_width": 100},
        )
        payload["zebra_enabled"] = False
        payload["zebra_color"] = color
        saved = self.layout.save_layout("categories", payload)
        self.assertFalse(saved["zebra_enabled"])
        self.assertEqual(saved["zebra_color"], color)
        by_key = {col["field_key"]: col for col in saved["columns"]}
        self.assertEqual(by_key["CategoryCode"]["sort_direction"], "asc")
        self.assertEqual(by_key["CategoryCode"]["column_width"], 160)

    def test_same_flow_all_table_ui_hosts(self) -> None:
        for table_key in ("inventory", "categories", "equipment_settings"):
            layout = self.layout.ensure_table_layout(table_key)
            self.assertIn("__multi_select", {
                col["field_key"] for col in layout["columns"]
            })
            saved = self.layout.save_layout(
                table_key,
                self._payload_from_layout(
                    layout, __multi_select={"column_width": 44}
                ),
            )
            ms = next(
                col
                for col in saved["columns"]
                if col["field_key"] == "__multi_select"
            )
            self.assertEqual(ms["column_width"], 44)


if __name__ == "__main__":
    unittest.main()
