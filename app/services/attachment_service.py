"""Inventory attachment registry: relative paths under the model library root.

Registers existing files only (no upload/copy/move). Content is served only for
rows that belong to the given inventory and are not disabled.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any

from app.services.attachment_paths_service import AttachmentPathsService
from app.services.ui_service import UiService

PREVIEWABLE_TYPES = frozenset(
    {"pdf", "jpg", "jpeg", "png", "glb", "json", "txt", "md", "yaml", "yml"}
)
TEXT_TYPES = frozenset({"json", "txt", "md", "yaml", "yml"})
IMAGE_TYPES = frozenset({"jpg", "jpeg", "png"})
MAX_TEXT_PREVIEW_BYTES = 512 * 1024

_UNSAFE_FILENAME = re.compile(r'[\x00-\x1f<>:"/\\|?*]')


class AttachmentService:
    def __init__(
        self,
        ui: UiService,
        paths: AttachmentPathsService | None = None,
    ) -> None:
        self.ui = ui
        self.store = ui.store
        self.paths = paths if paths is not None else AttachmentPathsService(ui)

    def _language(self, language: str | None = None) -> str:
        if language is not None:
            return language
        return self.ui.get_prefs()["language"]

    def _msg(self, key: str, language: str | None = None) -> str:
        return self.ui.t(key, self._language(language))

    def model_root(self) -> Path:
        info = self.paths.get_effective_path()
        if not info.get("supported"):
            raise ValueError(self._msg("att_err_root_os_unsupported"))
        root_text = str(info.get("effective_path") or "").strip()
        if root_text == "":
            raise ValueError(self._msg("att_err_root_not_set"))
        root = Path(root_text)
        if not root.is_absolute():
            raise ValueError(self._msg("att_err_root_not_absolute"))
        if not root.exists() or not root.is_dir():
            raise ValueError(self._msg("att_err_root_missing"))
        try:
            return root.resolve()
        except OSError as exc:
            raise ValueError(self._msg("att_err_root_unreadable")) from exc

    @staticmethod
    def normalize_rel_dir(path_text: str | None) -> str:
        raw = "" if path_text is None else str(path_text).strip()
        if raw == "" or raw == ".":
            return ""
        raw = raw.replace("\\", "/")
        while "//" in raw:
            raw = raw.replace("//", "/")
        raw = raw.strip("/")
        parts = PurePosixPath(raw).parts
        if any(part in ("", ".", "..") for part in parts):
            raise ValueError("att_err_path_invalid")
        if PurePosixPath(raw).is_absolute():
            raise ValueError("att_err_path_invalid")
        return "/".join(parts)

    @staticmethod
    def normalize_file_name(file_name: str | None) -> str:
        name = "" if file_name is None else str(file_name).strip()
        if name == "" or "/" in name or "\\" in name or name in (".", ".."):
            raise ValueError("att_err_file_invalid")
        if _UNSAFE_FILENAME.search(name):
            raise ValueError("att_err_file_invalid")
        return name

    @staticmethod
    def type_from_filename(file_name: str) -> str:
        suffix = Path(file_name).suffix.lower().lstrip(".")
        return suffix

    def resolve_under_root(self, rel_dir: str, file_name: str) -> Path:
        root = self.model_root()
        try:
            norm_dir = self.normalize_rel_dir(rel_dir)
            norm_file = self.normalize_file_name(file_name)
        except ValueError as exc:
            code = str(exc)
            raise ValueError(self._msg(code if code.startswith("att_") else "att_err_path_invalid")) from exc
        relative = PurePosixPath(norm_dir) / norm_file if norm_dir else PurePosixPath(norm_file)
        candidate = (root / Path(*relative.parts)).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(self._msg("att_err_path_outside_root")) from exc
        return candidate

    def validate_existing_file(self, rel_dir: str, file_name: str) -> dict[str, str]:
        try:
            norm_dir = self.normalize_rel_dir(rel_dir)
            norm_file = self.normalize_file_name(file_name)
        except ValueError as exc:
            code = str(exc)
            raise ValueError(
                self._msg(code if code.startswith("att_") else "att_err_path_invalid")
            ) from exc
        path = self.resolve_under_root(norm_dir, norm_file)
        if not path.exists() or not path.is_file():
            raise ValueError(self._msg("att_err_file_missing"))
        if not os.access(path, os.R_OK):
            raise ValueError(self._msg("att_err_file_unreadable"))
        return {
            "Path": norm_dir,
            "File": norm_file,
            "Type": self.type_from_filename(norm_file),
        }

    def prepare_writable_fields(self, values: dict[str, Any]) -> dict[str, Any]:
        """Normalize Path/File/Type from an existing on-disk file under the root."""
        prepared = self.validate_existing_file(
            values.get("Path"),
            values.get("File"),
        )
        out = dict(values)
        out["Path"] = prepared["Path"]
        out["File"] = prepared["File"]
        out["Type"] = prepared["Type"]
        return out

    def assert_inventory_exists(self, inventory_id: int) -> None:
        row = self.store.fetchone(
            "SELECT TxId FROM inventory WHERE TxId = ?",
            (inventory_id,),
        )
        if row is None:
            raise KeyError(self._msg("att_err_inventory_not_found"))

    def get_row_for_inventory(
        self, inventory_id: int, txid: int, *, allow_disabled: bool = False
    ) -> dict[str, Any]:
        self.assert_inventory_exists(inventory_id)
        row = self.store.fetchone(
            """
            SELECT TxId, InventoryId, Path, File, Type, Remark, isDisable,
                   CreatedAt, UpdatedAt
            FROM attachment
            WHERE TxId = ? AND InventoryId = ?
            """,
            (txid, inventory_id),
        )
        if row is None:
            raise KeyError(self._msg("att_err_not_found"))
        item = dict(row)
        if not allow_disabled and int(item.get("isDisable") or 0):
            raise PermissionError(self._msg("att_err_disabled"))
        return item

    def list_active_for_inventory(self, inventory_id: int) -> list[dict[str, Any]]:
        self.assert_inventory_exists(inventory_id)
        rows = self.store.fetchall(
            """
            SELECT TxId, InventoryId, Path, File, Type, Remark, isDisable
            FROM attachment
            WHERE InventoryId = ? AND isDisable = 0
            ORDER BY TxId DESC
            """,
            (inventory_id,),
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            file_name = str(item.get("File") or "")
            rel_path = str(item.get("Path") or "")
            label = file_name
            # Same filename may appear under different folders.
            duplicates = [
                r
                for r in rows
                if str(r["File"]) == file_name and int(r["TxId"]) != int(item["TxId"])
            ]
            if duplicates and rel_path:
                label = f"{file_name} ({rel_path})"
            elif duplicates:
                label = f"{file_name} (/)"
            type_name = str(item.get("Type") or "").lower()
            result.append(
                {
                    "TxId": int(item["TxId"]),
                    "File": file_name,
                    "Path": rel_path,
                    "Type": type_name,
                    "label": label,
                    "preview_supported": type_name in PREVIEWABLE_TYPES,
                }
            )
        return result

    def browse_files(
        self, relative_dir: str | None = None, *, language: str | None = None
    ) -> dict[str, Any]:
        lang = self._language(language)
        root = self.model_root()
        try:
            current_rel = self.normalize_rel_dir(relative_dir)
        except ValueError as exc:
            raise ValueError(self._msg("att_err_path_invalid", lang)) from exc

        current = root if current_rel == "" else (root / Path(*PurePosixPath(current_rel).parts))
        try:
            current = current.resolve()
        except OSError as exc:
            raise ValueError(self._msg("att_err_path_invalid", lang)) from exc
        try:
            current.relative_to(root)
        except ValueError as exc:
            raise ValueError(self._msg("att_err_path_outside_root", lang)) from exc
        if not current.exists() or not current.is_dir():
            raise ValueError(self._msg("att_err_dir_missing", lang))

        directories: list[dict[str, str]] = []
        files: list[dict[str, str]] = []
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        child = Path(entry.path).resolve()
                        try:
                            child.relative_to(root)
                        except ValueError:
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            child_rel = (
                                f"{current_rel}/{entry.name}"
                                if current_rel
                                else entry.name
                            )
                            directories.append({"name": entry.name, "rel": child_rel})
                        elif entry.is_file(follow_symlinks=False):
                            type_name = self.type_from_filename(entry.name)
                            files.append(
                                {
                                    "name": entry.name,
                                    "Path": current_rel,
                                    "File": entry.name,
                                    "Type": type_name,
                                    "preview_supported": (
                                        "1" if type_name in PREVIEWABLE_TYPES else "0"
                                    ),
                                }
                            )
                    except OSError:
                        continue
        except PermissionError as exc:
            raise ValueError(self._msg("att_err_dir_unreadable", lang)) from exc
        except OSError as exc:
            raise ValueError(self._msg("att_err_dir_unreadable", lang)) from exc

        directories.sort(key=lambda item: item["name"].lower())
        files.sort(key=lambda item: item["name"].lower())

        parent_rel: str | None = None
        if current_rel:
            parent = str(PurePosixPath(current_rel).parent)
            parent_rel = "" if parent == "." else parent.replace("\\", "/")

        return {
            "root_set": True,
            "current_rel": current_rel,
            "parent_rel": parent_rel,
            "can_go_up": current_rel != "",
            "directories": directories,
            "files": files,
            "labels": {
                "title": self._msg("att_browse_title", lang),
                "current": self._msg("att_browse_current", lang),
                "up": self._msg("att_browse_up", lang),
                "empty_dirs": self._msg("att_browse_empty_dirs", lang),
                "empty_files": self._msg("att_browse_empty_files", lang),
                "select": self._msg("att_browse_select", lang),
                "cancel": self._msg("att_btn_cancel", lang),
                "folders": self._msg("att_browse_folders", lang),
                "files": self._msg("att_browse_files", lang),
            },
        }

    def content_type_for(self, file_name: str, type_name: str) -> str:
        guessed, _ = mimetypes.guess_type(file_name)
        if type_name == "glb":
            return "model/gltf-binary"
        if type_name == "pdf":
            return "application/pdf"
        if type_name in IMAGE_TYPES and guessed:
            return guessed
        if type_name in TEXT_TYPES:
            if type_name == "json":
                return "application/json; charset=utf-8"
            if type_name in ("yaml", "yml"):
                return "text/yaml; charset=utf-8"
            if type_name == "md":
                return "text/markdown; charset=utf-8"
            return "text/plain; charset=utf-8"
        if guessed and guessed != "text/html":
            return guessed
        return "application/octet-stream"

    def safe_download_name(self, file_name: str) -> str:
        cleaned = _UNSAFE_FILENAME.sub("_", file_name).strip() or "download.bin"
        return cleaned[:180]

    def build_preview_meta(
        self, inventory_id: int, txid: int, *, language: str | None = None
    ) -> dict[str, Any]:
        lang = self._language(language)
        row = self.get_row_for_inventory(inventory_id, txid, allow_disabled=False)
        type_name = str(row.get("Type") or "").lower()
        file_name = str(row.get("File") or "")
        rel_dir = str(row.get("Path") or "")
        preview_supported = type_name in PREVIEWABLE_TYPES
        meta: dict[str, Any] = {
            "TxId": int(row["TxId"]),
            "InventoryId": int(row["InventoryId"]),
            "Path": rel_dir,
            "File": file_name,
            "Type": type_name,
            "preview_supported": preview_supported,
            "content_url": (
                f"/api/inventory/{inventory_id}/attachments/{txid}/content"
            ),
            "download_url": (
                f"/api/inventory/{inventory_id}/attachments/{txid}/content"
                "?disposition=attachment"
            ),
            "labels": {
                "loading": self._msg("att_preview_loading", lang),
                "unsupported": self._msg("att_preview_unsupported", lang),
                "missing": self._msg("att_err_file_missing", lang),
                "unreadable": self._msg("att_err_file_unreadable", lang),
                "failed": self._msg("att_preview_failed", lang),
                "download": self._msg("att_btn_download", lang),
                "text_truncated": self._msg("att_preview_text_truncated", lang),
                "json_invalid": self._msg("att_preview_json_invalid", lang),
                "static_disclaimer": self._msg("att_glb_static_disclaimer", lang),
                "fit": self._msg("cad_btn_fit", lang),
                "reset": self._msg("cad_btn_reset", lang),
                "grid": self._msg("cad_label_grid", lang),
                "axes": self._msg("cad_label_axes", lang),
                "size": self._msg("cad_label_size", lang),
                "load_failed": self._msg("att_preview_failed", lang),
            },
        }
        try:
            path = self.resolve_under_root(rel_dir, file_name)
            if not path.is_file():
                meta["file_status"] = "missing"
                meta["message"] = self._msg("att_err_file_missing", lang)
                return meta
            if not os.access(path, os.R_OK):
                meta["file_status"] = "unreadable"
                meta["message"] = self._msg("att_err_file_unreadable", lang)
                return meta
            meta["file_status"] = "ok"
            meta["size_bytes"] = path.stat().st_size
        except ValueError as exc:
            meta["file_status"] = "error"
            meta["message"] = str(exc)
            return meta

        if not preview_supported:
            meta["viewer"] = "download_only"
            meta["message"] = self._msg("att_preview_unsupported", lang)
            return meta

        if type_name == "pdf":
            meta["viewer"] = "pdf"
        elif type_name in IMAGE_TYPES:
            meta["viewer"] = "image"
        elif type_name == "glb":
            meta["viewer"] = "glb"
            meta["cad_static"] = {
                "available": True,
                "glb_url": meta["content_url"],
                "model_key": "",
                "parts": [],
                "aabb_m": None,
                "disclaimer": self._msg("att_glb_static_disclaimer", lang),
                "labels": {
                    "fit": meta["labels"]["fit"],
                    "reset": meta["labels"]["reset"],
                    "grid": meta["labels"]["grid"],
                    "axes": meta["labels"]["axes"],
                    "size": meta["labels"]["size"],
                    "loading": meta["labels"]["loading"],
                    "load_failed": meta["labels"]["load_failed"],
                    "parts": "",
                    "unavailable": meta["labels"]["failed"],
                },
            }
        elif type_name in TEXT_TYPES:
            meta["viewer"] = "text"
            meta["text_format"] = type_name
            meta["max_bytes"] = MAX_TEXT_PREVIEW_BYTES
        else:
            meta["viewer"] = "download_only"
            meta["message"] = self._msg("att_preview_unsupported", lang)
        return meta

    def read_text_preview(
        self, inventory_id: int, txid: int, *, language: str | None = None
    ) -> dict[str, Any]:
        lang = self._language(language)
        row = self.get_row_for_inventory(inventory_id, txid, allow_disabled=False)
        type_name = str(row.get("Type") or "").lower()
        if type_name not in TEXT_TYPES:
            raise ValueError(self._msg("att_preview_unsupported", lang))
        path = self.resolve_under_root(str(row.get("Path") or ""), str(row.get("File") or ""))
        if not path.is_file():
            raise FileNotFoundError(self._msg("att_err_file_missing", lang))
        if not os.access(path, os.R_OK):
            raise PermissionError(self._msg("att_err_file_unreadable", lang))
        size = path.stat().st_size
        truncated = size > MAX_TEXT_PREVIEW_BYTES
        raw = path.read_bytes()[:MAX_TEXT_PREVIEW_BYTES]
        text = raw.decode("utf-8", errors="replace")
        formatted = text
        json_error = None
        if type_name == "json":
            try:
                formatted = json.dumps(
                    json.loads(text), ensure_ascii=False, indent=2
                )
            except json.JSONDecodeError as exc:
                json_error = self._msg("att_preview_json_invalid", lang)
                formatted = text
                # keep original; surface hint
                _ = exc
        return {
            "TxId": txid,
            "Type": type_name,
            "text": formatted,
            "truncated": truncated,
            "size_bytes": size,
            "max_bytes": MAX_TEXT_PREVIEW_BYTES,
            "json_error": json_error,
            "message": (
                self._msg("att_preview_text_truncated", lang) if truncated else ""
            ),
        }

    def resolve_content_path(
        self, inventory_id: int, txid: int
    ) -> tuple[Path, dict[str, Any]]:
        row = self.get_row_for_inventory(inventory_id, txid, allow_disabled=False)
        path = self.resolve_under_root(str(row.get("Path") or ""), str(row.get("File") or ""))
        if not path.is_file():
            raise FileNotFoundError(self._msg("att_err_file_missing"))
        if not os.access(path, os.R_OK):
            raise PermissionError(self._msg("att_err_file_unreadable"))
        return path, row
