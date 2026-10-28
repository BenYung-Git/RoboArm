"""Automated tests for JAKA process channel + simulation (no formal DB writes)."""

from __future__ import annotations

import gc
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.jaka.protocol import (
    ERR_CONNECT_FAIL,
    ERR_CONNECT_TIMEOUT,
    ERR_DISCONNECTED,
    ERR_EQUIPMENT_NOT_CONFIGURED,
    ERR_INVALID_RESPONSE,
    ERR_OP_NOT_ALLOWED,
    ERR_PROCESS_CRASHED,
    ERR_PYTHON_EXE_MISSING,
    ERR_SDK_LOAD_FAILED,
    ERR_TIMEOUT,
)
from app.services.equipment_connection_service import EquipmentConnectionService
from app.services.jaka_bridge_service import JakaBridgeService
from app.services.jaka_process_client import JakaProcessClient
from app.services.maint_service import MaintService
from app.services.ui_service import UiService
from app.storage.config_store import load_app_config, resolve_path


class JakaBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmp.name) / "jaka_bridge_test.db"
        formal = resolve_path("data/RoboArm.db").resolve()
        if self.db_path.resolve() == formal:
            raise RuntimeError("Refusing formal DB")
        self.ui = UiService(sqlite_path=str(self.db_path))
        # Point at formal jaka config paths but keep isolated DB.
        formal_cfg = load_app_config()
        jaka = dict(formal_cfg.get("jaka") or {})
        self.ui.config = {**self.ui.config, "jaka": jaka}
        self.maint = MaintService(self.ui)
        self.eq = EquipmentConnectionService(self.ui)
        self.bridge = JakaBridgeService(self.ui, self.eq)
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
        self.arm = self._inv("JA1", "JAKA臂", "Arm", self.arm_cat, "jaka", "S1")
        self.arm_b = self._inv("JA2", "JAKA臂B", "ArmB", self.arm_cat, "jaka", "S2")

    def tearDown(self) -> None:
        self.bridge = None
        self.eq = None
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

    def _python_exe(self) -> Path:
        cfg = self.ui.config["jaka"]
        path = Path(str(cfg["python_exe"]))
        if not path.is_file():
            self.skipTest(f"JAKA python missing: {path}")
        return path

    def _client(self, timeout_sec: float = 15.0) -> JakaProcessClient:
        return JakaProcessClient(self._python_exe(), timeout_sec=timeout_sec)

    def test_normal_json_roundtrip_sim_ok(self) -> None:
        self.eq.save_connection(
            self.arm["TxId"],
            {
                "driver_type": "jaka",
                "connection_mode": "network",
                "host_address": "192.168.1.10",
            },
        )
        result = self.bridge.run_simulate(self.arm["TxId"], "connect_ok")
        self.assertTrue(result["ok"])
        self.assertTrue(result["simulated"])
        self.assertEqual(result["op"], "sim_connect_ok")
        self.assertEqual(result["data"].get("host_address"), "192.168.1.10")
        self.assertFalse(result["data"].get("live_connected"))
        self.assertFalse(result["data"].get("controller_connection_verified"))

    def test_simulate_fail_timeout_disconnect(self) -> None:
        self.eq.save_connection(
            self.arm["TxId"],
            {
                "driver_type": "jaka",
                "connection_mode": "network",
                "host_address": "10.0.0.1",
            },
        )
        fail = self.bridge.run_simulate(self.arm["TxId"], "connect_fail")
        self.assertFalse(fail["ok"])
        self.assertTrue(fail["simulated"])
        self.assertEqual(fail["error_code"], ERR_CONNECT_FAIL)

        timeout = self.bridge.run_simulate(self.arm["TxId"], "connect_timeout")
        self.assertFalse(timeout["ok"])
        self.assertTrue(timeout["simulated"])
        self.assertEqual(timeout["error_code"], ERR_CONNECT_TIMEOUT)

        disc = self.bridge.run_simulate(self.arm["TxId"], "disconnect")
        self.assertFalse(disc["ok"])
        self.assertTrue(disc["simulated"])
        self.assertEqual(disc["error_code"], ERR_DISCONNECTED)

    def test_illegal_op_rejected(self) -> None:
        client = self._client()
        result = client.invoke("drop_table;--", {})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], ERR_OP_NOT_ALLOWED)

        bad_scenario = self.bridge.run_simulate(self.arm["TxId"], "real_login")
        self.assertFalse(bad_scenario["ok"])
        self.assertEqual(bad_scenario["error_code"], ERR_OP_NOT_ALLOWED)

    def test_invalid_response_and_process_crash(self) -> None:
        client = self._client()
        bad = client.invoke("sim_bad_stdout", {})
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["error_code"], ERR_INVALID_RESPONSE)

        crash = client.invoke("sim_crash", {})
        self.assertFalse(crash["ok"])
        self.assertEqual(crash["error_code"], ERR_PROCESS_CRASHED)

    def test_python_exe_missing(self) -> None:
        client = JakaProcessClient(
            Path(self._tmp.name) / "no_such_python.exe", timeout_sec=5
        )
        result = client.invoke("sim_connect_ok", {})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], ERR_PYTHON_EXE_MISSING)

    def test_unconfigured_equipment(self) -> None:
        result = self.bridge.run_simulate(self.arm["TxId"], "connect_ok")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], ERR_EQUIPMENT_NOT_CONFIGURED)
        self.assertTrue(result["simulated"])

    def test_shared_equipment_settings_across_combinations(self) -> None:
        self.eq.save_connection(
            self.arm["TxId"],
            {
                "driver_type": "jaka",
                "connection_mode": "network",
                "host_address": "172.16.0.9",
                "remark": "shared",
            },
        )
        h1 = self.maint.create_row(
            "product_combinations",
            {"CombinationCode": "C1", "CombinationName": "組合1"},
        )
        h2 = self.maint.create_row(
            "product_combinations",
            {"CombinationCode": "C2", "CombinationName": "組合2"},
        )
        self.maint.create_row(
            "product_combination_items",
            {"CombinationTxId": h1["TxId"], "EquipmentTxId": self.arm["TxId"]},
        )
        self.maint.create_row(
            "product_combination_items",
            {"CombinationTxId": h2["TxId"], "EquipmentTxId": self.arm["TxId"]},
        )
        a = self.bridge.get_equipment_connection_snapshot(self.arm["TxId"])
        b = self.bridge.get_equipment_connection_snapshot(self.arm["TxId"])
        self.assertTrue(a["ok"])
        self.assertEqual(a["connection"], b["connection"])
        self.assertEqual(a["connection"]["host_address"], "172.16.0.9")
        # Different physical equipment stays unconfigured.
        other = self.bridge.get_equipment_connection_snapshot(self.arm_b["TxId"])
        self.assertEqual(other["error_code"], ERR_EQUIPMENT_NOT_CONFIGURED)

    def test_simulate_does_not_pollute_formal_state(self) -> None:
        self.eq.save_connection(
            self.arm["TxId"],
            {
                "driver_type": "jaka",
                "connection_mode": "network",
                "host_address": "192.168.0.5",
            },
        )
        before = self.eq.get_connection_row(self.arm["TxId"])
        self.assertIsNotNone(before)
        formal_verified = self.ui.config["jaka"].get("controller_connection_verified")
        import_verified = self.ui.config["jaka"].get("import_verified")

        for scenario in (
            "connect_ok",
            "connect_fail",
            "connect_timeout",
            "disconnect",
        ):
            result = self.bridge.run_simulate(self.arm["TxId"], scenario)
            self.assertTrue(result["simulated"])
            self.assertFalse(result["data"].get("live_connected", False))
            self.assertFalse(
                result["data"].get("controller_connection_verified", False)
            )

        after = self.eq.get_connection_row(self.arm["TxId"])
        self.assertEqual(after["HostAddress"], before["HostAddress"])
        self.assertEqual(after["UpdatedAt"], before["UpdatedAt"])
        self.assertEqual(
            self.ui.config["jaka"].get("controller_connection_verified"),
            formal_verified,
        )
        self.assertEqual(
            self.ui.config["jaka"].get("import_verified"), import_verified
        )
        self.assertFalse(
            self.ui.config["jaka"].get("controller_connection_verified")
        )

    def test_real_process_timeout_cleanup(self) -> None:
        client = self._client(timeout_sec=0.5)
        result = client.invoke(
            "sim_connect_ok",
            {"sleep_ms": 10000},
            timeout_sec=0.5,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], ERR_TIMEOUT)

    def test_sdk_diag_failure_does_not_affect_host(self) -> None:
        # Point at empty dir so import fails; host must stay usable.
        empty = Path(self._tmp.name) / "empty_sdk"
        empty.mkdir()
        result = self.bridge.run_sdk_diag(sdk_dir_override=empty, timeout_sec=15)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], ERR_SDK_LOAD_FAILED)
        self.assertFalse(result.get("simulated"))

        # Host services still work after failed diag.
        view = self.eq.build_view(self.arm["TxId"])
        self.assertFalse(view["configured"])
        snap = self.bridge.get_equipment_connection_snapshot(self.arm["TxId"])
        self.assertEqual(snap["error_code"], ERR_EQUIPMENT_NOT_CONFIGURED)

    def test_sdk_failure_does_not_fallback_to_sim_success(self) -> None:
        empty = Path(self._tmp.name) / "empty_sdk2"
        empty.mkdir()
        diag = self.bridge.run_sdk_diag(sdk_dir_override=empty)
        self.assertFalse(diag["ok"])
        # Bridge must not rewrite diag into simulated success.
        self.assertFalse(diag.get("simulated"))
        self.assertNotEqual(diag.get("op"), "sim_connect_ok")

    def test_no_public_diag_api_route(self) -> None:
        from app.main import app

        paths = {getattr(route, "path", None) for route in app.routes}
        self.assertNotIn("/api/jaka/diag", paths)
        self.assertNotIn("/api/jaka/simulate", paths)


if __name__ == "__main__":
    unittest.main()
