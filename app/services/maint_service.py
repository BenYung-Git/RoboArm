from typing import Any

from app.services.ui_service import UiService
from app.storage.config_store import resolve_path
from app.storage.json_store import load_json


class MaintService:
    """Shared file-maintenance CRUD for tables declared in tables.json."""

    def __init__(self, ui_service: UiService) -> None:
        self.ui = ui_service
        self.config = ui_service.config
        self.store = ui_service.store
        self._tables_config: dict[str, Any] | None = None

    def get_tables_config(self) -> dict[str, Any]:
        if self._tables_config is None:
            data = load_json(resolve_path(self.config["maint_tables_path"]))
            for key in ("max_list_columns", "tables"):
                if key not in data:
                    raise KeyError(f"Missing maintenance tables key: {key}")
            self._tables_config = data
        return self._tables_config

    def get_table_def(self, table_key: str) -> dict[str, Any]:
        tables = self.get_tables_config()["tables"]
        if table_key not in tables:
            raise KeyError(f"Unknown maintenance table_key: {table_key}")
        table_def = tables[table_key]
        for key in ("db_table", "label_key", "columns"):
            if key not in table_def:
                raise KeyError(f"Missing table def key: {key} for {table_key}")
        return table_def

    def display_columns(self, table_def: dict[str, Any]) -> list[dict[str, Any]]:
        max_cols = int(self.get_tables_config()["max_list_columns"])
        return table_def["columns"][:max_cols]

    def search_columns(self, table_def: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            column
            for column in self.display_columns(table_def)
            if not column["is_flag"]
        ]

    def flag_columns(self, table_def: dict[str, Any]) -> list[dict[str, Any]]:
        return [column for column in table_def["columns"] if column["is_flag"]]

    def build_meta(self, table_key: str, language: str | None = None) -> dict[str, Any]:
        lang = language if language is not None else self.ui.get_prefs()["language"]
        table_def = self.get_table_def(table_key)
        columns = []
        for column in table_def["columns"]:
            item = {
                "field": column["field"],
                "label": self.ui.t(column["label_key"], lang),
                "field_type": column["field_type"],
                "is_flag": column["is_flag"],
                "editable": column["editable"],
                "auto_gen": column["auto_gen"],
                "required": column["required"],
            }
            if column.get("options"):
                item["options"] = [
                    {
                        "value": option["value"],
                        "label": self.ui.t(option["label_key"], lang),
                    }
                    for option in column["options"]
                ]
            columns.append(item)
        display = self.display_columns(table_def)
        return {
            "table_key": table_key,
            "label": self.ui.t(table_def["label_key"], lang),
            "max_list_columns": int(self.get_tables_config()["max_list_columns"]),
            "columns": columns,
            "display_fields": [column["field"] for column in display],
            "search_fields": [
                column["field"] for column in self.search_columns(table_def)
            ],
            "flag_fields": [column["field"] for column in self.flag_columns(table_def)],
            "labels": {
                "search": self.ui.t("maint_label_search", lang),
                "filter_all": self.ui.t("maint_filter_all", lang),
                "status_enabled": self.ui.t("maint_status_enabled", lang),
                "status_disabled": self.ui.t("maint_status_disabled", lang),
                "tip_add": self.ui.t("maint_tip_add", lang),
                "tip_edit": self.ui.t("maint_tip_edit", lang),
                "tip_disable": self.ui.t("maint_tip_disable", lang),
                "tip_enable": self.ui.t("maint_tip_enable", lang),
                "tip_save": self.ui.t("maint_tip_save", lang),
                "tip_cancel": self.ui.t("maint_tip_cancel", lang),
                "tip_copy": self.ui.t("maint_tip_copy", lang),
                "actions": self.ui.t("maint_label_actions", lang),
                "form_add": self.ui.t("maint_form_add", lang),
                "form_edit": self.ui.t("maint_form_edit", lang),
                "form_copy": self.ui.t("maint_form_copy", lang),
                "form_view": self.ui.t("maint_form_view", lang),
                "icon_add": self.ui.t("maint_icon_add", lang),
                "icon_edit": self.ui.t("maint_icon_edit", lang),
                "icon_disable": self.ui.t("maint_icon_disable", lang),
                "icon_enable": self.ui.t("maint_icon_enable", lang),
                "icon_save": self.ui.t("maint_icon_save", lang),
                "icon_cancel": self.ui.t("maint_icon_cancel", lang),
                "icon_copy": self.ui.t("maint_icon_copy", lang),
                "confirm_disable": self.ui.t("maint_confirm_disable", lang),
                "confirm_enable": self.ui.t("maint_confirm_enable", lang),
                "confirm_discard": self.ui.t("maint_confirm_discard", lang),
                "msg_select_row": self.ui.t("maint_msg_select_row", lang),
                "msg_save_ok": self.ui.t("maint_msg_save_ok", lang),
                "msg_required": self.ui.t("maint_msg_required", lang),
            },
        }

    def build_table_ui_meta(
        self, table_key: str, language: str | None = None
    ) -> dict[str, Any]:
        """Meta for the shared table_ui architecture (inventory and future tables)."""
        lang = language if language is not None else self.ui.get_prefs()["language"]
        meta = self.build_meta(table_key, lang)
        meta["labels"].update(
            {
                "tab_list": self.ui.t("table_ui_tab_list", lang),
                "tab_edit": self.ui.t("table_ui_tab_edit", lang),
                "tab_attachments": self.ui.t("table_ui_tab_attachments", lang),
                "tab_messages": self.ui.t("table_ui_tab_messages", lang),
                "tip_search": self.ui.t("table_ui_tip_search", lang),
                "icon_search": self.ui.t("table_ui_icon_search", lang),
                "tip_nav_first": self.ui.t("table_ui_tip_nav_first", lang),
                "tip_nav_prev": self.ui.t("table_ui_tip_nav_prev", lang),
                "tip_nav_next": self.ui.t("table_ui_tip_nav_next", lang),
                "tip_nav_last": self.ui.t("table_ui_tip_nav_last", lang),
                "icon_nav_first": self.ui.t("table_ui_icon_nav_first", lang),
                "icon_nav_prev": self.ui.t("table_ui_icon_nav_prev", lang),
                "icon_nav_next": self.ui.t("table_ui_icon_nav_next", lang),
                "icon_nav_last": self.ui.t("table_ui_icon_nav_last", lang),
                "label_select_all": self.ui.t("table_ui_label_select_all", lang),
                "label_deselect_all": self.ui.t("table_ui_label_deselect_all", lang),
                "dirty_message": self.ui.t("table_ui_dirty_message", lang),
                "dirty_save": self.ui.t("table_ui_dirty_save", lang),
                "dirty_cancel": self.ui.t("table_ui_dirty_cancel", lang),
                "disabled_banner": self.ui.t("table_ui_disabled_banner", lang),
                "mode_add": self.ui.t("table_ui_mode_add", lang),
                "mode_edit": self.ui.t("table_ui_mode_edit", lang),
                "mode_copy": self.ui.t("table_ui_mode_copy", lang),
                "tab_layout": self.ui.t("table_ui_tab_layout", lang),
                "tip_layout": self.ui.t("table_ui_tip_layout", lang),
                "icon_layout": self.ui.t("table_ui_icon_layout", lang),
                "tip_save_layout": self.ui.t("table_ui_tip_save_layout", lang),
                "tip_cancel_layout": self.ui.t("table_ui_tip_cancel_layout", lang),
                "layout_title": self.ui.t("table_ui_layout_title", lang),
                "layout_table_name": self.ui.t("table_ui_layout_table_name", lang),
                "layout_zebra": self.ui.t("table_ui_layout_zebra", lang),
                "layout_zebra_enabled": self.ui.t("table_ui_layout_zebra_enabled", lang),
                "layout_zebra_color": self.ui.t("table_ui_layout_zebra_color", lang),
                "layout_columns": self.ui.t("table_ui_layout_columns", lang),
                "layout_visible": self.ui.t("table_ui_layout_visible", lang),
                "layout_field_name": self.ui.t("table_ui_layout_field_name", lang),
                "layout_field_desc": self.ui.t("table_ui_layout_field_desc", lang),
                "layout_sort_dir": self.ui.t("table_ui_layout_sort_dir", lang),
                "layout_sort_empty": self.ui.t("table_ui_layout_sort_empty", lang),
                "layout_sort_asc": self.ui.t("table_ui_layout_sort_asc", lang),
                "layout_sort_desc": self.ui.t("table_ui_layout_sort_desc", lang),
                "tip_move_up": self.ui.t("table_ui_tip_move_up", lang),
                "tip_move_down": self.ui.t("table_ui_tip_move_down", lang),
                "icon_move_up": self.ui.t("table_ui_icon_move_up", lang),
                "icon_move_down": self.ui.t("table_ui_icon_move_down", lang),
                "tip_drag": self.ui.t("table_ui_tip_drag", lang),
                "icon_drag": self.ui.t("table_ui_icon_drag", lang),
                "msg_layout_saved": self.ui.t("table_ui_msg_layout_saved", lang),
            }
        )
        return meta

    def peek_next_txid(self, table_key: str) -> int:
        table_def = self.get_table_def(table_key)
        db_table = table_def["db_table"]
        return self.ui.next_txid(db_table)

    def _validate_field(self, table_def: dict[str, Any], field: str) -> str:
        allowed = {column["field"] for column in table_def["columns"]}
        if field not in allowed:
            raise ValueError(f"Invalid field: {field}")
        return field

    def _option_label(
        self, column: dict[str, Any], value: Any, language: str
    ) -> Any:
        options = column.get("options") or []
        if not options:
            return value
        for option in options:
            if option["value"] == value:
                return self.ui.t(option["label_key"], language)
        return value

    def _decorate_row(
        self, table_def: dict[str, Any], row: dict[str, Any], language: str
    ) -> dict[str, Any]:
        item = dict(row)
        item["isDisable"] = bool(item.get("isDisable", 0))
        item["isDisable_label"] = (
            self.ui.t("maint_status_disabled", language)
            if item["isDisable"]
            else self.ui.t("maint_status_enabled", language)
        )
        for column in table_def["columns"]:
            field = column["field"]
            if field not in item:
                continue
            if column.get("options"):
                item[f"{field}_label"] = self._option_label(
                    column, item[field], language
                )
        return item

    def _coerce_value(self, column: dict[str, Any], value: Any) -> Any:
        field_type = column["field_type"]
        if value is None:
            return None
        if field_type == "number":
            text = str(value).strip()
            if text == "":
                return None
            try:
                number = float(text)
            except ValueError as exc:
                raise ValueError(f"Invalid number for field: {column['field']}") from exc
            if number.is_integer():
                return int(number)
            return number
        if field_type == "select":
            text = str(value).strip()
            allowed = {option["value"] for option in column.get("options") or []}
            if allowed and text not in allowed:
                raise ValueError(f"Invalid option for field: {column['field']}")
            return text
        if isinstance(value, str):
            return value
        return value

    def list_rows(
        self,
        table_key: str,
        search: str | None = None,
        flag_filters: dict[str, str] | None = None,
        language: str | None = None,
        sort_field: str | None = None,
        sort_dir: str | None = None,
        search_fields: list[str] | None = None,
        sort_specs: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        lang = language if language is not None else self.ui.get_prefs()["language"]
        table_def = self.get_table_def(table_key)
        db_table = table_def["db_table"]
        fields = [
            self._validate_field(table_def, column["field"])
            for column in table_def["columns"]
        ]

        sql = f"SELECT {', '.join(fields)} FROM {db_table} WHERE 1 = 1"
        params: list[Any] = []

        if flag_filters:
            for field, value in flag_filters.items():
                column = next(
                    (item for item in table_def["columns"] if item["field"] == field),
                    None,
                )
                if column is None or not column["is_flag"]:
                    raise ValueError(f"Invalid flag filter field: {field}")
                if value == "":
                    continue
                if value not in ("0", "1"):
                    raise ValueError(f"Invalid flag filter value: {value}")
                sql += f" AND {field} = ?"
                params.append(int(value))

        if search:
            if search_fields is not None:
                search_cols = [
                    {"field": self._validate_field(table_def, field)}
                    for field in search_fields
                ]
            else:
                search_cols = self.search_columns(table_def)
            if search_cols:
                clauses = []
                for column in search_cols:
                    clauses.append(f"CAST({column['field']} AS TEXT) LIKE ?")
                    params.append(f"%{search}%")
                sql += " AND (" + " OR ".join(clauses) + ")"

        order_parts: list[str] = []
        if sort_specs is not None:
            seen: set[str] = set()
            for spec in sort_specs:
                field = self._validate_field(table_def, spec["field"])
                if field in seen:
                    raise ValueError(f"Duplicate sort field: {field}")
                direction = str(spec["dir"]).lower()
                if direction not in ("asc", "desc"):
                    raise ValueError(f"Invalid sort_dir: {spec['dir']}")
                seen.add(field)
                order_parts.append(f"{field} {direction.upper()}")
        elif sort_field is not None and sort_dir is not None and sort_dir != "":
            field = self._validate_field(table_def, sort_field)
            direction = str(sort_dir).lower()
            if direction not in ("asc", "desc"):
                raise ValueError(f"Invalid sort_dir: {sort_dir}")
            order_parts.append(f"{field} {direction.upper()}")
            order_parts.append("TxId DESC")
        else:
            order_parts.append("TxId DESC")

        if order_parts:
            sql += " ORDER BY " + ", ".join(order_parts)
        rows = self.store.fetchall(sql, tuple(params))
        result = []
        for row in rows:
            item = {field: row[field] for field in fields}
            result.append(self._decorate_row(table_def, item, lang))
        return result

    def get_row(self, table_key: str, txid: int) -> dict[str, Any] | None:
        table_def = self.get_table_def(table_key)
        db_table = table_def["db_table"]
        fields = [
            self._validate_field(table_def, column["field"])
            for column in table_def["columns"]
        ]
        row = self.store.fetchone(
            f"SELECT {', '.join(fields)} FROM {db_table} WHERE TxId = ?",
            (txid,),
        )
        if row is None:
            return None
        lang = self.ui.get_prefs()["language"]
        item = {field: row[field] for field in fields}
        return self._decorate_row(table_def, item, lang)

    def _build_writable_values(
        self, table_def: dict[str, Any], payload: dict[str, Any], *, for_create: bool
    ) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for column in table_def["columns"]:
            field = column["field"]
            if column["auto_gen"]:
                continue
            if field == "isDisable":
                if for_create:
                    values[field] = 0
                continue
            if field not in payload:
                if column["required"] and for_create:
                    raise ValueError(f"Missing required field: {field}")
                continue
            value = self._coerce_value(column, payload[field])
            if column["required"] and (value is None or str(value).strip() == ""):
                raise ValueError(f"Empty required field: {field}")
            if value is None and column["field_type"] != "number":
                value = ""
            values[field] = value
        return values

    def create_row(self, table_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        table_def = self.get_table_def(table_key)
        db_table = table_def["db_table"]
        values = self._build_writable_values(table_def, payload, for_create=True)

        def _insert(connection: Any) -> int:
            row = connection.execute(
                f"SELECT COALESCE(MAX(TxId), 0) + 1 AS next_id FROM {db_table}"
            ).fetchone()
            txid = int(row["next_id"])
            values["TxId"] = txid
            fields = list(values.keys())
            placeholders = ", ".join(["?"] * len(fields))
            sql = (
                f"INSERT INTO {db_table} ({', '.join(fields)}) "
                f"VALUES ({placeholders})"
            )
            connection.execute(sql, tuple(values[field] for field in fields))
            return txid

        txid = self.store.run_transaction(_insert)
        created = self.get_row(table_key, txid)
        if created is None:
            raise RuntimeError("Create succeeded but row not found")
        return created

    def update_row(
        self, table_key: str, txid: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        table_def = self.get_table_def(table_key)
        db_table = table_def["db_table"]
        existing = self.get_row(table_key, txid)
        if existing is None:
            raise KeyError(f"Row not found: TxId={txid}")

        updates = self._build_writable_values(table_def, payload, for_create=False)
        updates.pop("isDisable", None)
        if not updates:
            raise ValueError("No editable fields to update")

        assignments = ", ".join([f"{field} = ?" for field in updates])
        sql = f"UPDATE {db_table} SET {assignments} WHERE TxId = ?"
        self.store.execute(sql, tuple(list(updates.values()) + [txid]))
        updated = self.get_row(table_key, txid)
        if updated is None:
            raise RuntimeError("Update succeeded but row not found")
        return updated

    def toggle_disable(self, table_key: str, txid: int) -> dict[str, Any]:
        table_def = self.get_table_def(table_key)
        db_table = table_def["db_table"]
        existing = self.get_row(table_key, txid)
        if existing is None:
            raise KeyError(f"Row not found: TxId={txid}")
        new_value = 0 if existing["isDisable"] else 1
        self.store.execute(
            f"UPDATE {db_table} SET isDisable = ? WHERE TxId = ?",
            (new_value, txid),
        )
        updated = self.get_row(table_key, txid)
        if updated is None:
            raise RuntimeError("Toggle succeeded but row not found")
        return updated
