from datetime import datetime, timezone
from typing import Any

from app.services.relation_service import RelationService
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
        self.relations = RelationService(self)

    def get_tables_config(self) -> dict[str, Any]:
        if self._tables_config is None:
            data = load_json(resolve_path(self.config["maint_tables_path"]))
            for key in ("max_list_columns", "tables"):
                if key not in data:
                    raise KeyError(f"Missing maintenance tables key: {key}")
            for table_key, table_def in data["tables"].items():
                if "supports_categories" not in table_def:
                    raise KeyError(
                        f"Missing supports_categories for table_key: {table_key}"
                    )
                if not isinstance(table_def["supports_categories"], bool):
                    raise ValueError(
                        "supports_categories must be boolean for table_key: "
                        f"{table_key}"
                    )
            self._tables_config = data
        return self._tables_config

    def get_table_def(self, table_key: str) -> dict[str, Any]:
        tables = self.get_tables_config()["tables"]
        if table_key not in tables:
            raise KeyError(f"Unknown maintenance table_key: {table_key}")
        table_def = tables[table_key]
        for key in ("db_table", "label_key", "columns", "supports_categories"):
            if key not in table_def:
                raise KeyError(f"Missing table def key: {key} for {table_key}")
        return table_def

    def persist_columns(self, table_def: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            column
            for column in table_def["columns"]
            if column.get("db_persist", True) is not False
        ]

    def display_columns(self, table_def: dict[str, Any]) -> list[dict[str, Any]]:
        max_cols = int(self.get_tables_config()["max_list_columns"])
        return table_def["columns"][:max_cols]

    def search_columns(self, table_def: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            column
            for column in self.display_columns(table_def)
            if (not column["is_flag"])
            and column.get("db_persist", True) is not False
            and column["field_type"] != "display"
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
            if column["field_type"] == "relation":
                item["options"] = self.relations.resolve_options(
                    table_key, column, lang, for_selection=True
                )
            if "force_value" in column:
                item["force_value"] = column["force_value"]
            if column.get("nullable"):
                item["nullable"] = True
            if "display_decimals" in column:
                item["display_decimals"] = int(column["display_decimals"])
            if "default_value" in column:
                item["default_value"] = column["default_value"]
            if column.get("db_persist") is False:
                item["db_persist"] = False
            if column["field_type"] == "display":
                item["display_from_field"] = column.get("display_from_field")
            if column.get("option_match_parent"):
                item["option_match_parent"] = column["option_match_parent"]
            columns.append(item)
        display = self.display_columns(table_def)
        result = {
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
        if "field_visibility" in table_def:
            result["field_visibility"] = table_def["field_visibility"]
        if "detail" in table_def:
            detail = table_def["detail"]
            for key in ("table_key", "parent_field", "presentation"):
                if key not in detail:
                    raise KeyError(f"Missing detail key: {key}")
            presentation = detail["presentation"]
            if presentation == "tab":
                for key in (
                    "tab_key",
                    "tab_label_key",
                    "require_parent_message_key",
                ):
                    if key not in detail:
                        raise KeyError(f"Missing detail key: {key}")
                result["detail"] = {
                    "table_key": detail["table_key"],
                    "parent_field": detail["parent_field"],
                    "presentation": presentation,
                    "tab_key": detail["tab_key"],
                    "tab_label": self.ui.t(detail["tab_label_key"], lang),
                    "require_parent_message": self.ui.t(
                        detail["require_parent_message_key"], lang
                    ),
                }
            elif presentation == "expand_row":
                for key in (
                    "title_key",
                    "add_label_key",
                    "collapsed_icon_key",
                    "expanded_icon_key",
                    "loading_key",
                    "load_error_key",
                    "embedded_toolbar",
                ):
                    if key not in detail:
                        raise KeyError(f"Missing detail key: {key}")
                toolbar = detail["embedded_toolbar"]
                if not isinstance(toolbar, dict):
                    raise ValueError(
                        "detail.embedded_toolbar must be an object"
                    )
                for key in (
                    "show_search",
                    "show_flag_filter",
                    "show_multi_select_controls",
                    "layout_save_placement",
                    "layout_settings_placement",
                ):
                    if key not in toolbar:
                        raise KeyError(
                            f"Missing detail.embedded_toolbar key: {key}"
                        )
                placement = toolbar["layout_save_placement"]
                if placement not in ("toolbar", "chrome"):
                    raise ValueError(
                        "Unsupported embedded_toolbar.layout_save_placement: "
                        f"{placement}"
                    )
                settings_placement = toolbar["layout_settings_placement"]
                if settings_placement not in ("none", "chrome"):
                    raise ValueError(
                        "Unsupported embedded_toolbar."
                        f"layout_settings_placement: {settings_placement}"
                    )
                detail_meta: dict[str, Any] = {
                    "table_key": detail["table_key"],
                    "parent_field": detail["parent_field"],
                    "presentation": presentation,
                    "title": self.ui.t(detail["title_key"], lang),
                    "add_label": self.ui.t(detail["add_label_key"], lang),
                    "collapsed_icon": self.ui.t(
                        detail["collapsed_icon_key"], lang
                    ),
                    "expanded_icon": self.ui.t(
                        detail["expanded_icon_key"], lang
                    ),
                    "tip_expand": self.ui.t("table_ui_tip_expand_row", lang),
                    "tip_collapse": self.ui.t(
                        "table_ui_tip_collapse_row", lang
                    ),
                    "loading_message": self.ui.t(detail["loading_key"], lang),
                    "load_error_message": self.ui.t(
                        detail["load_error_key"], lang
                    ),
                    "embedded_toolbar": {
                        "show_search": bool(toolbar["show_search"]),
                        "show_flag_filter": bool(toolbar["show_flag_filter"]),
                        "show_multi_select_controls": bool(
                            toolbar["show_multi_select_controls"]
                        ),
                        "layout_save_placement": placement,
                        "layout_settings_placement": settings_placement,
                    },
                }
                parent_context_fields = detail.get("parent_context_fields") or []
                if parent_context_fields:
                    if not isinstance(parent_context_fields, list):
                        raise ValueError(
                            "detail.parent_context_fields must be a list"
                        )
                    detail_meta["parent_context_fields"] = list(
                        parent_context_fields
                    )
                result["detail"] = detail_meta
            else:
                raise ValueError(
                    f"Unsupported detail.presentation: {presentation}"
                )
        return result

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
                "tip_open_layout": self.ui.t("table_ui_tip_open_layout", lang),
                "icon_layout": self.ui.t("table_ui_icon_layout", lang),
                "icon_layout_save_badge": self.ui.t(
                    "table_ui_icon_layout_save_badge", lang
                ),
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
                "layout_column_width": self.ui.t(
                    "table_ui_layout_column_width", lang
                ),
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
        if table_key == "product_combination_items":
            meta["labels"].update(
                {
                    "btn_equipment_connection": self.ui.t(
                        "eq_conn_btn_open", lang
                    ),
                    "msg_select_equipment_first": self.ui.t(
                        "eq_conn_msg_select_equipment_first", lang
                    ),
                    "msg_save_item_first": self.ui.t(
                        "eq_conn_msg_save_item_first", lang
                    ),
                    "msg_connection_not_applicable": self.ui.t(
                        "eq_conn_msg_not_applicable", lang
                    ),
                }
            )
            meta["equipment_connection"] = {
                "enabled": True,
                "equipment_field": "EquipmentTxId",
            }
        return meta

    def peek_next_txid(self, table_key: str) -> int:
        table_def = self.get_table_def(table_key)
        db_table = table_def["db_table"]
        return self.ui.next_txid(db_table)

    def peek_auto_gen_value(
        self, table_key: str, field: str, scope_value: Any
    ) -> Any:
        table_def = self.get_table_def(table_key)
        column = next(
            (item for item in table_def["columns"] if item["field"] == field),
            None,
        )
        if column is None:
            raise KeyError(f"Unknown field: {field}")
        if not column.get("auto_gen"):
            raise ValueError(f"Field is not auto_gen: {field}")
        rule = column.get("auto_gen_rule")
        if not isinstance(rule, dict):
            raise ValueError(f"Missing auto_gen_rule for field: {field}")
        if rule.get("kind") != "scoped_max_step":
            raise ValueError(f"Unsupported auto_gen_rule for field: {field}")
        return self._next_scoped_item_id(table_def, column, scope_value)

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
        self,
        table_key: str,
        table_def: dict[str, Any],
        row: dict[str, Any],
        language: str,
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
            if column["field_type"] == "display":
                continue
            if field not in item:
                continue
            if "display_decimals" in column and item[field] is not None:
                decimals = int(column["display_decimals"])
                item[field] = round(float(item[field]), decimals)
                item[f"{field}_display"] = f"{float(item[field]):.{decimals}f}"
            if column.get("options"):
                item[f"{field}_label"] = self._option_label(
                    column, item[field], language
                )
            if column["field_type"] == "relation":
                value = item[field]
                if value is None or str(value).strip() == "":
                    continue
                options = self.relations.resolve_options(
                    table_key,
                    column,
                    language,
                    for_selection=False,
                    include_value=value,
                )
                matched = None
                for option in options:
                    if str(option["value"]) == str(value):
                        matched = option
                        break
                if matched is None:
                    raise ValueError(
                        f"Unable to resolve relation option for field {field}: {value}"
                    )
                item[f"{field}_label"] = matched["label"]
                for key, annotate_value in matched.items():
                    if key in ("value", "label"):
                        continue
                    item[f"{field}_{key}"] = annotate_value
        for column in table_def["columns"]:
            if column["field_type"] != "display":
                continue
            field = column["field"]
            source = column.get("display_from_field")
            if not source:
                raise KeyError(f"Missing display_from_field for field: {field}")
            item[field] = item.get(source)
            if item[field] is None:
                item[field] = ""
        return item

    def _coerce_value(
        self,
        column: dict[str, Any],
        value: Any,
        *,
        owner_table_key: str | None = None,
        language: str | None = None,
        previous_value: Any | None = None,
    ) -> Any:
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
            if "display_decimals" in column:
                return round(number, int(column["display_decimals"]))
            if number.is_integer():
                return int(number)
            return number
        if field_type == "long":
            text = str(value).strip()
            if text == "":
                return None
            try:
                number = float(text)
            except ValueError as exc:
                raise ValueError(f"Invalid long for field: {column['field']}") from exc
            if not float(number).is_integer():
                raise ValueError(f"Invalid long for field: {column['field']}")
            return int(number)
        if field_type == "select":
            text = str(value).strip()
            allowed = {option["value"] for option in column.get("options") or []}
            if allowed and text not in allowed:
                raise ValueError(f"Invalid option for field: {column['field']}")
            return text
        if field_type == "relation":
            if owner_table_key is None:
                raise ValueError(
                    f"Missing owner_table_key for relation field: {column['field']}"
                )
            lang = language if language is not None else self.ui.get_prefs()["language"]
            return self.relations.validate_value(
                owner_table_key,
                column,
                value,
                lang,
                previous_value=previous_value,
            )
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
        eq_filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        lang = language if language is not None else self.ui.get_prefs()["language"]
        table_def = self.get_table_def(table_key)
        db_table = table_def["db_table"]
        fields = [
            self._validate_field(table_def, column["field"])
            for column in self.persist_columns(table_def)
        ]

        sql = f"SELECT {', '.join(fields)} FROM {db_table} WHERE 1 = 1"
        params: list[Any] = []

        if eq_filters:
            for field, value in eq_filters.items():
                self._validate_field(table_def, field)
                if value is None or str(value).strip() == "":
                    raise ValueError(f"Empty eq filter value for field: {field}")
                sql += f" AND {field} = ?"
                params.append(value)

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

        persist_names = {
            column["field"] for column in self.persist_columns(table_def)
        }
        order_parts: list[str] = []
        effective_specs = sort_specs
        if not effective_specs:
            effective_specs = table_def.get("default_list_sort")
        if effective_specs:
            seen: set[str] = set()
            for spec in effective_specs:
                field = self._validate_field(table_def, spec["field"])
                if field not in persist_names:
                    raise ValueError(f"Cannot sort non-persisted field: {field}")
                if field in seen:
                    raise ValueError(f"Duplicate sort field: {field}")
                direction = str(spec["dir"]).lower()
                if direction not in ("asc", "desc"):
                    raise ValueError(f"Invalid sort_dir: {spec['dir']}")
                seen.add(field)
                order_parts.append(f"{field} {direction.upper()}")
        elif sort_field is not None and sort_dir is not None and sort_dir != "":
            field = self._validate_field(table_def, sort_field)
            if field not in persist_names:
                raise ValueError(f"Cannot sort non-persisted field: {field}")
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
            result.append(self._decorate_row(table_key, table_def, item, lang))
        return result

    def get_row(self, table_key: str, txid: int) -> dict[str, Any] | None:
        table_def = self.get_table_def(table_key)
        db_table = table_def["db_table"]
        fields = [
            self._validate_field(table_def, column["field"])
            for column in self.persist_columns(table_def)
        ]
        row = self.store.fetchone(
            f"SELECT {', '.join(fields)} FROM {db_table} WHERE TxId = ?",
            (txid,),
        )
        if row is None:
            return None
        lang = self.ui.get_prefs()["language"]
        item = {field: row[field] for field in fields}
        return self._decorate_row(table_key, table_def, item, lang)

    def _utc_now_iso(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _next_scoped_item_id(
        self,
        table_def: dict[str, Any],
        column: dict[str, Any],
        scope_value: Any,
    ) -> float:
        rule = column.get("auto_gen_rule")
        if not isinstance(rule, dict):
            raise ValueError(f"Missing auto_gen_rule for field: {column['field']}")
        if rule.get("kind") != "scoped_max_step":
            raise ValueError(
                f"Unsupported auto_gen_rule kind for field: {column['field']}"
            )
        for key in (
            "scope_field",
            "first_value",
            "integer_step",
            "fraction_step",
            "decimals",
        ):
            if key not in rule:
                raise KeyError(f"Missing auto_gen_rule key: {key}")
        if scope_value is None or str(scope_value).strip() == "":
            raise ValueError(
                f"Missing scope value for ItemId: {rule['scope_field']}"
            )
        db_table = table_def["db_table"]
        scope_field = rule["scope_field"]
        decimals = int(rule["decimals"])
        row = self.store.fetchone(
            f"SELECT MAX({column['field']}) AS max_id FROM {db_table} "
            f"WHERE {scope_field} = ?",
            (scope_value,),
        )
        max_id = None if row is None else row["max_id"]
        if max_id is None:
            next_id = float(rule["first_value"])
        else:
            current = float(max_id)
            scaled = round(current * (10**decimals))
            fraction = int(scaled) % (10**decimals)
            if fraction == 0:
                next_id = current + float(rule["integer_step"])
            else:
                next_id = current + float(rule["fraction_step"])
        return round(next_id, decimals)

    def _build_writable_values(
        self,
        table_key: str,
        table_def: dict[str, Any],
        payload: dict[str, Any],
        *,
        for_create: bool,
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        values: dict[str, Any] = {}
        language = self.ui.get_prefs()["language"]
        now = self._utc_now_iso()
        for column in table_def["columns"]:
            field = column["field"]
            if column.get("db_persist") is False or column["field_type"] == "display":
                continue
            if "force_value" in column:
                values[field] = column["force_value"]
                continue
            if column["auto_gen"] and column["field_type"] == "datetime":
                on_events = column.get("auto_gen_on") or []
                if not isinstance(on_events, list):
                    raise ValueError(
                        f"auto_gen_on must be list for field: {field}"
                    )
                if for_create and "create" in on_events:
                    values[field] = now
                elif (not for_create) and "update" in on_events:
                    values[field] = now
                continue
            if (
                column["auto_gen"]
                and for_create
                and isinstance(column.get("auto_gen_rule"), dict)
                and column["auto_gen_rule"].get("kind") == "scoped_max_step"
            ):
                provided = payload.get(field)
                use_provided = (
                    bool(column.get("editable"))
                    and provided is not None
                    and str(provided).strip() != ""
                )
                if not use_provided:
                    scope_field = column["auto_gen_rule"]["scope_field"]
                    scope_value = payload.get(scope_field)
                    if scope_value is None and scope_field in values:
                        scope_value = values[scope_field]
                    values[field] = self._next_scoped_item_id(
                        table_def, column, scope_value
                    )
                    continue
            if column["auto_gen"] and for_create and not column["editable"]:
                continue
            if field == "isDisable":
                if for_create:
                    values[field] = 0
                continue
            if field not in payload:
                if for_create and "default_value" in column:
                    values[field] = column["default_value"]
                    continue
                if column["required"] and for_create:
                    raise ValueError(f"Missing required field: {field}")
                continue
            previous_value = None if existing is None else existing.get(field)
            value = self._coerce_value(
                column,
                payload[field],
                owner_table_key=table_key,
                language=language,
                previous_value=previous_value,
            )
            nullable = bool(column.get("nullable"))
            if nullable and (
                value is None
                or (isinstance(value, str) and str(value).strip() == "")
            ):
                if column["required"]:
                    raise ValueError(f"Empty required field: {field}")
                values[field] = None
                continue
            if column["required"] and (value is None or str(value).strip() == ""):
                raise ValueError(f"Empty required field: {field}")
            if value is None and column["field_type"] not in (
                "number",
                "long",
                "datetime",
            ):
                value = ""
            values[field] = value
        return values

    def _assert_unique_keys(
        self,
        table_key: str,
        table_def: dict[str, Any],
        values: dict[str, Any],
        *,
        exclude_txid: int | None,
    ) -> None:
        unique_keys = table_def.get("unique_keys") or []
        db_table = table_def["db_table"]
        for key_fields in unique_keys:
            if not isinstance(key_fields, list) or not key_fields:
                raise ValueError(f"Invalid unique_keys for table_key: {table_key}")
            for field in key_fields:
                if field not in values:
                    raise ValueError(
                        f"Missing unique key field in values: {field}"
                    )
            clauses = [f"{field} = ?" for field in key_fields]
            params: list[Any] = [values[field] for field in key_fields]
            sql = (
                f"SELECT TxId FROM {db_table} WHERE "
                + " AND ".join(clauses)
            )
            if exclude_txid is not None:
                sql += " AND TxId <> ?"
                params.append(exclude_txid)
            row = self.store.fetchone(sql, tuple(params))
            if row is not None:
                raise ValueError(
                    "Duplicate unique key: " + ", ".join(key_fields)
                )

    def _assert_protected_fields(
        self,
        table_key: str,
        table_def: dict[str, Any],
        existing: dict[str, Any],
        updates: dict[str, Any],
    ) -> None:
        protected = table_def.get("protected_fields_when_referenced") or []
        if not protected:
            return
        if not self.relations.is_value_referenced(table_key, existing["TxId"]):
            return
        for field in protected:
            if field not in updates:
                continue
            if str(updates[field]) != str(existing.get(field)):
                raise ValueError(
                    f"Field locked when referenced: {field}"
                )

    def _assert_workflow_step_item_scope(
        self, values: dict[str, Any]
    ) -> None:
        """CombinationItemTxId must belong to the workflow's combination."""
        workflow_txid = values.get("WorkflowTxId")
        item_txid = values.get("CombinationItemTxId")
        if item_txid is None or str(item_txid).strip() == "":
            return
        if workflow_txid is None or str(workflow_txid).strip() == "":
            raise ValueError("Missing WorkflowTxId for CombinationItemTxId")
        workflow = self.store.fetchone(
            "SELECT CombinationTxId FROM workflows WHERE TxId = ?",
            (workflow_txid,),
        )
        if workflow is None:
            raise ValueError(f"Invalid WorkflowTxId: {workflow_txid}")
        item = self.store.fetchone(
            "SELECT CombinationTxId FROM product_combination_items WHERE TxId = ?",
            (item_txid,),
        )
        if item is None:
            raise ValueError(f"Invalid CombinationItemTxId: {item_txid}")
        if str(item["CombinationTxId"]) != str(workflow["CombinationTxId"]):
            raise ValueError(
                "CombinationItemTxId does not belong to workflow combination"
            )

    def create_row(self, table_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        table_def = self.get_table_def(table_key)
        db_table = table_def["db_table"]
        values = self._build_writable_values(
            table_key, table_def, payload, for_create=True
        )
        if table_key == "workflow_steps":
            self._assert_workflow_step_item_scope(values)
        self._assert_unique_keys(
            table_key, table_def, values, exclude_txid=None
        )

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

        updates = self._build_writable_values(
            table_key,
            table_def,
            payload,
            for_create=False,
            existing=existing,
        )
        updates.pop("isDisable", None)
        if not updates:
            raise ValueError("No editable fields to update")
        self._assert_protected_fields(table_key, table_def, existing, updates)
        merged = dict(existing)
        merged.update(updates)
        if table_key == "workflow_steps":
            self._assert_workflow_step_item_scope(merged)
        self._assert_unique_keys(
            table_key, table_def, merged, exclude_txid=txid
        )

        assignments = ", ".join([f"{field} = ?" for field in updates])
        sql = f"UPDATE {db_table} SET {assignments} WHERE TxId = ?"
        self.store.execute(sql, tuple(list(updates.values()) + [txid]))
        if (
            table_key == "workflows"
            and "CombinationTxId" in updates
            and str(updates["CombinationTxId"])
            != str(existing.get("CombinationTxId"))
        ):
            self._clear_out_of_scope_workflow_step_items(
                txid, updates["CombinationTxId"]
            )
        updated = self.get_row(table_key, txid)
        if updated is None:
            raise RuntimeError("Update succeeded but row not found")
        return updated

    def _clear_out_of_scope_workflow_step_items(
        self, workflow_txid: int, combination_txid: Any
    ) -> None:
        """When a workflow changes combination, clear items not in the new combo."""
        rows = self.store.fetchall(
            """
            SELECT TxId, CombinationItemTxId FROM workflow_steps
            WHERE WorkflowTxId = ?
              AND CombinationItemTxId IS NOT NULL
            """,
            (workflow_txid,),
        )
        for row in rows:
            item = self.store.fetchone(
                """
                SELECT CombinationTxId FROM product_combination_items
                WHERE TxId = ?
                """,
                (row["CombinationItemTxId"],),
            )
            if item is None or str(item["CombinationTxId"]) != str(
                combination_txid
            ):
                self.store.execute(
                    """
                    UPDATE workflow_steps
                    SET CombinationItemTxId = NULL
                    WHERE TxId = ?
                    """,
                    (row["TxId"],),
                )

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
        if table_key == "workflows":
            self.store.execute(
                "UPDATE workflow_steps SET isDisable = ? WHERE WorkflowTxId = ?",
                (new_value, txid),
            )
        updated = self.get_row(table_key, txid)
        if updated is None:
            raise RuntimeError("Toggle succeeded but row not found")
        return updated
