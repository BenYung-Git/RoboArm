"""Serve approved CAD static assets from the attachment-paths model root.

Does not expose the entire model library; only allowlisted relative files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.attachment_paths_service import AttachmentPathsService
from app.services.ui_service import UiService

# Allowlisted CAD packages (relative to model library root).
CAD_PACKAGES: dict[str, dict[str, Any]] = {
    "jaka_zu7": {
        "glb_rel": Path("Jaka") / "zu7" / "web" / "zu7_assembly.glb",
        "manifest_rel": Path("Jaka") / "zu7" / "web" / "manifest.json",
        "parts": [
            {"node_name": "NAUO1", "product_name": "Zu 7 00", "label_key": "cad_part_zu7_00"},
            {"node_name": "NAUO2", "product_name": "Zu 7 01", "label_key": "cad_part_zu7_01"},
            {"node_name": "NAUO3", "product_name": "ZU 7 02", "label_key": "cad_part_zu7_02"},
            {"node_name": "NAUO4", "product_name": "ZU 7 03", "label_key": "cad_part_zu7_03"},
            {"node_name": "NAUO5", "product_name": "Zu 7 04", "label_key": "cad_part_zu7_04"},
            {"node_name": "NAUO6", "product_name": "Zu 7 05", "label_key": "cad_part_zu7_05"},
            {"node_name": "NAUO7", "product_name": "Zu 7 06", "label_key": "cad_part_zu7_06"},
        ],
        # From reconcile (gltf Y-up meters); display only — not used to rescale the mesh.
        "expected_aabb_m": {
            "dx": 0.787685,
            "dy": 0.300650,
            "dz": 0.233188,
            "unit": "m",
            "frame": "gltf_Yup",
        },
    }
}


class CadModelService:
    def __init__(self, ui: UiService, paths: AttachmentPathsService | None = None) -> None:
        self.ui = ui
        self.paths = paths if paths is not None else AttachmentPathsService(ui)

    def _model_root(self) -> Path:
        info = self.paths.get_effective_path()
        if not info.get("supported"):
            raise ValueError("model_root_os_unsupported")
        root_text = str(info.get("effective_path") or "").strip()
        if root_text == "":
            raise ValueError("model_root_not_set")
        root = Path(root_text)
        if not root.is_absolute():
            raise ValueError("model_root_not_absolute")
        if not root.is_dir():
            raise ValueError("model_root_missing")
        return root.resolve()

    def _safe_under_root(self, root: Path, relative: Path) -> Path:
        if relative.is_absolute():
            raise ValueError("cad_path_invalid")
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("cad_path_outside_root") from exc
        return candidate

    def resolve_glb(self, model_key: str) -> Path:
        pkg = CAD_PACKAGES.get(model_key)
        if pkg is None:
            raise KeyError(f"Unknown CAD model_key: {model_key}")
        root = self._model_root()
        path = self._safe_under_root(root, Path(pkg["glb_rel"]))
        if not path.is_file():
            raise FileNotFoundError(f"CAD GLB not found: {path}")
        return path

    def build_viewer_cad_static(
        self, model_key: str, language: str | None = None
    ) -> dict[str, Any] | None:
        if model_key not in CAD_PACKAGES:
            return None
        lang = language if language is not None else self.ui.get_prefs()["language"]
        pkg = CAD_PACKAGES[model_key]
        available = False
        detail = ""
        try:
            glb = self.resolve_glb(model_key)
            available = True
            detail = glb.name
        except (ValueError, FileNotFoundError, KeyError) as exc:
            detail = str(exc)

        parts = []
        for item in pkg["parts"]:
            parts.append(
                {
                    "node_name": item["node_name"],
                    "product_name": item["product_name"],
                    "label": self.ui.t(item["label_key"], lang),
                }
            )

        aabb = dict(pkg["expected_aabb_m"])
        # Prefer reconciled AABB from manifest if present (read-only).
        try:
            root = self._model_root()
            man_path = self._safe_under_root(root, Path(pkg["manifest_rel"]))
            if man_path.is_file():
                man = json.loads(man_path.read_text(encoding="utf-8"))
                world = (
                    (man.get("aabb_reconcile") or {})
                    .get("overall", {})
                    .get("glb_world_m")
                )
                if isinstance(world, dict) and "dx" in world:
                    aabb = {
                        "xmin": float(world.get("xmin", 0.0)),
                        "ymin": float(world.get("ymin", 0.0)),
                        "zmin": float(world.get("zmin", 0.0)),
                        "xmax": float(world.get("xmax", 0.0)),
                        "ymax": float(world.get("ymax", 0.0)),
                        "zmax": float(world.get("zmax", 0.0)),
                        "dx": float(world["dx"]),
                        "dy": float(world["dy"]),
                        "dz": float(world["dz"]),
                        "unit": "m",
                        "frame": "gltf_Yup",
                        "source": "manifest.aabb_reconcile.overall.glb_world_m",
                    }
        except (ValueError, FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
            pass

        return {
            "enabled": available,
            "model_key": model_key,
            "glb_url": f"/api/cad-models/{model_key}/assembly.glb",
            "parts": parts,
            "aabb_m": aabb,
            "units": "m",
            "up_axis": "Y",
            "no_extra_scale": True,
            "no_extra_axis_convert": True,
            "available": available,
            "detail": detail,
            "disclaimer": self.ui.t("cad_static_disclaimer", lang),
            "labels": {
                "fit": self.ui.t("cad_btn_fit", lang),
                "reset": self.ui.t("cad_btn_reset", lang),
                "grid": self.ui.t("cad_label_grid", lang),
                "axes": self.ui.t("cad_label_axes", lang),
                "parts": self.ui.t("cad_label_parts", lang),
                "size": self.ui.t("cad_label_size", lang),
                "loading": self.ui.t("cad_msg_loading", lang),
                "load_failed": self.ui.t("cad_msg_load_failed", lang),
                "unavailable": self.ui.t("cad_msg_unavailable", lang),
            },
        }
