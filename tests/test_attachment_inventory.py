"""Isolated tests for inventory attachment registry (never use formal DB)."""

from __future__ import annotations

import gc
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.attachment_paths_service import AttachmentPathsService
from app.services.attachment_service import AttachmentService
from app.services.maint_service import MaintService
from app.services.table_layout_service import TableLayoutService
from app.services.ui_service import UiService
from app.storage.config_store import load_app_config, resolve_path


class AttachmentInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)
        self.db_path = self.root / "attachment_test.db"
        formal = resolve_path("data/RoboArm.db").resolve()
        if self.db_path.resolve() == formal:
            raise RuntimeError("Refusing formal DB")

        self.model_root = self.root / "RoboModels"
        (self.model_root / "Jaka" / "zu7" / "web").mkdir(parents=True)
        self.glb = self.model_root / "Jaka" / "zu7" / "web" / "zu7_assembly.glb"
        self.glb.write_bytes(b"glTF" + b"\x00" * 20)
        self.pdf = self.model_root / "Jaka" / "doc.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 fixture")
        self.png = self.model_root / "sample.png"
        self.png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
        self.json_file = self.model_root / "Jaka" / "note.json"
        self.json_file.write_text('{"ok": true, "n": 1}', encoding="utf-8")
        self.txt = self.model_root / "readme.txt"
        self.txt.write_text("hello\n  indented", encoding="utf-8")
        self.bin = self.model_root / "mystery.bin"
        self.bin.write_bytes(b"\x00\x01\x02")

        settings_path = self.root / "attachment_paths.json"
        browse_roots = self.root / "browse_roots.json"
        cfg = dict(load_app_config())
        cfg["sqlite_path"] = str(self.db_path)
        cfg["attachment_paths_path"] = str(settings_path)
        cfg["browse_roots_path"] = str(browse_roots)
        browse_roots.write_text(
            json.dumps({"windows": [str(self.model_root)], "linux": [str(self.model_root)]}),
            encoding="utf-8",
        )
        self.ui = UiService(sqlite_path=str(self.db_path), config=cfg)
        self.paths = AttachmentPathsService(self.ui)
        # Persist without cross-OS format blockers (mirror attachment_paths tests).
        self.paths._persist(str(self.model_root), "/opt/robo_models")
        self.att = AttachmentService(self.ui, self.paths)
        self.maint = MaintService(self.ui, self.att)
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
        self.inv = self.maint.create_row(
            "inventory",
            {
                "ItemCode": "arm1",
                "ItemName": "測試臂",
                "ItemNameEn": "Test Arm",
                "Category": self.cat["TxId"],
                "Brand": "jaka",
                "Model": "zu7",
                "SerialNo": "s1",
                "Quantity": 1,
                "Unit": "台",
                "Location": "L",
                "dimensions": "",
                "Remark": "",
            },
        )
        self.inv2 = self.maint.create_row(
            "inventory",
            {
                "ItemCode": "arm2",
                "ItemName": "另一臂",
                "ItemNameEn": "Other Arm",
                "Category": self.cat["TxId"],
                "Brand": "jaka",
                "Model": "zu5",
                "SerialNo": "s2",
                "Quantity": 1,
                "Unit": "台",
                "Location": "L",
                "dimensions": "",
                "Remark": "",
            },
        )

    def tearDown(self) -> None:
        self.layout = None
        self.maint = None
        self.att = None
        self.paths = None
        self.ui = None
        gc.collect()
        self._tmp.cleanup()

    def test_schema_and_meta(self) -> None:
        cols = {
            row["name"]: row["type"]
            for row in self.ui.store.fetchall("PRAGMA table_info(attachment)")
        }
        for name in (
            "TxId",
            "InventoryId",
            "Path",
            "File",
            "Type",
            "Remark",
            "isDisable",
            "CreatedAt",
            "UpdatedAt",
        ):
            self.assertIn(name, cols)
        meta = self.maint.build_table_ui_meta("inventory")
        self.assertEqual(meta["detail"]["table_key"], "attachment")
        self.assertEqual(meta["detail"]["parent_field"], "InventoryId")
        self.assertEqual(meta["detail"]["presentation"], "tab")
        self.assertEqual(meta["detail"]["tab_key"], "attachments")
        self.assertIn("embedded_toolbar", meta["detail"])
        att_meta = self.maint.build_table_ui_meta("attachment")
        self.assertEqual(att_meta["table_key"], "attachment")
        self.assertTrue(any(c["field"] == "InventoryId" for c in att_meta["columns"]))
        self.assertEqual(self.ui.t("att_label_all", "zh_TW"), "所有附件")
        self.assertEqual(self.ui.t("att_label_all", "en"), "All attachments")
        self.assertEqual(self.ui.t("att_label_all", "zh_CN"), "所有附件")

    def test_create_validate_and_active_list(self) -> None:
        row = self.maint.create_row(
            "attachment",
            {
                "InventoryId": self.inv["TxId"],
                "Path": "Jaka/zu7/web",
                "File": "zu7_assembly.glb",
                "Type": "wrong",
                "Remark": "cad",
            },
        )
        self.assertEqual(row["TxId"], 1)
        self.assertEqual(row["Type"], "glb")
        self.assertFalse(row["isDisable"])
        self.assertEqual(row["Path"], "Jaka/zu7/web")
        active = self.att.list_active_for_inventory(self.inv["TxId"])
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["File"], "zu7_assembly.glb")

        with self.assertRaises(ValueError):
            self.maint.create_row(
                "attachment",
                {
                    "InventoryId": self.inv["TxId"],
                    "Path": "../outside",
                    "File": "x.glb",
                    "Remark": "",
                },
            )

        same_file_other = self.maint.create_row(
            "attachment",
            {
                "InventoryId": self.inv2["TxId"],
                "Path": "Jaka/zu7/web",
                "File": "zu7_assembly.glb",
                "Remark": "shared ref",
            },
        )
        self.assertEqual(same_file_other["InventoryId"], self.inv2["TxId"])
        self.assertEqual(
            len(self.att.list_active_for_inventory(self.inv["TxId"])), 1
        )
        self.assertEqual(
            len(self.att.list_active_for_inventory(self.inv2["TxId"])), 1
        )

    def test_disable_blocks_content_api(self) -> None:
        row = self.maint.create_row(
            "attachment",
            {
                "InventoryId": self.inv["TxId"],
                "Path": "",
                "File": "sample.png",
                "Remark": "",
            },
        )
        self.assertEqual(row["Type"], "png")
        self.maint.toggle_disable("attachment", row["TxId"])
        active = self.att.list_active_for_inventory(self.inv["TxId"])
        self.assertEqual(active, [])
        with self.assertRaises(PermissionError):
            self.att.resolve_content_path(self.inv["TxId"], row["TxId"])
        # Record still exists; file untouched.
        still = self.maint.get_row("attachment", row["TxId"])
        self.assertTrue(still["isDisable"])
        self.assertTrue(self.png.is_file())

    def test_wrong_inventory_rejected(self) -> None:
        row = self.maint.create_row(
            "attachment",
            {
                "InventoryId": self.inv["TxId"],
                "Path": "Jaka",
                "File": "doc.pdf",
                "Remark": "",
            },
        )
        with self.assertRaises(KeyError):
            self.att.get_row_for_inventory(self.inv2["TxId"], row["TxId"])

    def test_browse_files_and_types(self) -> None:
        with mock.patch(
            "app.services.attachment_paths_service.platform.system",
            return_value="Windows",
        ):
            payload = self.att.browse_files("")
        names = {item["name"] for item in payload["files"]}
        self.assertIn("sample.png", names)
        self.assertIn("readme.txt", names)
        jaka = self.att.browse_files("Jaka")
        self.assertTrue(any(d["name"] == "zu7" for d in jaka["directories"]))
        self.assertTrue(any(f["File"] == "doc.pdf" for f in jaka["files"]))

        text = self.maint.create_row(
            "attachment",
            {
                "InventoryId": self.inv["TxId"],
                "Path": "",
                "File": "readme.txt",
                "Remark": "",
            },
        )
        preview = self.att.read_text_preview(self.inv["TxId"], text["TxId"])
        self.assertIn("indented", preview["text"])

        js = self.maint.create_row(
            "attachment",
            {
                "InventoryId": self.inv["TxId"],
                "Path": "Jaka",
                "File": "note.json",
                "Remark": "",
            },
        )
        jp = self.att.read_text_preview(self.inv["TxId"], js["TxId"])
        self.assertIsNone(jp["json_error"])
        self.assertIn('"ok"', jp["text"])

        other = self.maint.create_row(
            "attachment",
            {
                "InventoryId": self.inv["TxId"],
                "Path": "",
                "File": "mystery.bin",
                "Remark": "",
            },
        )
        meta = self.att.build_preview_meta(self.inv["TxId"], other["TxId"])
        self.assertFalse(meta["preview_supported"])
        self.assertEqual(meta["viewer"], "download_only")

    def test_layout_defaults(self) -> None:
        layout = self.layout.ensure_table_layout("attachment")
        visible = [c for c in layout["columns"] if c["visible"] and not c.get("is_system")]
        self.assertLessEqual(len(visible), 6)
        self.assertTrue(any(c["field_key"] == "TxId" for c in visible))

    def test_inventory_untouched(self) -> None:
        before = self.maint.get_row("inventory", self.inv["TxId"])
        self.maint.create_row(
            "attachment",
            {
                "InventoryId": self.inv["TxId"],
                "Path": "",
                "File": "sample.png",
                "Remark": "x",
            },
        )
        after = self.maint.get_row("inventory", self.inv["TxId"])
        self.assertEqual(before["ItemCode"], after["ItemCode"])
        self.assertEqual(before["Remark"], after["Remark"])


if __name__ == "__main__":
    unittest.main()
