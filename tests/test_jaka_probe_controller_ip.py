"""Tests for get_controller_ip probe tooling (mock/sim only — no real SDK search)."""

from __future__ import annotations

import gc
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.jaka import worker as jaka_worker
from app.jaka.probe_observe import observe_value
from app.jaka.protocol import (
    ERR_PROBE_TYPE_ERROR,
    PROBE_GET_CONTROLLER_IP_TIMEOUT_SEC,
)
from app.services.equipment_connection_service import EquipmentConnectionService
from app.services.jaka_bridge_service import JakaBridgeService
from app.services.jaka_process_client import JakaProcessClient
from app.services.ui_service import UiService
from app.storage.config_store import load_app_config, resolve_path
from tools import jaka_probe_controller_ip as probe_cli


class ObserveValueTests(unittest.TestCase):
    def test_tuple_elements_recorded_without_interpreting(self) -> None:
        obs = observe_value((0, ["10.0.0.1"]))
        self.assertTrue(obs["is_tuple"])
        self.assertEqual(obs["tuple_len"], 2)
        self.assertEqual(obs["elements"][0]["type_name"], "int")
        self.assertEqual(obs["elements"][1]["type_name"], "list")
        self.assertIn("10.0.0.1", obs["elements"][1]["repr"])

    def test_string_not_assumed_delimiter(self) -> None:
        obs = observe_value((0, "10.0.0.1,10.0.0.2"))
        self.assertEqual(obs["elements"][1]["type_name"], "str")
        self.assertEqual(obs["elements"][1]["repr"], repr("10.0.0.1,10.0.0.2"))

    def test_nonzero_not_labeled_empty(self) -> None:
        obs = observe_value((-3, None))
        self.assertEqual(obs["elements"][0]["repr"], "-3")
        self.assertNotIn("no_devices", obs)


class ProbeHandlerMockTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.sdk_dir = Path(self._tmp.name) / "sdk"
        self.sdk_dir.mkdir()

    def tearDown(self) -> None:
        # Drop fake jkrc if installed.
        sys.modules.pop("jkrc", None)
        self._tmp.cleanup()

    def _install_fake_jkrc(self, fn) -> None:
        mod = ModuleType("jkrc")
        mod.get_controller_ip = fn  # type: ignore[attr-defined]
        mod.__file__ = str(self.sdk_dir / "jkrc.pyd")
        sys.modules["jkrc"] = mod

    def test_no_arg_success_records_observation(self) -> None:
        def fake() -> tuple:
            return (0, ["192.0.2.1"])

        self._install_fake_jkrc(fake)
        result = jaka_worker.handle_probe_get_controller_ip(
            "rid", {"sdk_dir": str(self.sdk_dir)}
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["op"], "probe_get_controller_ip")
        self.assertFalse(result["simulated"])
        data = result["data"]
        self.assertEqual(data["call"], "jkrc.get_controller_ip()")
        self.assertEqual(data["call_args"], [])
        self.assertFalse(data["rc_constructed"])
        self.assertFalse(data["login_called"])
        self.assertFalse(data["retried_with_other_signature"])
        self.assertTrue(data["return_observed"])
        self.assertIn("elapsed_ms", data)
        self.assertEqual(data["return_value"]["tuple_len"], 2)

    def test_type_error_stops_without_retry(self) -> None:
        calls = {"n": 0}

        def fake(*args, **kwargs):
            calls["n"] += 1
            raise TypeError("missing required positional argument")

        self._install_fake_jkrc(fake)
        result = jaka_worker.handle_probe_get_controller_ip(
            "rid", {"sdk_dir": str(self.sdk_dir)}
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], ERR_PROBE_TYPE_ERROR)
        self.assertEqual(calls["n"], 1)
        self.assertFalse(result["data"]["retried_with_other_signature"])
        self.assertEqual(result["data"]["exception_type"], "TypeError")
        self.assertFalse(result["data"]["return_observed"])

    def test_nonzero_errcode_not_converted_to_no_devices(self) -> None:
        self._install_fake_jkrc(lambda: (-3, "x"))
        result = jaka_worker.handle_probe_get_controller_ip(
            "rid", {"sdk_dir": str(self.sdk_dir)}
        )
        self.assertTrue(result["ok"])
        self.assertNotIn("no_devices", str(result))
        self.assertNotEqual(result.get("message", "").lower(), "no devices")
        self.assertTrue(result["data"]["return_observed"])


class ProbeCliAndSimTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmp.name) / "probe_test.db"
        formal = resolve_path("data/RoboArm.db").resolve()
        if self.db_path.resolve() == formal:
            raise RuntimeError("Refusing formal DB")
        self.ui = UiService(sqlite_path=str(self.db_path))
        jaka = dict(load_app_config().get("jaka") or {})
        self.ui.config = {**self.ui.config, "jaka": jaka}
        self.bridge = JakaBridgeService(self.ui, EquipmentConnectionService(self.ui))

    def tearDown(self) -> None:
        self.bridge = None
        self.ui = None
        gc.collect()
        self._tmp.cleanup()

    def _python_exe(self) -> Path:
        path = Path(str(self.ui.config["jaka"]["python_exe"]))
        if not path.is_file():
            self.skipTest(f"JAKA python missing: {path}")
        return path

    def test_default_timeout_constant(self) -> None:
        self.assertEqual(PROBE_GET_CONTROLLER_IP_TIMEOUT_SEC, 30.0)

    def test_cli_default_does_not_search(self) -> None:
        with mock.patch.object(probe_cli, "UiService") as ui_cls:
            code = probe_cli.main([])
            self.assertEqual(code, 0)
            ui_cls.assert_not_called()

    def test_cli_refuses_sim_with_run_search(self) -> None:
        code = probe_cli.main(["--sim", "ok", "--run-search"])
        self.assertEqual(code, 2)

    def test_sim_probe_ok_via_subprocess(self) -> None:
        # Use host/JAKA python only to run worker sim op — no jkrc search.
        client = JakaProcessClient(self._python_exe(), timeout_sec=15)
        # Override bridge client
        self.bridge._client_override = client
        result = self.bridge.run_sim_probe_get_controller_ip("ok")
        self.assertTrue(result["ok"])
        self.assertTrue(result["simulated"])
        self.assertTrue(result["data"]["return_observed"])
        self.assertEqual(result["data"]["call_args"], [])

    def test_sim_probe_type_error_via_subprocess(self) -> None:
        client = JakaProcessClient(self._python_exe(), timeout_sec=15)
        self.bridge._client_override = client
        result = self.bridge.run_sim_probe_get_controller_ip("type_error")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], ERR_PROBE_TYPE_ERROR)
        self.assertFalse(result["data"]["return_observed"])

    def test_sim_probe_nonzero_not_no_devices(self) -> None:
        client = JakaProcessClient(self._python_exe(), timeout_sec=15)
        self.bridge._client_override = client
        result = self.bridge.run_sim_probe_get_controller_ip("nonzero")
        self.assertTrue(result["ok"])
        self.assertTrue(result["simulated"])
        self.assertFalse(result["data"].get("interpreted_as_no_devices", True))
        self.assertEqual(result["data"]["return_value"]["elements"][0]["repr"], "-3")

    def test_run_search_path_uses_probe_op_only(self) -> None:
        fake_client = mock.Mock()
        fake_client.invoke.return_value = {
            "ok": True,
            "op": "probe_get_controller_ip",
            "simulated": False,
            "data": {"call_args": []},
        }
        self.bridge._client_override = fake_client
        # Use empty override dir that exists so resolve succeeds without real SDK call.
        empty = Path(self._tmp.name) / "empty_sdk"
        empty.mkdir()
        result = self.bridge.run_probe_get_controller_ip(sdk_dir_override=empty)
        self.assertTrue(result["ok"])
        fake_client.invoke.assert_called_once()
        args, kwargs = fake_client.invoke.call_args
        self.assertEqual(args[0], "probe_get_controller_ip")
        self.assertEqual(args[1].get("sdk_dir"), str(empty))

    def test_no_public_probe_api(self) -> None:
        from app.main import app

        paths = {getattr(route, "path", None) for route in app.routes}
        self.assertNotIn("/api/jaka/probe", paths)
        self.assertNotIn("/api/jaka/search", paths)


if __name__ == "__main__":
    unittest.main()
