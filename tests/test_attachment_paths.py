"""Isolated tests for attachment path settings (temp dirs only)."""

from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.attachment_paths_service import (
    STATUS_EMPTY,
    STATUS_FORMAT_ONLY,
    STATUS_INVALID,
    STATUS_NOT_DIR,
    STATUS_NOT_FOUND,
    STATUS_OK,
    STATUS_OUTSIDE_ROOT,
    AttachmentPathsService,
)
from app.services.ui_service import UiService
from app.storage.config_store import load_app_config


class AttachmentPathsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)
        self.settings_path = self.root / "attachment_paths.json"
        self.browse_roots_path = self.root / "browse_roots.json"
        self.model_root = self.root / "RoboModels"
        self.model_root.mkdir()
        (self.model_root / "Jaka").mkdir()
        (self.model_root / "Jaka" / "zu7").mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        self.outside = outside

        cfg = dict(load_app_config())
        cfg["attachment_paths_path"] = str(self.settings_path)
        cfg["browse_roots_path"] = str(self.browse_roots_path)
        cfg["sqlite_path"] = str(self.root / "ap_test.db")
        self.browse_roots_path.write_text(
            json.dumps(
                {
                    "windows": [str(self.model_root)],
                    "linux": [str(self.model_root)],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.ui = UiService(sqlite_path=str(self.root / "ap_test.db"), config=cfg)
        self.svc = AttachmentPathsService(self.ui)

    def tearDown(self) -> None:
        self.svc = None
        self.ui = None
        self._tmp.cleanup()

    def test_default_empty_and_not_overwritten_by_suggestion(self) -> None:
        data = self.svc.load_settings()
        self.assertEqual(data["model_root_windows"], "")
        self.assertEqual(data["model_root_linux"], "")
        payload = self.svc.build_payload()
        self.assertEqual(payload["suggested_windows_path"], r"C:\RoboModels")
        self.assertEqual(payload["windows_path"], "")
        self.assertEqual(payload["validation_status"], "not_checked")

    def test_os_selection_windows(self) -> None:
        with mock.patch("app.services.attachment_paths_service.platform.system", return_value="Windows"):
            self.svc.save_settings(str(self.model_root), "/opt/models")
            eff = self.svc.get_effective_path()
        self.assertEqual(eff["server_os"], "Windows")
        self.assertEqual(eff["effective_path"], str(self.model_root))

    def test_os_selection_linux(self) -> None:
        # Capture real host OS before patching the shared platform module.
        host_is_windows = os.name == "nt"
        with mock.patch(
            "app.services.attachment_paths_service.platform.system",
            return_value="Linux",
        ):
            if host_is_windows:
                linux_path = "/opt/robo_models"
                saved = self.svc._persist(str(self.model_root), linux_path)
                eff = self.svc.get_effective_path(saved)
                self.assertEqual(eff["server_os"], "Linux")
                self.assertEqual(eff["effective_path"], linux_path)
            else:
                self.svc.save_settings(r"C:\RoboModels", str(self.model_root))
                eff = self.svc.get_effective_path()
                self.assertEqual(eff["server_os"], "Linux")
                self.assertEqual(eff["effective_path"], str(self.model_root))

    def test_unsupported_os(self) -> None:
        with mock.patch("app.services.attachment_paths_service.platform.system", return_value="Darwin"):
            eff = self.svc.get_effective_path()
            self.assertFalse(eff["supported"])
            report = self.svc.validate_settings_input(str(self.model_root), "/tmp/x")
            self.assertFalse(report["can_save"])
            self.assertEqual(report["validation_status"], "unsupported_os")

    def test_no_fallback_to_other_os(self) -> None:
        self.svc._persist("", str(self.model_root) if platform.system() != "Windows" else "/opt/x")
        with mock.patch("app.services.attachment_paths_service.platform.system", return_value="Windows"):
            eff = self.svc.get_effective_path()
            self.assertEqual(eff["effective_path"], "")
            report = self.svc.validate_settings_input("", "/opt/models")
            self.assertEqual(report["current_validation"]["status"], STATUS_EMPTY)
            self.assertEqual(report["other_validation"]["status"], STATUS_FORMAT_ONLY)

    def test_validate_ok_and_persist(self) -> None:
        if platform.system() != "Windows":
            self.skipTest("Windows filesystem check")
        report = self.svc.validate_settings_input(str(self.model_root), "/opt/models")
        self.assertTrue(report["can_save"])
        self.assertEqual(report["current_validation"]["status"], STATUS_OK)
        self.assertEqual(report["linux_validation"]["status"], STATUS_FORMAT_ONLY)
        self.assertFalse(report["linux_validation"]["verified"])
        saved = self.svc.save_settings(str(self.model_root), "/opt/models")
        self.assertEqual(saved["windows_path"], str(self.model_root))
        reloaded = AttachmentPathsService(self.ui)
        self.assertEqual(reloaded.load_settings()["model_root_windows"], str(self.model_root))

    def test_validate_does_not_mutate_settings(self) -> None:
        self.svc._persist("kept-win", "kept-linux")
        before = self.svc.load_settings()
        self.svc.validate_settings_input(str(self.model_root), "/tmp/other")
        after = self.svc.reload_settings()
        self.assertEqual(after, before)

    def test_not_found_and_not_dir(self) -> None:
        if platform.system() != "Windows":
            self.skipTest("Windows filesystem check")
        missing = self.root / "missing_dir"
        report = self.svc.validate_path_text(
            str(missing), "Windows", check_filesystem=True
        )
        self.assertEqual(report["status"], STATUS_NOT_FOUND)
        file_path = self.root / "a_file.txt"
        file_path.write_text("x", encoding="utf-8")
        report2 = self.svc.validate_path_text(
            str(file_path), "Windows", check_filesystem=True
        )
        self.assertEqual(report2["status"], STATUS_NOT_DIR)

    def test_relative_and_blank(self) -> None:
        blank = self.svc.validate_path_text("", "Windows", check_filesystem=True)
        self.assertEqual(blank["status"], STATUS_EMPTY)
        rel = self.svc.validate_path_text(
            "RoboModels", "Windows", check_filesystem=False
        )
        self.assertEqual(rel["status"], STATUS_INVALID)
        spaced = self.svc.validate_path_text(
            "  C:\\path with space\\中文  ",
            "Windows",
            check_filesystem=False,
        )
        self.assertEqual(spaced["path"], r"C:\path with space\中文")
        self.assertEqual(spaced["status"], STATUS_FORMAT_ONLY)

    def test_browse_within_roots_and_block_escape(self) -> None:
        listing = self.svc.browse(str(self.model_root))
        names = {item["name"] for item in listing["directories"]}
        self.assertIn("Jaka", names)
        child = self.svc.browse(str(self.model_root / "Jaka"))
        self.assertTrue(child["can_go_up"])
        with self.assertRaises(ValueError) as ctx:
            self.svc.browse(str(self.outside))
        self.assertIn("允許", str(ctx.exception))

    def test_browse_rejects_dotdot_escape(self) -> None:
        sneaky = str(self.model_root / ".." / "outside")
        with self.assertRaises(ValueError):
            self.svc.browse(sneaky)

    def test_save_rejects_bad_current_path(self) -> None:
        if platform.system() != "Windows":
            self.skipTest("Windows filesystem check")
        with self.assertRaises(ValueError):
            self.svc.save_settings(str(self.root / "nope"), "/opt/x")


class AttachmentPathsLiveRoboModelsTests(unittest.TestCase):
    """Optional live check against C:\\RoboModels when present on this host."""

    def test_c_robomodels_readable_when_present(self) -> None:
        if platform.system() != "Windows":
            self.skipTest("Not Windows")
        target = Path(r"C:\RoboModels")
        if not target.is_dir():
            self.skipTest("C:\\RoboModels not present")
        cfg = dict(load_app_config())
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            settings = root / "attachment_paths.json"
            browse = root / "browse_roots.json"
            browse.write_text(
                json.dumps({"windows": [r"C:\RoboModels"], "linux": []}, indent=2)
                + "\n",
                encoding="utf-8",
            )
            cfg["attachment_paths_path"] = str(settings)
            cfg["browse_roots_path"] = str(browse)
            cfg["sqlite_path"] = str(root / "live.db")
            ui = UiService(sqlite_path=str(root / "live.db"), config=cfg)
            svc = AttachmentPathsService(ui)
            report = svc.validate_path_text(
                r"C:\RoboModels", "Windows", check_filesystem=True
            )
            self.assertEqual(report["status"], STATUS_OK)
            listing = svc.browse(r"C:\RoboModels")
            self.assertEqual(Path(listing["current_path"]).resolve(), target.resolve())


if __name__ == "__main__":
    unittest.main()
