"""Isolated tests for equipment_settings retirement (never use formal DB)."""

from __future__ import annotations

import gc
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.ui_service import UiService
from app.storage.config_store import resolve_path


class EquipmentSettingsRetireTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmp.name) / "equip_retire_test.db"
        formal = resolve_path("data/RoboArm.db").resolve()
        if self.db_path.resolve() == formal:
            raise RuntimeError("Refusing formal DB")
        self.ui = UiService(sqlite_path=str(self.db_path))

    def tearDown(self) -> None:
        self.ui = None
        gc.collect()
        self._tmp.cleanup()

    def _menu_keys(self) -> set[str]:
        return {
            row["menu_key"]
            for row in self.ui.store.fetchall("SELECT menu_key FROM menus")
        }

    def _insert_legacy_equipment_artifacts(self) -> None:
        self.ui.store.execute(
            """
            INSERT INTO menus (menu_key, route_path, sort_order, label_key)
            VALUES (?, ?, ?, ?)
            """,
            (
                "equipment_settings",
                "/page/equipment_settings",
                6,
                "menu_equipment_settings",
            ),
        )
        self.ui.store.execute(
            """
            INSERT INTO menus (menu_key, route_path, sort_order, label_key)
            VALUES (?, ?, ?, ?)
            """,
            (
                "custom_lab_menu",
                "/page/custom_lab_menu",
                99,
                "menu_custom_lab",
            ),
        )
        self.ui.store.execute(
            """
            INSERT INTO ui_text (TxId, text_key, zh_TW, en, zh_CN, isDisable)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (
                self.ui.next_txid("ui_text"),
                "menu_equipment_settings",
                "機械臂及電控櫃設定",
                "Robot Arm & Control Cabinet Settings",
                "机械臂及电控柜设置",
            ),
        )
        keep_txid = self.ui.next_txid("ui_text")
        self.ui.store.execute(
            """
            INSERT INTO ui_text (TxId, text_key, zh_TW, en, zh_CN, isDisable)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (
                keep_txid,
                "menu_custom_lab",
                "自訂實驗室",
                "Custom Lab",
                "自定义实验室",
            ),
        )
        self.ui.store.execute(
            """
            CREATE TABLE IF NOT EXISTS equipment_settings (
                TxId INTEGER PRIMARY KEY,
                EquipmentTxId INTEGER NOT NULL UNIQUE,
                Remark TEXT,
                isDisable INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.ui.store.execute(
            "INSERT INTO equipment_settings (TxId, EquipmentTxId, Remark, isDisable) "
            "VALUES (1, 100, 'legacy', 0)"
        )
        self.ui.store.execute(
            """
            CREATE TABLE IF NOT EXISTS ui_table_settings (
                TxId INTEGER PRIMARY KEY,
                table_key TEXT NOT NULL UNIQUE,
                table_name TEXT NOT NULL,
                zebra_enabled INTEGER NOT NULL DEFAULT 1,
                zebra_color TEXT NOT NULL DEFAULT 'light_blue',
                isDisable INTEGER NOT NULL DEFAULT 0,
                Remark TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.ui.store.execute(
            """
            CREATE TABLE IF NOT EXISTS ui_table_columns (
                TxId INTEGER PRIMARY KEY,
                table_setting_id INTEGER NOT NULL,
                field_key TEXT NOT NULL,
                field_label_key TEXT NOT NULL,
                field_desc_key TEXT NOT NULL,
                visible INTEGER NOT NULL DEFAULT 0,
                display_order INTEGER NOT NULL DEFAULT 0,
                sort_direction TEXT NOT NULL DEFAULT '',
                column_width INTEGER NOT NULL DEFAULT 100,
                isDisable INTEGER NOT NULL DEFAULT 0,
                Remark TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (table_setting_id, field_key)
            )
            """
        )
        self.ui.store.execute(
            """
            INSERT INTO ui_table_settings (
                TxId, table_key, table_name, zebra_enabled, zebra_color,
                isDisable, Remark, created_at, updated_at
            )
            VALUES (9001, 'equipment_settings', 'maint_table_equipment_settings',
                    1, 'blue', 0, '', 't', 't')
            """
        )
        self.ui.store.execute(
            """
            INSERT INTO ui_table_settings (
                TxId, table_key, table_name, zebra_enabled, zebra_color,
                isDisable, Remark, created_at, updated_at
            )
            VALUES (9002, 'inventory', 'maint_table_inventory',
                    1, 'blue', 0, '', 't', 't')
            """
        )
        self.ui.store.execute(
            """
            INSERT INTO ui_table_columns (
                TxId, table_setting_id, field_key, field_label_key, field_desc_key,
                visible, display_order, sort_direction, isDisable, Remark,
                created_at, updated_at, column_width
            )
            VALUES (9101, 9001, 'TxId', 'field_txid', 'field_desc_txid',
                    1, 1, '', 0, '', 't', 't', 100)
            """
        )
        self.ui.store.execute(
            """
            INSERT INTO ui_table_columns (
                TxId, table_setting_id, field_key, field_label_key, field_desc_key,
                visible, display_order, sort_direction, isDisable, Remark,
                created_at, updated_at, column_width
            )
            VALUES (9102, 9002, 'TxId', 'field_txid', 'field_desc_txid',
                    1, 1, '', 0, '', 't', 't', 100)
            """
        )

    def test_retire_removes_equipment_menu_keeps_custom_menu(self) -> None:
        self._insert_legacy_equipment_artifacts()
        keys_before = self._menu_keys()
        self.assertIn("equipment_settings", keys_before)
        self.assertIn("custom_lab_menu", keys_before)

        self.ui.retire_equipment_settings_feature()

        keys = self._menu_keys()
        self.assertNotIn("equipment_settings", keys)
        self.assertIn("custom_lab_menu", keys)
        self.assertIn("inventory", keys)
        self.assertIsNone(
            self.ui.store.fetchone(
                "SELECT text_key FROM ui_text WHERE text_key = ?",
                ("menu_equipment_settings",),
            )
        )
        self.assertIsNotNone(
            self.ui.store.fetchone(
                "SELECT text_key FROM ui_text WHERE text_key = ?",
                ("menu_custom_lab",),
            )
        )
        self.assertIsNone(
            self.ui.store.fetchone(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name = 'equipment_settings'"
            )
        )
        self.assertIsNone(
            self.ui.store.fetchone(
                "SELECT TxId FROM ui_table_settings WHERE table_key = ?",
                ("equipment_settings",),
            )
        )
        self.assertIsNotNone(
            self.ui.store.fetchone(
                "SELECT TxId FROM ui_table_settings WHERE table_key = ?",
                ("inventory",),
            )
        )
        self.assertIsNotNone(
            self.ui.store.fetchone(
                "SELECT TxId FROM ui_table_columns WHERE TxId = ?",
                (9102,),
            )
        )

    def test_ensure_seed_menus_does_not_remove_custom_menu(self) -> None:
        self.ui.store.execute(
            """
            INSERT INTO menus (menu_key, route_path, sort_order, label_key)
            VALUES (?, ?, ?, ?)
            """,
            (
                "custom_lab_menu",
                "/page/custom_lab_menu",
                99,
                "menu_custom_lab",
            ),
        )
        self.ui.ensure_seed_menus()
        self.assertIn("custom_lab_menu", self._menu_keys())
        self.assertNotIn("equipment_settings", self._menu_keys())

    def test_retire_is_idempotent(self) -> None:
        self._insert_legacy_equipment_artifacts()
        self.ui.retire_equipment_settings_feature()
        self.ui.retire_equipment_settings_feature()
        self.ui.ensure_seed_menus()
        keys = self._menu_keys()
        self.assertNotIn("equipment_settings", keys)
        self.assertIn("custom_lab_menu", keys)
        self.assertIn("inventory", keys)


if __name__ == "__main__":
    unittest.main()
