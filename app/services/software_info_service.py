"""Read-only software / environment info for System Setting (no JAKA SDK load)."""

from __future__ import annotations

import platform
import struct
import sys
from typing import Any

from app.services.ui_service import UiService
from app.storage.config_store import resolve_path


class SoftwareInfoService:
    """Collect host Python / app version info. Does not import jkrc or touch SDK."""

    def __init__(self, ui: UiService) -> None:
        self.ui = ui

    def _display(self, value: Any, empty_key: str, language: str) -> str:
        if value is None:
            return self.ui.t(empty_key, language)
        text = str(value).strip()
        if text == "":
            return self.ui.t(empty_key, language)
        return text

    def _jaka_cfg(self) -> dict[str, Any]:
        raw = self.ui.config.get("jaka")
        return raw if isinstance(raw, dict) else {}

    def build_payload(self, language: str | None = None) -> dict[str, Any]:
        lang = language if language is not None else self.ui.get_prefs()["language"]
        not_provided = "status_not_provided"
        not_configured = "status_not_configured"

        bits = struct.calcsize("P") * 8
        py_version = (
            f"{sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro}"
        )
        os_version = platform.platform()
        machine = platform.machine() or ""
        arch_bits = f"{bits}-bit"
        os_arch = (
            f"{os_version} / {machine} ({arch_bits})"
            if machine
            else f"{os_version} / {arch_bits}"
        )

        jaka = self._jaka_cfg()
        # Only treat as configured for display when formal config + recorded import verify.
        jaka_ready = bool(jaka.get("configured")) and bool(jaka.get("import_verified"))

        def row(label_key: str, value: str) -> dict[str, str]:
            return {"label": self.ui.t(label_key, lang), "value": value}

        system_rows = [
            row(
                "sw_label_app_version",
                self._display(self.ui.config.get("version"), not_provided, lang),
            ),
            row(
                "sw_label_host_python",
                self._display(
                    f"{py_version} / {bits}-bit",
                    not_provided,
                    lang,
                ),
            ),
            row("sw_label_os_arch", self._display(os_arch, not_provided, lang)),
        ]

        nc = self.ui.t(not_configured, lang)
        if jaka_ready:
            py_ver = jaka.get("python_version")
            py_bits = jaka.get("python_bits")
            jaka_py_disp = (
                f"{py_ver} / {py_bits}-bit"
                if py_ver is not None and py_bits is not None
                else self._display(py_ver, not_provided, lang)
            )
            sdk_ver = self._display(
                jaka.get("sdk_package_version"), not_provided, lang
            )
            lib_name = self._display(
                jaka.get("dynamic_library_name"), not_provided, lang
            )
            lib_ver_raw = jaka.get("dynamic_library_file_version")
            lib_ver = (
                self.ui.t(not_provided, lang)
                if lib_ver_raw is None or str(lib_ver_raw).strip() == ""
                else str(lib_ver_raw)
            )
            import_status = self.ui.t("status_jaka_import_verified", lang)
            controller_status = self.ui.t(
                "status_jaka_controller_unverified", lang
            )

            sdk_dir_cfg = str(jaka.get("sdk_dir") or "").strip()
            sdk_dir_disp = (
                str(resolve_path(sdk_dir_cfg)) if sdk_dir_cfg else nc
            )
            lib_full = (
                str(resolve_path(sdk_dir_cfg) / str(jaka.get("dynamic_library_name")))
                if sdk_dir_cfg and jaka.get("dynamic_library_name")
                else nc
            )
            mod_cfg = str(jaka.get("import_module_file") or "").strip()
            if mod_cfg:
                mod_disp = str(resolve_path(mod_cfg))
            elif sdk_dir_cfg and jaka.get("python_module_name"):
                mod_disp = str(
                    resolve_path(sdk_dir_cfg) / str(jaka.get("python_module_name"))
                )
            else:
                mod_disp = nc

            python_exe = self._display(jaka.get("python_exe"), not_provided, lang)
            env_dir = nc
            if jaka.get("python_exe"):
                try:
                    from pathlib import Path

                    env_dir = str(Path(str(jaka["python_exe"])).resolve().parent)
                except OSError:
                    env_dir = self.ui.t(not_provided, lang)

            jaka_rows = [
                row("sw_label_jaka_python", jaka_py_disp),
                row("sw_label_jaka_sdk_version", sdk_ver),
                row("sw_label_sdk_lib_name", lib_name),
                row("sw_label_sdk_lib_version", lib_ver),
                row("sw_label_jaka_import_status", import_status),
                row("sw_label_jaka_controller_status", controller_status),
            ]
            detail_jaka = {
                "python_exe": python_exe,
                "env_dir": env_dir,
                "sdk_dir": sdk_dir_disp,
                "lib_full": lib_full,
                "module": mod_disp,
            }
        else:
            jaka_rows = [
                row("sw_label_jaka_python", nc),
                row("sw_label_jaka_sdk_version", nc),
                row("sw_label_sdk_lib_name", nc),
                row("sw_label_sdk_lib_version", nc),
                row("sw_label_jaka_import_status", nc),
                row("sw_label_jaka_controller_status", nc),
            ]
            detail_jaka = {
                "python_exe": nc,
                "env_dir": nc,
                "sdk_dir": nc,
                "lib_full": nc,
                "module": nc,
            }

        detail_rows = [
            row(
                "sw_label_host_python_exe",
                self._display(sys.executable, not_provided, lang),
            ),
            row(
                "sw_label_host_env_dir",
                self._display(sys.prefix, not_provided, lang),
            ),
            row("sw_label_jaka_python_exe", detail_jaka["python_exe"]),
            row("sw_label_jaka_env_dir", detail_jaka["env_dir"]),
            row("sw_label_jaka_sdk_dir", detail_jaka["sdk_dir"]),
            row("sw_label_sdk_lib_full_path", detail_jaka["lib_full"]),
            row("sw_label_sdk_python_module", detail_jaka["module"]),
        ]

        return {
            "system": {
                "title": self.ui.t("sw_section_system", lang),
                "rows": system_rows,
            },
            "jaka": {
                "title": self.ui.t("sw_section_jaka", lang),
                "rows": jaka_rows,
                "configured": jaka_ready,
            },
            "details": {
                "title": self.ui.t("sw_section_details", lang),
                "rows": detail_rows,
                "expanded_default": False,
            },
            "labels": {
                "tab_ui_text": self.ui.t("tab_interface_text", lang),
                "tab_software": self.ui.t("tab_software_version", lang),
                "toggle_expand": self.ui.t("sw_btn_expand_details", lang),
                "toggle_collapse": self.ui.t("sw_btn_collapse_details", lang),
            },
        }
