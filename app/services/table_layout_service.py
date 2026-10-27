from datetime import datetime, timezone
from typing import Any

from app.services.maint_service import MaintService
from app.services.ui_service import UiService
from app.storage.config_store import resolve_path
from app.storage.json_store import load_json


class TableLayoutService:
    """Shared layout settings for table_ui hosts (inventory and future tables)."""

    def __init__(self, ui_service: UiService, maint_service: MaintService) -> None:
        self.ui = ui_service
        self.maint = maint_service
        self.store = ui_service.store
        self.config = ui_service.config
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS ui_table_settings (
                TxId INTEGER PRIMARY KEY,
                table_key TEXT NOT NULL UNIQUE,
                table_name TEXT NOT NULL,
                zebra_enabled INTEGER NOT NULL DEFAULT 1,
                zebra_color TEXT NOT NULL DEFAULT 'light_blue',
                isDisable INTEGER NOT NULL DEFAULT 0,
                Remark TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS ui_table_columns (
                TxId INTEGER PRIMARY KEY,
                table_setting_id INTEGER NOT NULL,
                field_key TEXT NOT NULL,
                field_label_key TEXT NOT NULL,
                field_desc_key TEXT NOT NULL,
                visible INTEGER NOT NULL DEFAULT 0,
                display_order INTEGER NOT NULL DEFAULT 0,
                sort_direction TEXT NOT NULL DEFAULT '',
                column_width INTEGER NOT NULL DEFAULT 100,
                isDisable INTEGER NOT NULL DEFAULT 0,
                Remark TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (table_setting_id, field_key)
            )
            """
        )
        columns = {
            row["name"]
            for row in self.store.fetchall("PRAGMA table_info(ui_table_columns)")
        }
        if "column_width" not in columns:
            self.store.execute(
                "ALTER TABLE ui_table_columns "
                "ADD COLUMN column_width INTEGER NOT NULL DEFAULT 100"
            )

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def get_layout_config(self) -> dict[str, Any]:
        tables_config = self.maint.get_tables_config()
        if "layout" not in tables_config:
            raise KeyError("Missing tables.json layout config")
        layout = tables_config["layout"]
        for key in ("data_column_width", "system_columns"):
            if key not in layout:
                raise KeyError(f"Missing tables.json layout key: {key}")
        data_width = layout["data_column_width"]
        for key in ("default", "min", "max"):
            if key not in data_width:
                raise KeyError(f"Missing data_column_width key: {key}")
        if not isinstance(layout["system_columns"], list):
            raise ValueError("layout.system_columns must be a list")
        for item in layout["system_columns"]:
            for key in (
                "field_key",
                "label_key",
                "desc_key",
                "default_width",
                "min_width",
                "max_width",
                "sortable",
                "can_hide",
                "can_reorder",
            ):
                if key not in item:
                    raise KeyError(f"Missing system column key: {key}")
        return layout

    def system_column_defs(self) -> dict[str, dict[str, Any]]:
        return {
            item["field_key"]: item for item in self.get_layout_config()["system_columns"]
        }

    def width_limits_for_field(self, field_key: str) -> tuple[int, int, int]:
        layout = self.get_layout_config()
        system = self.system_column_defs()
        if field_key in system:
            item = system[field_key]
            return (
                int(item["default_width"]),
                int(item["min_width"]),
                int(item["max_width"]),
            )
        data = layout["data_column_width"]
        return (int(data["default"]), int(data["min"]), int(data["max"]))

    def get_zebra_colors_config(self) -> dict[str, Any]:
        data = load_json(resolve_path(self.config["zebra_colors_path"]))
        for key in ("default_color_key", "colors"):
            if key not in data:
                raise KeyError(f"Missing zebra_colors key: {key}")
        return data

    def zebra_color_map(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in self.get_zebra_colors_config()["colors"]:
            result[item["color_key"]] = item["css_value"]
        return result

    def initial_default_visible_count(self) -> int:
        """Initial default visible data columns (including TxId), not a user max."""
        return int(self.maint.get_tables_config()["max_list_columns"])

    def ensure_table_layout(self, table_key: str) -> dict[str, Any]:
        table_def = self.maint.get_table_def(table_key)
        existing = self.store.fetchone(
            """
            SELECT TxId
            FROM ui_table_settings
            WHERE table_key = ? AND isDisable = 0
            """,
            (table_key,),
        )
        if existing is None:
            return self._create_default_layout(table_key, table_def)
        self._sync_columns(int(existing["TxId"]), table_def)
        return self.get_layout(table_key)

    def _insert_column_row(
        self,
        connection: Any,
        *,
        col_txid: int,
        setting_id: int,
        field_key: str,
        label_key: str,
        desc_key: str,
        visible: int,
        display_order: int,
        sort_dir: str,
        column_width: int,
        now: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO ui_table_columns (
                TxId, table_setting_id, field_key, field_label_key,
                field_desc_key, visible, display_order, sort_direction,
                column_width, isDisable, Remark, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '', ?, ?)
            """,
            (
                col_txid,
                setting_id,
                field_key,
                label_key,
                desc_key,
                visible,
                display_order,
                sort_dir,
                column_width,
                now,
                now,
            ),
        )

    def _create_default_layout(
        self, table_key: str, table_def: dict[str, Any]
    ) -> dict[str, Any]:
        now = self._now()
        zebra = self.get_zebra_colors_config()
        default_color = zebra["default_color_key"]
        if default_color not in self.zebra_color_map():
            raise KeyError(f"Unknown default zebra color: {default_color}")
        data_default = int(self.get_layout_config()["data_column_width"]["default"])
        system_defs = self.get_layout_config()["system_columns"]

        def _insert(connection: Any) -> None:
            row = connection.execute(
                "SELECT COALESCE(MAX(TxId), 0) + 1 AS next_id FROM ui_table_settings"
            ).fetchone()
            setting_id = int(row["next_id"])
            connection.execute(
                """
                INSERT INTO ui_table_settings (
                    TxId, table_key, table_name, zebra_enabled, zebra_color,
                    isDisable, Remark, created_at, updated_at
                ) VALUES (?, ?, ?, 1, ?, 0, '', ?, ?)
                """,
                (
                    setting_id,
                    table_key,
                    table_def["label_key"],
                    default_color,
                    now,
                    now,
                ),
            )
            max_visible = self.initial_default_visible_count()
            visible_count = 0
            display_order = 1
            max_row = connection.execute(
                "SELECT COALESCE(MAX(TxId), 0) AS max_id FROM ui_table_columns"
            ).fetchone()
            col_txid = int(max_row["max_id"]) + 1
            for system in system_defs:
                self._insert_column_row(
                    connection,
                    col_txid=col_txid,
                    setting_id=setting_id,
                    field_key=system["field_key"],
                    label_key=system["label_key"],
                    desc_key=system["desc_key"],
                    visible=1,
                    display_order=0,
                    sort_dir="",
                    column_width=int(system["default_width"]),
                    now=now,
                )
                col_txid += 1
            for column in table_def["columns"]:
                field = column["field"]
                if "desc_key" not in column:
                    raise KeyError(f"Missing desc_key for field: {field}")
                if visible_count < max_visible:
                    visible = 1
                    order = display_order
                    display_order += 1
                    visible_count += 1
                else:
                    visible = 0
                    order = 0
                sort_dir = ""
                default_sort = table_def.get("default_list_sort") or [
                    {"field": "TxId", "dir": "desc"}
                ]
                for spec in default_sort:
                    if spec.get("field") == field:
                        sort_dir = str(spec.get("dir") or "")
                        break
                self._insert_column_row(
                    connection,
                    col_txid=col_txid,
                    setting_id=setting_id,
                    field_key=field,
                    label_key=column["label_key"],
                    desc_key=column["desc_key"],
                    visible=visible,
                    display_order=order,
                    sort_dir=sort_dir,
                    column_width=data_default,
                    now=now,
                )
                col_txid += 1

        self.store.run_transaction(_insert)
        return self.get_layout(table_key)

    def _sync_columns(self, setting_id: int, table_def: dict[str, Any]) -> None:
        existing_rows = self.store.fetchall(
            """
            SELECT field_key FROM ui_table_columns
            WHERE table_setting_id = ? AND isDisable = 0
            """,
            (setting_id,),
        )
        existing = {row["field_key"] for row in existing_rows}
        now = self._now()
        data_default = int(self.get_layout_config()["data_column_width"]["default"])
        for system in self.get_layout_config()["system_columns"]:
            field = system["field_key"]
            if field in existing:
                continue

            def _add_system(
                connection: Any, sys_col: dict[str, Any] = system
            ) -> None:
                row = connection.execute(
                    "SELECT COALESCE(MAX(TxId), 0) + 1 AS next_id FROM ui_table_columns"
                ).fetchone()
                self._insert_column_row(
                    connection,
                    col_txid=int(row["next_id"]),
                    setting_id=setting_id,
                    field_key=sys_col["field_key"],
                    label_key=sys_col["label_key"],
                    desc_key=sys_col["desc_key"],
                    visible=1,
                    display_order=0,
                    sort_dir="",
                    column_width=int(sys_col["default_width"]),
                    now=now,
                )

            self.store.run_transaction(_add_system)

        for column in table_def["columns"]:
            field = column["field"]
            if field in existing:
                continue
            if "desc_key" not in column:
                raise KeyError(f"Missing desc_key for field: {field}")

            def _add(connection: Any, col: dict[str, Any] = column) -> None:
                row = connection.execute(
                    "SELECT COALESCE(MAX(TxId), 0) + 1 AS next_id FROM ui_table_columns"
                ).fetchone()
                self._insert_column_row(
                    connection,
                    col_txid=int(row["next_id"]),
                    setting_id=setting_id,
                    field_key=col["field"],
                    label_key=col["label_key"],
                    desc_key=col["desc_key"],
                    visible=0,
                    display_order=0,
                    sort_dir="",
                    column_width=data_default,
                    now=now,
                )

            self.store.run_transaction(_add)

    def _validate_column_width(self, field_key: str, width: Any) -> int:
        default, min_width, max_width = self.width_limits_for_field(field_key)
        if width is None or width == "":
            raise ValueError(f"Missing column_width for {field_key}")
        try:
            width_int = int(width)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid column_width for {field_key}") from exc
        if width_int < min_width or width_int > max_width:
            raise ValueError(
                f"column_width for {field_key} must be between "
                f"{min_width} and {max_width}"
            )
        return width_int

    def get_layout(self, table_key: str, language: str | None = None) -> dict[str, Any]:
        lang = language if language is not None else self.ui.get_prefs()["language"]
        setting = self.store.fetchone(
            """
            SELECT TxId, table_key, table_name, zebra_enabled, zebra_color,
                   isDisable, Remark, created_at, updated_at
            FROM ui_table_settings
            WHERE table_key = ? AND isDisable = 0
            """,
            (table_key,),
        )
        if setting is None:
            return self.ensure_table_layout(table_key)

        columns = self.store.fetchall(
            """
            SELECT TxId, table_setting_id, field_key, field_label_key, field_desc_key,
                   visible, display_order, sort_direction, column_width, isDisable,
                   Remark, created_at, updated_at
            FROM ui_table_columns
            WHERE table_setting_id = ? AND isDisable = 0
            """,
            (int(setting["TxId"]),),
        )
        zebra = self.get_zebra_colors_config()
        color_options = []
        for item in zebra["colors"]:
            color_options.append(
                {
                    "color_key": item["color_key"],
                    "label": self.ui.t(item["label_key"], lang),
                    "css_value": item["css_value"],
                }
            )

        system_defs = self.system_column_defs()
        layout_cfg = self.get_layout_config()
        visible_cols: list[dict[str, Any]] = []
        hidden_cols: list[dict[str, Any]] = []
        system_cols: list[dict[str, Any]] = []
        for row in columns:
            field_key = row["field_key"]
            is_system = field_key in system_defs
            width = row["column_width"]
            if width is None:
                raise ValueError(f"Missing stored column_width for {field_key}")
            default, min_width, max_width = self.width_limits_for_field(field_key)
            item = {
                "TxId": int(row["TxId"]),
                "field_key": field_key,
                "field_label_key": row["field_label_key"],
                "field_desc_key": row["field_desc_key"],
                "field_label": self.ui.t(row["field_label_key"], lang),
                "field_desc": self.ui.t(row["field_desc_key"], lang),
                "visible": bool(row["visible"]),
                "display_order": int(row["display_order"]),
                "sort_direction": row["sort_direction"] or "",
                "column_width": int(width),
                "is_system": is_system,
                "sortable": (
                    False if is_system else True
                ),
                "can_hide": (
                    False
                    if is_system
                    else True
                ),
                "can_reorder": (
                    False
                    if is_system
                    else True
                ),
                "width_min": min_width,
                "width_max": max_width,
                "width_default": default,
            }
            if is_system:
                sys_def = system_defs[field_key]
                item["sortable"] = bool(sys_def["sortable"])
                item["can_hide"] = bool(sys_def["can_hide"])
                item["can_reorder"] = bool(sys_def["can_reorder"])
                item["visible"] = True
                item["sort_direction"] = ""
                system_cols.append(item)
                continue
            if item["visible"]:
                visible_cols.append(item)
            else:
                hidden_cols.append(item)

        visible_cols.sort(key=lambda col: col["display_order"])
        hidden_cols.sort(key=lambda col: col["field_label"])
        system_cols.sort(key=lambda col: col["field_key"])

        css_map = self.zebra_color_map()
        color_key = setting["zebra_color"]
        if color_key not in css_map:
            raise KeyError(f"Unknown zebra_color: {color_key}")

        return {
            "TxId": int(setting["TxId"]),
            "table_key": setting["table_key"],
            "table_name_key": setting["table_name"],
            "table_name": self.ui.t(setting["table_name"], lang),
            "zebra_enabled": bool(setting["zebra_enabled"]),
            "zebra_color": color_key,
            "zebra_css_value": css_map[color_key],
            "zebra_color_options": color_options,
            "columns": system_cols + visible_cols + hidden_cols,
            "list_fields": [col["field_key"] for col in visible_cols],
            "width_rules": {
                "data": {
                    "default": int(layout_cfg["data_column_width"]["default"]),
                    "min": int(layout_cfg["data_column_width"]["min"]),
                    "max": int(layout_cfg["data_column_width"]["max"]),
                },
                "system": {
                    item["field_key"]: {
                        "default": int(item["default_width"]),
                        "min": int(item["min_width"]),
                        "max": int(item["max_width"]),
                    }
                    for item in layout_cfg["system_columns"]
                },
            },
        }

    def save_layout(self, table_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        layout = self.ensure_table_layout(table_key)
        setting_id = layout["TxId"]
        zebra_enabled = bool(payload.get("zebra_enabled"))
        zebra_color = payload.get("zebra_color")
        color_map = self.zebra_color_map()
        if zebra_color not in color_map:
            raise ValueError(f"Invalid zebra_color: {zebra_color}")

        columns_payload = payload.get("columns")
        if not isinstance(columns_payload, list):
            raise ValueError("Missing columns list")

        table_def = self.maint.get_table_def(table_key)
        allowed = {column["field"] for column in table_def["columns"]}
        system_defs = self.system_column_defs()
        allowed |= set(system_defs.keys())
        by_field: dict[str, Any] = {}
        for item in columns_payload:
            field = item.get("field_key")
            if field not in allowed:
                raise ValueError(f"Invalid field_key: {field}")
            if field in by_field:
                raise ValueError(f"Duplicate field_key: {field}")
            by_field[field] = item

        for field in allowed:
            if field not in by_field:
                raise ValueError(f"Missing field_key in layout payload: {field}")

        for field, item in by_field.items():
            is_system = field in system_defs
            direction = item.get("sort_direction")
            if direction is None:
                direction = ""
            if is_system:
                if direction not in ("",):
                    raise ValueError(f"System column cannot sort: {field}")
                item["sort_direction"] = ""
                item["visible"] = True
            else:
                if direction not in ("", "asc", "desc"):
                    raise ValueError(f"Invalid sort_direction for {field}")
                item["sort_direction"] = direction
            item["column_width"] = self._validate_column_width(
                field, item.get("column_width")
            )

        now = self._now()

        def _save(connection: Any) -> None:
            connection.execute(
                """
                UPDATE ui_table_settings
                SET zebra_enabled = ?, zebra_color = ?, updated_at = ?
                WHERE TxId = ?
                """,
                (1 if zebra_enabled else 0, zebra_color, now, setting_id),
            )
            visible_ordered: list[str] = []
            for item in columns_payload:
                field = item["field_key"]
                if field in system_defs:
                    continue
                if bool(item.get("visible")):
                    visible_ordered.append(field)

            order_map: dict[str, int] = {}
            for index, field in enumerate(visible_ordered, start=1):
                order_map[field] = index

            for field, item in by_field.items():
                if field in system_defs:
                    visible = 1
                    display_order = 0
                    sort_direction = ""
                else:
                    visible = 1 if bool(item.get("visible")) else 0
                    display_order = order_map.get(field, 0) if visible else 0
                    sort_direction = item["sort_direction"]
                connection.execute(
                    """
                    UPDATE ui_table_columns
                    SET visible = ?, display_order = ?, sort_direction = ?,
                        column_width = ?, updated_at = ?
                    WHERE table_setting_id = ? AND field_key = ? AND isDisable = 0
                    """,
                    (
                        visible,
                        display_order,
                        sort_direction,
                        item["column_width"],
                        now,
                        setting_id,
                        field,
                    ),
                )

        self.store.run_transaction(_save)
        return self.get_layout(table_key)
