"""Per-physical-equipment connection settings (no SDK load / no network I/O)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.services.ui_service import UiService

ALLOWED_DRIVER_TYPES = ("jaka",)
ALLOWED_CONNECTION_MODES = ("network",)
APPLICABLE_CATEGORY_CODES = frozenset({"robot_arm", "control_box"})
APPLICABLE_BRAND = "jaka"
IPV4_PATTERN = re.compile(
    r"^(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
    r"(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$"
)


class EquipmentConnectionService:
    def __init__(self, ui: UiService) -> None:
        self.ui = ui
        self.store = ui.store

    def _utc_now_iso(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _language(self, language: str | None) -> str:
        return language if language is not None else self.ui.get_prefs()["language"]

    def is_applicable_category_and_brand(
        self, category_code: str | None, brand: str | None
    ) -> bool:
        if category_code not in APPLICABLE_CATEGORY_CODES:
            return False
        if brand is None or str(brand).strip() == "":
            return False
        return str(brand).strip().lower() == APPLICABLE_BRAND

    def load_equipment(self, equipment_txid: int) -> dict[str, Any]:
        row = self.store.fetchone(
            """
            SELECT i.TxId, i.ItemCode, i.ItemName, i.ItemNameEn, i.Brand,
                   i.SerialNo, i.isDisable,
                   c.CategoryCode, c.zh_TW AS cat_zh_TW, c.en AS cat_en,
                   c.zh_CN AS cat_zh_CN
            FROM inventory i
            JOIN categories c ON c.TxId = i.Category
            WHERE i.TxId = ?
            """,
            (equipment_txid,),
        )
        if row is None:
            raise KeyError(f"Unknown equipment TxId: {equipment_txid}")
        return dict(row)

    def validate_host_address(self, host_address: str) -> str:
        text = str(host_address).strip()
        if text == "":
            raise ValueError("host_address_required")
        if not IPV4_PATTERN.fullmatch(text):
            raise ValueError("host_address_invalid_ipv4")
        return text

    def validate_payload(self, payload: dict[str, Any]) -> dict[str, str]:
        if "driver_type" not in payload:
            raise ValueError("driver_type_required")
        if "connection_mode" not in payload:
            raise ValueError("connection_mode_required")
        if "host_address" not in payload:
            raise ValueError("host_address_required")
        driver = str(payload["driver_type"]).strip().lower()
        mode = str(payload["connection_mode"]).strip().lower()
        if driver not in ALLOWED_DRIVER_TYPES:
            raise ValueError("driver_type_invalid")
        if mode not in ALLOWED_CONNECTION_MODES:
            raise ValueError("connection_mode_invalid")
        host = self.validate_host_address(payload["host_address"])
        remark = payload.get("remark")
        if remark is None:
            remark_text = ""
        else:
            remark_text = str(remark).strip()
        return {
            "DriverType": driver,
            "ConnectionMode": mode,
            "HostAddress": host,
            "Remark": remark_text,
        }

    def get_connection_row(self, equipment_txid: int) -> dict[str, Any] | None:
        row = self.store.fetchone(
            "SELECT * FROM equipment_connection WHERE EquipmentTxId = ?",
            (equipment_txid,),
        )
        return dict(row) if row is not None else None

    def build_view(
        self, equipment_txid: int, language: str | None = None
    ) -> dict[str, Any]:
        lang = self._language(language)
        equipment = self.load_equipment(equipment_txid)
        category_code = equipment["CategoryCode"]
        brand = equipment["Brand"]
        applicable = self.is_applicable_category_and_brand(category_code, brand)
        name_field = "ItemNameEn" if lang == "en" else "ItemName"
        category_label = equipment[
            "cat_en" if lang == "en" else ("cat_zh_CN" if lang == "zh_CN" else "cat_zh_TW")
        ]
        connection = self.get_connection_row(equipment_txid)
        configured = connection is not None
        connection_payload = None
        if connection is not None:
            connection_payload = {
                "driver_type": connection["DriverType"],
                "connection_mode": connection["ConnectionMode"],
                "host_address": connection["HostAddress"],
                "remark": connection["Remark"] or "",
                "updated_at": connection["UpdatedAt"],
            }
        return {
            "applicable": applicable,
            "configured": configured,
            "status_label": self.ui.t(
                "status_configured" if configured else "status_not_configured",
                lang,
            ),
            "equipment": {
                "txid": int(equipment["TxId"]),
                "item_code": equipment["ItemCode"],
                "name": equipment[name_field],
                "serial_no": equipment["SerialNo"] or "",
                "brand": brand,
                "category_code": category_code,
                "category_label": category_label,
                "is_disable": bool(equipment["isDisable"]),
            },
            "connection": connection_payload,
            "options": {
                "driver_types": [
                    {
                        "value": "jaka",
                        "label": self.ui.t("eq_conn_driver_jaka", lang),
                    }
                ],
                "connection_modes": [
                    {
                        "value": "network",
                        "label": self.ui.t("eq_conn_mode_network", lang),
                    }
                ],
            },
            "labels": {
                "title": self.ui.t("eq_conn_title", lang),
                "shared_warning": self.ui.t("eq_conn_shared_warning", lang),
                "equipment_name": self.ui.t("eq_conn_label_equipment_name", lang),
                "equipment_id": self.ui.t("eq_conn_label_equipment_id", lang),
                "equipment_category": self.ui.t(
                    "eq_conn_label_equipment_category", lang
                ),
                "driver_type": self.ui.t("eq_conn_label_driver_type", lang),
                "connection_mode": self.ui.t("eq_conn_label_connection_mode", lang),
                "host_address": self.ui.t("eq_conn_label_host_address", lang),
                "remark": self.ui.t("field_remark", lang),
                "save": self.ui.t("eq_conn_btn_save", lang),
                "cancel": self.ui.t("eq_conn_btn_cancel", lang),
                "clear": self.ui.t("eq_conn_btn_clear", lang),
                "clear_confirm": self.ui.t("eq_conn_clear_confirm", lang),
                "not_applicable": self.ui.t("eq_conn_msg_not_applicable", lang),
                "select_equipment_first": self.ui.t(
                    "eq_conn_msg_select_equipment_first", lang
                ),
                "save_item_first": self.ui.t("eq_conn_msg_save_item_first", lang),
                "saved": self.ui.t("eq_conn_msg_saved", lang),
                "cleared": self.ui.t("eq_conn_msg_cleared", lang),
                "host_hint": self.ui.t("eq_conn_hint_host_ipv4", lang),
            },
            "errors": {
                "driver_type_required": self.ui.t(
                    "eq_conn_err_driver_type_required", lang
                ),
                "driver_type_invalid": self.ui.t(
                    "eq_conn_err_driver_type_invalid", lang
                ),
                "connection_mode_required": self.ui.t(
                    "eq_conn_err_connection_mode_required", lang
                ),
                "connection_mode_invalid": self.ui.t(
                    "eq_conn_err_connection_mode_invalid", lang
                ),
                "host_address_required": self.ui.t(
                    "eq_conn_err_host_address_required", lang
                ),
                "host_address_invalid_ipv4": self.ui.t(
                    "eq_conn_err_host_address_invalid_ipv4", lang
                ),
                "not_applicable": self.ui.t("eq_conn_msg_not_applicable", lang),
            },
        }

    def save_connection(
        self, equipment_txid: int, payload: dict[str, Any], language: str | None = None
    ) -> dict[str, Any]:
        view = self.build_view(equipment_txid, language)
        if not view["applicable"]:
            raise ValueError("not_applicable")
        values = self.validate_payload(payload)
        now = self._utc_now_iso()
        existing = self.get_connection_row(equipment_txid)
        if existing is None:
            self.store.execute(
                """
                INSERT INTO equipment_connection (
                    EquipmentTxId, DriverType, ConnectionMode, HostAddress,
                    Remark, CreatedAt, UpdatedAt
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    equipment_txid,
                    values["DriverType"],
                    values["ConnectionMode"],
                    values["HostAddress"],
                    values["Remark"],
                    now,
                    now,
                ),
            )
        else:
            self.store.execute(
                """
                UPDATE equipment_connection
                SET DriverType = ?, ConnectionMode = ?, HostAddress = ?,
                    Remark = ?, UpdatedAt = ?
                WHERE EquipmentTxId = ?
                """,
                (
                    values["DriverType"],
                    values["ConnectionMode"],
                    values["HostAddress"],
                    values["Remark"],
                    now,
                    equipment_txid,
                ),
            )
        return self.build_view(equipment_txid, language)

    def clear_connection(
        self, equipment_txid: int, language: str | None = None
    ) -> dict[str, Any]:
        view = self.build_view(equipment_txid, language)
        if not view["applicable"]:
            raise ValueError("not_applicable")
        self.store.execute(
            "DELETE FROM equipment_connection WHERE EquipmentTxId = ?",
            (equipment_txid,),
        )
        return self.build_view(equipment_txid, language)
