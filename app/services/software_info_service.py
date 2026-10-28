"""Read-only software / environment info for System Setting (no JAKA SDK load)."""

from __future__ import annotations

import platform
import struct
import sys
from typing import Any

from app.services.ui_service import UiService


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

        # Formal JAKA runtime is not configured in this project yet.
        # Do not treat test-folder SDK filenames as confirmed formal metadata.
        jaka_configured = False

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
        jaka_rows = [
            row("sw_label_jaka_python", nc),
            row("sw_label_jaka_sdk_version", nc),
            row("sw_label_sdk_lib_name", nc),
            row("sw_label_sdk_lib_version", nc),
        ]

        detail_rows = [
            row(
                "sw_label_host_python_exe",
                self._display(sys.executable, not_provided, lang),
            ),
            row(
                "sw_label_host_env_dir",
                self._display(sys.prefix, not_provided, lang),
            ),
            row("sw_label_jaka_python_exe", nc),
            row("sw_label_jaka_env_dir", nc),
            row("sw_label_jaka_sdk_dir", nc),
            row("sw_label_sdk_lib_full_path", nc),
            row("sw_label_sdk_python_module", nc),
        ]

        return {
            "system": {
                "title": self.ui.t("sw_section_system", lang),
                "rows": system_rows,
            },
            "jaka": {
                "title": self.ui.t("sw_section_jaka", lang),
                "rows": jaka_rows,
                "configured": jaka_configured,
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
