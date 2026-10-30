"""Attachment path settings: 3D model library roots (Windows / Linux).

Local JSON settings + deploy browse-root whitelist. No model I/O beyond
existence/readability checks and folder listing within allowed roots.
"""

from __future__ import annotations

import os
import platform
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from app.services.ui_service import UiService
from app.storage.config_store import resolve_path
from app.storage.json_store import load_json, save_json

WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
SUGGESTED_WINDOWS_MODEL_ROOT = r"C:\RoboModels"

STATUS_OK = "ok"
STATUS_EMPTY = "empty"
STATUS_INVALID = "invalid"
STATUS_NOT_FOUND = "not_found"
STATUS_NOT_DIR = "not_dir"
STATUS_NOT_READABLE = "not_readable"
STATUS_FORMAT_ONLY = "format_ok_unverified"
STATUS_UNSUPPORTED_OS = "unsupported_os"
STATUS_NOT_CHECKED = "not_checked"
STATUS_OUTSIDE_ROOT = "outside_root"
STATUS_NO_BROWSE_ROOTS = "no_browse_roots"


class AttachmentPathsService:
    """Resolve and validate model-library roots for the RoboArm host OS."""

    def __init__(self, ui: UiService) -> None:
        self.ui = ui
        self._settings_path = resolve_path(ui.config["attachment_paths_path"])
        self._browse_roots_path = resolve_path(ui.config["browse_roots_path"])
        self._cache: dict[str, str] | None = None

    def _language(self, language: str | None) -> str:
        return language if language is not None else self.ui.get_prefs()["language"]

    def detect_server_os(self) -> str:
        system = platform.system()
        if system == "Windows":
            return "Windows"
        if system == "Linux":
            return "Linux"
        return "Unsupported"

    def _empty_settings(self) -> dict[str, str]:
        return {"model_root_windows": "", "model_root_linux": ""}

    def load_settings(self) -> dict[str, str]:
        if self._cache is not None:
            return dict(self._cache)
        if not self._settings_path.is_file():
            self._cache = self._empty_settings()
            return dict(self._cache)
        raw = load_json(self._settings_path)
        if not isinstance(raw, dict):
            self._cache = self._empty_settings()
            return dict(self._cache)
        windows = str(raw.get("model_root_windows") or "").strip()
        linux = str(raw.get("model_root_linux") or "").strip()
        self._cache = {
            "model_root_windows": windows,
            "model_root_linux": linux,
        }
        return dict(self._cache)

    def reload_settings(self) -> dict[str, str]:
        self._cache = None
        return self.load_settings()

    def _persist(self, windows: str, linux: str) -> dict[str, str]:
        payload = {
            "model_root_windows": windows,
            "model_root_linux": linux,
        }
        save_json(self._settings_path, payload)
        self._cache = dict(payload)
        return dict(payload)

    def load_browse_roots(self) -> dict[str, list[str]]:
        if not self._browse_roots_path.is_file():
            return {"windows": [], "linux": []}
        raw = load_json(self._browse_roots_path)
        if not isinstance(raw, dict):
            return {"windows": [], "linux": []}
        windows = raw.get("windows") if isinstance(raw.get("windows"), list) else []
        linux = raw.get("linux") if isinstance(raw.get("linux"), list) else []
        return {
            "windows": [str(item).strip() for item in windows if str(item).strip()],
            "linux": [str(item).strip() for item in linux if str(item).strip()],
        }

    def current_os_field(self) -> str | None:
        server_os = self.detect_server_os()
        if server_os == "Windows":
            return "model_root_windows"
        if server_os == "Linux":
            return "model_root_linux"
        return None

    def get_effective_path(self, settings: dict[str, str] | None = None) -> dict[str, Any]:
        """Shared entry for resolving the active model-library root."""
        data = settings if settings is not None else self.load_settings()
        server_os = self.detect_server_os()
        if server_os == "Windows":
            path = str(data.get("model_root_windows") or "").strip()
            return {
                "server_os": server_os,
                "supported": True,
                "field": "model_root_windows",
                "effective_path": path,
            }
        if server_os == "Linux":
            path = str(data.get("model_root_linux") or "").strip()
            return {
                "server_os": server_os,
                "supported": True,
                "field": "model_root_linux",
                "effective_path": path,
            }
        return {
            "server_os": server_os,
            "supported": False,
            "field": None,
            "effective_path": "",
        }

    def _normalize_input(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _is_absolute_for_os(self, path_text: str, target_os: str) -> bool:
        if target_os == "Windows":
            if WINDOWS_DRIVE_RE.match(path_text):
                return PureWindowsPath(path_text).is_absolute()
            # UNC paths
            if path_text.startswith("\\\\") or path_text.startswith("//"):
                return PureWindowsPath(path_text).is_absolute()
            return False
        if target_os == "Linux":
            return PurePosixPath(path_text).is_absolute() and path_text.startswith("/")
        return False

    def _status_message(self, status: str, language: str, detail: str | None = None) -> str:
        key_map = {
            STATUS_OK: "ap_status_ok",
            STATUS_EMPTY: "ap_status_empty",
            STATUS_INVALID: "ap_status_invalid",
            STATUS_NOT_FOUND: "ap_status_not_found",
            STATUS_NOT_DIR: "ap_status_not_dir",
            STATUS_NOT_READABLE: "ap_status_not_readable",
            STATUS_FORMAT_ONLY: "ap_status_format_only",
            STATUS_UNSUPPORTED_OS: "ap_status_unsupported_os",
            STATUS_NOT_CHECKED: "ap_status_not_checked",
            STATUS_OUTSIDE_ROOT: "ap_status_outside_root",
            STATUS_NO_BROWSE_ROOTS: "ap_status_no_browse_roots",
        }
        key = key_map.get(status, "ap_status_invalid")
        try:
            text = self.ui.t(key, language)
        except (KeyError, ValueError):
            text = status
        if detail:
            return f"{text}: {detail}"
        return text

    def validate_path_text(
        self,
        path_text: str,
        target_os: str,
        *,
        check_filesystem: bool,
        language: str | None = None,
    ) -> dict[str, Any]:
        lang = self._language(language)
        cleaned = self._normalize_input(path_text)
        if cleaned == "":
            return {
                "ok": False,
                "status": STATUS_EMPTY,
                "path": "",
                "message": self._status_message(STATUS_EMPTY, lang),
                "verified": False,
            }
        if target_os not in ("Windows", "Linux"):
            return {
                "ok": False,
                "status": STATUS_UNSUPPORTED_OS,
                "path": cleaned,
                "message": self._status_message(STATUS_UNSUPPORTED_OS, lang),
                "verified": False,
            }
        if not self._is_absolute_for_os(cleaned, target_os):
            return {
                "ok": False,
                "status": STATUS_INVALID,
                "path": cleaned,
                "message": self._status_message(STATUS_INVALID, lang),
                "verified": False,
            }
        if not check_filesystem:
            return {
                "ok": True,
                "status": STATUS_FORMAT_ONLY,
                "path": cleaned,
                "message": self._status_message(STATUS_FORMAT_ONLY, lang),
                "verified": False,
            }

        path = Path(cleaned)
        try:
            if not path.exists():
                return {
                    "ok": False,
                    "status": STATUS_NOT_FOUND,
                    "path": cleaned,
                    "message": self._status_message(STATUS_NOT_FOUND, lang),
                    "verified": False,
                }
            if not path.is_dir():
                return {
                    "ok": False,
                    "status": STATUS_NOT_DIR,
                    "path": cleaned,
                    "message": self._status_message(STATUS_NOT_DIR, lang),
                    "verified": False,
                }
            # Probe actual readability for the service account.
            with os.scandir(path) as entries:
                next(entries, None)
        except PermissionError:
            return {
                "ok": False,
                "status": STATUS_NOT_READABLE,
                "path": cleaned,
                "message": self._status_message(STATUS_NOT_READABLE, lang),
                "verified": False,
            }
        except OSError as exc:
            return {
                "ok": False,
                "status": STATUS_NOT_READABLE,
                "path": cleaned,
                "message": self._status_message(
                    STATUS_NOT_READABLE, lang, detail=str(exc)
                ),
                "verified": False,
            }
        return {
            "ok": True,
            "status": STATUS_OK,
            "path": cleaned,
            "message": self._status_message(STATUS_OK, lang),
            "verified": True,
        }

    def validate_settings_input(
        self,
        windows_path: Any,
        linux_path: Any,
        *,
        language: str | None = None,
    ) -> dict[str, Any]:
        lang = self._language(language)
        server_os = self.detect_server_os()
        windows = self._normalize_input(windows_path)
        linux = self._normalize_input(linux_path)

        windows_check = self.validate_path_text(
            windows,
            "Windows",
            check_filesystem=(server_os == "Windows" and windows != ""),
            language=lang,
        )
        linux_check = self.validate_path_text(
            linux,
            "Linux",
            check_filesystem=(server_os == "Linux" and linux != ""),
            language=lang,
        )

        if server_os == "Windows":
            current = windows_check
            other = linux_check
        elif server_os == "Linux":
            current = linux_check
            other = windows_check
        else:
            current = {
                "ok": False,
                "status": STATUS_UNSUPPORTED_OS,
                "path": "",
                "message": self._status_message(STATUS_UNSUPPORTED_OS, lang),
                "verified": False,
            }
            other = {
                "ok": True,
                "status": STATUS_NOT_CHECKED,
                "path": "",
                "message": self._status_message(STATUS_NOT_CHECKED, lang),
                "verified": False,
            }

        # Empty current path is a failure for "check"; save allows empty only for non-current.
        can_save = True
        save_blockers: list[str] = []
        if server_os == "Unsupported":
            can_save = False
            save_blockers.append(current["message"])
        else:
            if server_os == "Windows" and windows != "" and not windows_check["ok"]:
                can_save = False
                save_blockers.append(windows_check["message"])
            if server_os == "Linux" and linux != "" and not linux_check["ok"]:
                can_save = False
                save_blockers.append(linux_check["message"])
            # Non-current filled path must pass format-only.
            if server_os == "Windows" and linux != "" and not linux_check["ok"]:
                can_save = False
                save_blockers.append(linux_check["message"])
            if server_os == "Linux" and windows != "" and not windows_check["ok"]:
                can_save = False
                save_blockers.append(windows_check["message"])

        effective = self.get_effective_path(
            {"model_root_windows": windows, "model_root_linux": linux}
        )
        return {
            "server_os": server_os,
            "windows_path": windows,
            "linux_path": linux,
            "effective_path": effective["effective_path"],
            "windows_validation": windows_check,
            "linux_validation": linux_check,
            "current_validation": current,
            "other_validation": other,
            "can_save": can_save,
            "validation_status": current["status"],
            "validation_message": current["message"],
            "save_blockers": save_blockers,
        }

    def save_settings(
        self,
        windows_path: Any,
        linux_path: Any,
        *,
        language: str | None = None,
    ) -> dict[str, Any]:
        report = self.validate_settings_input(
            windows_path, linux_path, language=language
        )
        if not report["can_save"]:
            blockers = report.get("save_blockers") or [report["validation_message"]]
            raise ValueError("; ".join(blockers))
        saved = self._persist(report["windows_path"], report["linux_path"])
        # Re-validate persisted current path for response status.
        after = self.validate_settings_input(
            saved["model_root_windows"],
            saved["model_root_linux"],
            language=language,
        )
        return after

    def _resolve_allowed_roots(self, server_os: str) -> list[Path]:
        roots_cfg = self.load_browse_roots()
        key = "windows" if server_os == "Windows" else "linux"
        roots: list[Path] = []
        for item in roots_cfg.get(key, []):
            try:
                roots.append(Path(item).resolve())
            except OSError:
                continue
        return roots

    def _is_under_root(self, candidate: Path, root: Path) -> bool:
        try:
            candidate.relative_to(root)
            return True
        except ValueError:
            return False

    def _find_containing_root(
        self, candidate: Path, roots: list[Path]
    ) -> Path | None:
        for root in roots:
            if candidate == root or self._is_under_root(candidate, root):
                return root
        return None

    def browse(
        self,
        path_text: str | None = None,
        *,
        language: str | None = None,
    ) -> dict[str, Any]:
        lang = self._language(language)
        server_os = self.detect_server_os()
        if server_os == "Unsupported":
            raise ValueError(self._status_message(STATUS_UNSUPPORTED_OS, lang))

        roots = self._resolve_allowed_roots(server_os)
        if not roots:
            raise ValueError(self._status_message(STATUS_NO_BROWSE_ROOTS, lang))

        requested = self._normalize_input(path_text)
        if requested == "":
            current = roots[0]
        else:
            if not self._is_absolute_for_os(requested, server_os):
                raise ValueError(self._status_message(STATUS_INVALID, lang))
            try:
                current = Path(requested).resolve()
            except OSError as exc:
                raise ValueError(
                    self._status_message(STATUS_INVALID, lang, detail=str(exc))
                ) from exc

        containing = self._find_containing_root(current, roots)
        if containing is None:
            raise ValueError(self._status_message(STATUS_OUTSIDE_ROOT, lang))

        if not current.exists() or not current.is_dir():
            raise ValueError(self._status_message(STATUS_NOT_FOUND, lang))

        try:
            children: list[dict[str, str]] = []
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                        child_path = Path(entry.path).resolve()
                        if self._find_containing_root(child_path, roots) is None:
                            continue
                        children.append(
                            {
                                "name": entry.name,
                                "path": str(child_path),
                            }
                        )
                    except OSError:
                        continue
            children.sort(key=lambda item: item["name"].lower())
        except PermissionError as exc:
            raise ValueError(self._status_message(STATUS_NOT_READABLE, lang)) from exc
        except OSError as exc:
            raise ValueError(
                self._status_message(STATUS_NOT_READABLE, lang, detail=str(exc))
            ) from exc

        parent: str | None = None
        if current != containing:
            parent_path = current.parent.resolve()
            if self._find_containing_root(parent_path, roots) is not None:
                parent = str(parent_path)

        return {
            "server_os": server_os,
            "current_path": str(current),
            "parent_path": parent,
            "roots": [str(root) for root in roots],
            "can_go_up": parent is not None,
            "directories": children,
        }

    def build_payload(self, language: str | None = None) -> dict[str, Any]:
        lang = self._language(language)
        settings = self.load_settings()
        effective = self.get_effective_path(settings)
        server_os = effective["server_os"]
        windows = settings["model_root_windows"]
        linux = settings["model_root_linux"]

        if server_os == "Unsupported":
            validation = {
                "ok": False,
                "status": STATUS_UNSUPPORTED_OS,
                "path": "",
                "message": self._status_message(STATUS_UNSUPPORTED_OS, lang),
                "verified": False,
            }
        elif effective["effective_path"] == "":
            validation = {
                "ok": False,
                "status": STATUS_NOT_CHECKED,
                "path": "",
                "message": self._status_message(STATUS_NOT_CHECKED, lang),
                "verified": False,
            }
        else:
            # Do not auto-check on load; UI starts as not checked unless asked.
            validation = {
                "ok": False,
                "status": STATUS_NOT_CHECKED,
                "path": effective["effective_path"],
                "message": self._status_message(STATUS_NOT_CHECKED, lang),
                "verified": False,
            }

        browse_roots = self.load_browse_roots()
        if server_os == "Windows":
            browse_enabled_field = "windows"
            browse_roots_active = browse_roots.get("windows") or []
        elif server_os == "Linux":
            browse_enabled_field = "linux"
            browse_roots_active = browse_roots.get("linux") or []
        else:
            browse_enabled_field = None
            browse_roots_active = []

        return {
            "server_os": server_os,
            "supported": bool(effective["supported"]),
            "selection_mode": "auto_by_server_os",
            "windows_path": windows,
            "linux_path": linux,
            "effective_path": effective["effective_path"],
            "suggested_windows_path": SUGGESTED_WINDOWS_MODEL_ROOT,
            "validation_status": validation["status"],
            "validation_message": validation["message"],
            "browse_enabled_field": browse_enabled_field,
            "browse_roots": browse_roots_active,
            "browse_available": len(browse_roots_active) > 0,
            "labels": {
                "tab_attachment_paths": self.ui.t("tab_attachment_paths", lang),
                "section_model_library": self.ui.t("ap_section_model_library", lang),
                "server_env": self.ui.t("ap_label_server_env", lang),
                "selection_mode": self.ui.t("ap_label_selection_mode", lang),
                "selection_mode_value": self.ui.t("ap_selection_auto", lang),
                "windows_path": self.ui.t("ap_label_windows_path", lang),
                "linux_path": self.ui.t("ap_label_linux_path", lang),
                "effective_path": self.ui.t("ap_label_effective_path", lang),
                "path_status": self.ui.t("ap_label_path_status", lang),
                "in_use": self.ui.t("ap_label_in_use", lang),
                "browse": self.ui.t("ap_btn_browse", lang),
                "copy": self.ui.t("ap_btn_copy", lang),
                "check": self.ui.t("ap_btn_check", lang),
                "save": self.ui.t("ap_btn_save", lang),
                "cancel": self.ui.t("ap_btn_cancel", lang),
                "select_folder": self.ui.t("ap_btn_select_folder", lang),
                "go_up": self.ui.t("ap_btn_go_up", lang),
                "hint_server_path": self.ui.t("ap_hint_server_path", lang),
                "browse_disabled": self.ui.t("ap_msg_browse_disabled", lang),
                "copy_ok": self.ui.t("ap_msg_copy_ok", lang),
                "copy_fail": self.ui.t("ap_msg_copy_fail", lang),
                "save_ok": self.ui.t("ap_msg_save_ok", lang),
                "no_browse_roots": self.ui.t("ap_status_no_browse_roots", lang),
                "os_windows": self.ui.t("ap_os_windows", lang),
                "os_linux": self.ui.t("ap_os_linux", lang),
                "os_unsupported": self.ui.t("ap_os_unsupported", lang),
                "browse_title": self.ui.t("ap_browse_title", lang),
                "browse_current": self.ui.t("ap_browse_current", lang),
                "empty_dirs": self.ui.t("ap_browse_empty", lang),
            },
        }
