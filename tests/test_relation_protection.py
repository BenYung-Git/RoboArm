"""Isolated relation tests (never use data/RoboArm.db)."""

from __future__ import annotations

import copy
import gc
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.maint_service import MaintService
from app.services.ui_service import UiService
from app.storage.config_store import load_app_config, resolve_path
from app.storage.json_store import load_json


REF_TABLE_KEY = "ref_items"
REF_DB_TABLE = "ref_items"


def _build_test_tables_config() -> dict:
    data = load_json(resolve_path(load_app_config()["maint_tables_path"]))
    tables = copy.deepcopy(data["tables"])
    tables[REF_TABLE_KEY] = {
        "db_table": REF_DB_TABLE,
        "label_key": "maint_table_inventory",
        "supports_categories": True,
        "columns": [
            {
                "field": "TxId",
                "label_key": "field_txid",
                "field_type": "long",
                "is_flag": False,
                "editable": False,
                "auto_gen": True,
                "required": True,
            },
            {
                "field": "ItemName",
                "label_key": "field_item_name",
                "field_type": "text",
                "is_flag": False,
                "editable": True,
                "auto_gen": False,
                "required": True,
            },
            {
                "field": "Category",
                "label_key": "field_category",
                "field_type": "relation",
                "is_flag": False,
                "editable": True,
                "auto_gen": False,
                "required": True,
                "relation": {
                    "source_kind": "table",
                    "source_table_key": "categories",
                    "value_field": "TxId",
                    "label": {
                        "kind": "row_lang_fields",
                        "fields": {
                            "zh_TW": "zh_TW",
                            "en": "en",
                            "zh_CN": "zh_CN",
                        },
                    },
                    "filters": [
                        {
                            "field": "CategoryGroup",
                            "op": "eq",
                            "value_from": "current_table_key",
                        },
                        {
                            "field": "isDisable",
                            "op": "eq",
                            "value": 0,
                            "selection_only": True,
                        },
                    ],
                    "order_by": [
                        {"field_from": "label_lang", "dir": "asc"},
                    ],
                },
            },
            {
                "field": "isDisable",
                "label_key": "field_is_disable",
                "field_type": "flag",
                "is_flag": True,
                "editable": False,
                "auto_gen": False,
                "required": True,
                "default_value": False,
            },
            {
                "field": "Remark",
                "label_key": "field_remark",
                "field_type": "text",
                "is_flag": False,
                "editable": True,
                "auto_gen": False,
                "required": False,
            },
        ],
    }
    data["tables"] = tables
    return data


class RelationProtectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmp.name) / "relation_test.db"
        self.tables_path = Path(self._tmp.name) / "tables.json"
        if not str(self.db_path).strip():
            raise RuntimeError("Test database path missing")
        if self.db_path.resolve() == resolve_path("data/RoboArm.db").resolve():
            raise RuntimeError("Refusing to use formal database for tests")

        tables_data = _build_test_tables_config()
        self.tables_path.write_text(
            json.dumps(tables_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        config = copy.deepcopy(load_app_config())
        config["maint_tables_path"] = str(self.tables_path)
        config["sqlite_path"] = str(self.db_path)
        self.ui = UiService(sqlite_path=str(self.db_path), config=config)
        self.ui.store.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {REF_DB_TABLE} (
                TxId INTEGER PRIMARY KEY,
                ItemName TEXT NOT NULL,
                Category INTEGER NOT NULL,
                isDisable INTEGER NOT NULL DEFAULT 0,
                Remark TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self.maint = MaintService(self.ui)

    def tearDown(self) -> None:
        self.maint = None
        self.ui = None
        gc.collect()
        self._tmp.cleanup()

    def _create_category(
        self,
        *,
        group: str,
        code: str,
        zh_tw: str,
        en: str,
        zh_cn: str,
    ) -> dict:
        return self.maint.create_row(
            "categories",
            {
                "CategoryGroup": group,
                "CategoryCode": code,
                "zh_TW": zh_tw,
                "en": en,
                "zh_CN": zh_cn,
                "Remark": "",
            },
        )

    def _category_column(self) -> dict:
        return next(
            c
            for c in self.maint.get_table_def(REF_TABLE_KEY)["columns"]
            if c["field"] == "Category"
        )

    def test_full_category_crud_and_disable(self) -> None:
        created = self._create_category(
            group="inventory",
            code="robot_arm",
            zh_tw="機械臂",
            en="Robot Arm",
            zh_cn="机械臂",
        )
        txid = created["TxId"]
        loaded = self.maint.get_row("categories", txid)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["CategoryCode"], "robot_arm")
        self.assertNotIn("SortOrder", loaded)
        updated = self.maint.update_row(
            "categories",
            txid,
            {
                "CategoryGroup": "inventory",
                "CategoryCode": "robot_arm",
                "zh_TW": "機械臂A",
                "en": "Robot Arm A",
                "zh_CN": "机械臂A",
                "Remark": "note",
            },
        )
        self.assertEqual(updated["zh_TW"], "機械臂A")
        disabled = self.maint.toggle_disable("categories", txid)
        self.assertTrue(disabled["isDisable"])
        enabled = self.maint.toggle_disable("categories", txid)
        self.assertFalse(enabled["isDisable"])

    def test_label_lang_orders_by_current_language_name_asc(self) -> None:
        # Insert in non-alpha TxId order; options must follow language name ASC only.
        self._create_category(
            group=REF_TABLE_KEY,
            code="z_last",
            zh_tw="香蕉",
            en="Banana",
            zh_cn="香蕉",
        )
        self._create_category(
            group=REF_TABLE_KEY,
            code="a_first",
            zh_tw="蘋果",
            en="Apple",
            zh_cn="苹果",
        )
        self._create_category(
            group=REF_TABLE_KEY,
            code="m_mid",
            zh_tw="芒果",
            en="Mango",
            zh_cn="芒果",
        )
        column = self._category_column()
        tw = [
            o["label"]
            for o in self.maint.relations.resolve_options(
                REF_TABLE_KEY, column, "zh_TW", for_selection=True
            )
        ]
        en = [
            o["label"]
            for o in self.maint.relations.resolve_options(
                REF_TABLE_KEY, column, "en", for_selection=True
            )
        ]
        cn = [
            o["label"]
            for o in self.maint.relations.resolve_options(
                REF_TABLE_KEY, column, "zh_CN", for_selection=True
            )
        ]
        self.assertEqual(tw, sorted(tw))
        self.assertEqual(en, ["Apple", "Banana", "Mango"])
        self.assertEqual(cn, sorted(cn))
        self.assertEqual(en, sorted(en))

    def test_label_lang_does_not_add_code_or_txid_tiebreak(self) -> None:
        self._create_category(
            group=REF_TABLE_KEY,
            code="code_b",
            zh_tw="同名",
            en="Same",
            zh_cn="同名",
        )
        self._create_category(
            group=REF_TABLE_KEY,
            code="code_a",
            zh_tw="同名",
            en="Same",
            zh_cn="同名",
        )
        column = self._category_column()
        options = self.maint.relations.resolve_options(
            REF_TABLE_KEY, column, "en", for_selection=True
        )
        self.assertEqual([o["label"] for o in options], ["Same", "Same"])
        codes = []
        for option in options:
            row = self.maint.get_row("categories", int(option["value"]))
            assert row is not None
            codes.append(row["CategoryCode"])
        # Stable input order (TxId insert order), not CategoryCode ASC.
        self.assertEqual(codes, ["code_b", "code_a"])

    def test_label_lang_empty_name_raises(self) -> None:
        created = self._create_category(
            group=REF_TABLE_KEY,
            code="cab",
            zh_tw="控制櫃",
            en="Control Cabinet",
            zh_cn="控制柜",
        )
        self.ui.store.execute(
            "UPDATE categories SET en = '' WHERE TxId = ?",
            (created["TxId"],),
        )
        with self.assertRaises(ValueError):
            self.maint.relations.resolve_options(
                REF_TABLE_KEY, self._category_column(), "en", for_selection=True
            )

    def test_fixed_field_order_by_unaffected(self) -> None:
        meta = self.maint.build_table_ui_meta("categories", "zh_TW")
        group = next(c for c in meta["columns"] if c["field"] == "CategoryGroup")
        values = [o["value"] for o in group["options"]]
        self.assertEqual(values, sorted(values))
        self.assertIn("inventory", values)
        self.assertIn(REF_TABLE_KEY, values)

    def test_language_labels_for_tab_fields_group_list_and_relation(self) -> None:
        self._create_category(
            group=REF_TABLE_KEY,
            code="cab",
            zh_tw="控制櫃",
            en="Control Cabinet",
            zh_cn="控制柜",
        )
        host_tw = self.ui.get_table_ui_for_menu("source_table", "zh_TW")
        host_en = self.ui.get_table_ui_for_menu("source_table", "en")
        host_cn = self.ui.get_table_ui_for_menu("source_table", "zh_CN")
        assert host_tw and host_en and host_cn
        self.assertEqual(host_tw["tabs"][0]["label"], "分類表")
        self.assertEqual(host_en["tabs"][0]["label"], "Categories")
        self.assertEqual(host_cn["tabs"][0]["label"], "分类表")

        meta_tw = self.maint.build_table_ui_meta("categories", "zh_TW")
        meta_en = self.maint.build_table_ui_meta("categories", "en")
        meta_cn = self.maint.build_table_ui_meta("categories", "zh_CN")
        field_tw = next(c for c in meta_tw["columns"] if c["field"] == "CategoryCode")
        field_en = next(c for c in meta_en["columns"] if c["field"] == "CategoryCode")
        field_cn = next(c for c in meta_cn["columns"] if c["field"] == "CategoryCode")
        self.assertEqual(field_tw["label"], "分類代碼")
        self.assertEqual(field_en["label"], "Category Code")
        self.assertEqual(field_cn["label"], "分类代码")

        group_tw = next(c for c in meta_tw["columns"] if c["field"] == "CategoryGroup")
        group_en = next(c for c in meta_en["columns"] if c["field"] == "CategoryGroup")
        group_cn = next(c for c in meta_cn["columns"] if c["field"] == "CategoryGroup")
        inv_tw = next(o for o in group_tw["options"] if o["value"] == "inventory")
        inv_en = next(o for o in group_en["options"] if o["value"] == "inventory")
        inv_cn = next(o for o in group_cn["options"] if o["value"] == "inventory")
        self.assertEqual(inv_tw["label"], "存貨")
        self.assertEqual(inv_en["label"], "Inventory")
        self.assertEqual(inv_cn["label"], "存货")

        rows_tw = self.maint.list_rows("categories", language="zh_TW")
        rows_en = self.maint.list_rows("categories", language="en")
        rows_cn = self.maint.list_rows("categories", language="zh_CN")
        self.assertEqual(rows_tw[0]["zh_TW"], "控制櫃")
        self.assertEqual(rows_en[0]["en"], "Control Cabinet")
        self.assertEqual(rows_cn[0]["zh_CN"], "控制柜")

        rel_tw = self.maint.build_meta(REF_TABLE_KEY, "zh_TW")
        rel_en = self.maint.build_meta(REF_TABLE_KEY, "en")
        rel_cn = self.maint.build_meta(REF_TABLE_KEY, "zh_CN")
        cat_tw = next(c for c in rel_tw["columns"] if c["field"] == "Category")
        cat_en = next(c for c in rel_en["columns"] if c["field"] == "Category")
        cat_cn = next(c for c in rel_cn["columns"] if c["field"] == "Category")
        self.assertEqual(cat_tw["options"][0]["label"], "控制櫃")
        self.assertEqual(cat_en["options"][0]["label"], "Control Cabinet")
        self.assertEqual(cat_cn["options"][0]["label"], "控制柜")

    def test_missing_language_name_has_no_fallback(self) -> None:
        created = self._create_category(
            group=REF_TABLE_KEY,
            code="cab",
            zh_tw="控制櫃",
            en="Control Cabinet",
            zh_cn="控制柜",
        )
        self.ui.store.execute(
            "UPDATE categories SET en = '' WHERE TxId = ?",
            (created["TxId"],),
        )
        with self.assertRaises(ValueError):
            self.maint.relations.resolve_label(
                REF_TABLE_KEY, self._category_column(), created["TxId"], "en"
            )

    def test_cross_table_category_rejected(self) -> None:
        other = self._create_category(
            group="inventory",
            code="robot_arm",
            zh_tw="機械臂",
            en="Robot Arm",
            zh_cn="机械臂",
        )
        with self.assertRaises(ValueError):
            self.maint.create_row(
                REF_TABLE_KEY,
                {
                    "ItemName": "x",
                    "Category": other["TxId"],
                    "Remark": "",
                },
            )

    def test_disabled_not_offered_for_new_selection(self) -> None:
        created = self._create_category(
            group=REF_TABLE_KEY,
            code="cab",
            zh_tw="控制櫃",
            en="Control Cabinet",
            zh_cn="控制柜",
        )
        self.maint.toggle_disable("categories", created["TxId"])
        options = self.maint.relations.resolve_options(
            REF_TABLE_KEY, self._category_column(), "zh_TW", for_selection=True
        )
        values = [str(o["value"]) for o in options]
        self.assertNotIn(str(created["TxId"]), values)

    def test_old_record_keeps_disabled_category_and_allows_other_edits(self) -> None:
        created = self._create_category(
            group=REF_TABLE_KEY,
            code="cab",
            zh_tw="控制櫃",
            en="Control Cabinet",
            zh_cn="控制柜",
        )
        item = self.maint.create_row(
            REF_TABLE_KEY,
            {
                "ItemName": "device-1",
                "Category": created["TxId"],
                "Remark": "",
            },
        )
        self.maint.toggle_disable("categories", created["TxId"])
        updated = self.maint.update_row(
            REF_TABLE_KEY,
            item["TxId"],
            {
                "ItemName": "device-1-renamed",
                "Category": created["TxId"],
                "Remark": "keep",
            },
        )
        self.assertEqual(updated["ItemName"], "device-1-renamed")
        self.assertEqual(int(updated["Category"]), int(created["TxId"]))
        self.assertEqual(updated["Category_label"], "控制櫃")

    def test_referenced_category_cannot_change_group(self) -> None:
        created = self._create_category(
            group=REF_TABLE_KEY,
            code="cab",
            zh_tw="控制櫃",
            en="Control Cabinet",
            zh_cn="控制柜",
        )
        self.maint.create_row(
            REF_TABLE_KEY,
            {
                "ItemName": "device-1",
                "Category": created["TxId"],
                "Remark": "",
            },
        )
        with self.assertRaises(ValueError):
            self.maint.update_row(
                "categories",
                created["TxId"],
                {
                    "CategoryGroup": "inventory",
                    "CategoryCode": "cab",
                    "zh_TW": "控制櫃",
                    "en": "Control Cabinet",
                    "zh_CN": "控制柜",
                    "Remark": "",
                },
            )

    def test_relation_list_edit_save_consistency(self) -> None:
        created = self._create_category(
            group=REF_TABLE_KEY,
            code="cab",
            zh_tw="控制櫃",
            en="Control Cabinet",
            zh_cn="控制柜",
        )
        item = self.maint.create_row(
            REF_TABLE_KEY,
            {
                "ItemName": "device-1",
                "Category": created["TxId"],
                "Remark": "",
            },
        )
        listed = self.maint.list_rows(REF_TABLE_KEY, language="zh_TW")
        self.assertEqual(listed[0]["Category_label"], "控制櫃")
        loaded = self.maint.get_row(REF_TABLE_KEY, item["TxId"])
        assert loaded is not None
        self.assertEqual(loaded["Category_label"], "控制櫃")
        meta = self.maint.build_meta(REF_TABLE_KEY, "zh_TW")
        cat_col = next(c for c in meta["columns"] if c["field"] == "Category")
        option_values = [str(o["value"]) for o in cat_col["options"]]
        self.assertIn(str(created["TxId"]), option_values)
        saved = self.maint.update_row(
            REF_TABLE_KEY,
            item["TxId"],
            {
                "ItemName": "device-1",
                "Category": created["TxId"],
                "Remark": "ok",
            },
        )
        self.assertEqual(int(saved["Category"]), int(created["TxId"]))
        self.assertEqual(saved["Category_label"], "控制櫃")

    def test_missing_supports_categories_raises(self) -> None:
        broken = load_json(resolve_path(load_app_config()["maint_tables_path"]))
        broken = copy.deepcopy(broken)
        del broken["tables"]["inventory"]["supports_categories"]
        broken_path = Path(self._tmp.name) / "broken_tables.json"
        broken_path.write_text(
            json.dumps(broken, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        config = copy.deepcopy(load_app_config())
        config["maint_tables_path"] = str(broken_path)
        config["sqlite_path"] = str(Path(self._tmp.name) / "broken.db")
        ui = UiService(sqlite_path=config["sqlite_path"], config=config)
        maint = MaintService(ui)
        with self.assertRaises(KeyError):
            maint.get_tables_config()

    def test_empty_sqlite_path_does_not_use_formal_db(self) -> None:
        with self.assertRaises(ValueError):
            UiService(sqlite_path="")
        formal = resolve_path("data/RoboArm.db").resolve()
        self.assertNotEqual(self.db_path.resolve(), formal)


if __name__ == "__main__":
    unittest.main()
