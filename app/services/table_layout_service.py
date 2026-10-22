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
                isDisable INTEGER NOT NULL DEFAULT 0,
                Remark TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (table_setting_id, field_key)
            )
            """
        )

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

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

    def _create_default_layout(
        self, table_key: str, table_def: dict[str, Any]
    ) -> dict[str, Any]:
        now = self._now()
        zebra = self.get_zebra_colors_config()
        default_color = zebra["default_color_key"]
        if default_color not in self.zebra_color_map():
            raise KeyError(f"Unknown default zebra color: {default_color}")

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
                sort_dir = "desc" if field == "TxId" else ""
                connection.execute(
                    """
                    INSERT INTO ui_table_columns (
                        TxId, table_setting_id, field_key, field_label_key,
                        field_desc_key, visible, display_order, sort_direction,
                        isDisable, Remark, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '', ?, ?)
                    """,
                    (
                        col_txid,
                        setting_id,
                        field,
                        column["label_key"],
                        column["desc_key"],
                        visible,
                        order,
                        sort_dir,
                        now,
                        now,
                    ),
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
                connection.execute(
                    """
                    INSERT INTO ui_table_columns (
                        TxId, table_setting_id, field_key, field_label_key,
                        field_desc_key, visible, display_order, sort_direction,
                        isDisable, Remark, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 0, 0, '', 0, '', ?, ?)
                    """,
                    (
                        int(row["next_id"]),
                        setting_id,
                        col["field"],
                        col["label_key"],
                        col["desc_key"],
                        now,
                        now,
                    ),
                )

            self.store.run_transaction(_add)

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
                   visible, display_order, sort_direction, isDisable, Remark,
                   created_at, updated_at
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

        visible_cols: list[dict[str, Any]] = []
        hidden_cols: list[dict[str, Any]] = []
        for row in columns:
            item = {
                "TxId": int(row["TxId"]),
                "field_key": row["field_key"],
                "field_label_key": row["field_label_key"],
                "field_desc_key": row["field_desc_key"],
                "field_label": self.ui.t(row["field_label_key"], lang),
                "field_desc": self.ui.t(row["field_desc_key"], lang),
                "visible": bool(row["visible"]),
                "display_order": int(row["display_order"]),
                "sort_direction": row["sort_direction"] or "",
            }
            if item["visible"]:
                visible_cols.append(item)
            else:
                hidden_cols.append(item)

        visible_cols.sort(key=lambda col: col["display_order"])
        hidden_cols.sort(key=lambda col: col["field_label"])

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
            "columns": visible_cols + hidden_cols,
            "list_fields": [col["field_key"] for col in visible_cols],
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
        by_field: dict[str, Any] = {}
        for item in columns_payload:
            field = item.get("field_key")
            if field not in allowed:
                raise ValueError(f"Invalid field_key: {field}")
            if field in by_field:
                raise ValueError(f"Duplicate field_key: {field}")
            by_field[field] = item

        for field, item in by_field.items():
            direction = item.get("sort_direction")
            if direction is None:
                direction = ""
            if direction not in ("", "asc", "desc"):
                raise ValueError(f"Invalid sort_direction for {field}")
            item["sort_direction"] = direction

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
                if bool(item.get("visible")):
                    visible_ordered.append(item["field_key"])

            order_map: dict[str, int] = {}
            for index, field in enumerate(visible_ordered, start=1):
                order_map[field] = index

            for field, item in by_field.items():
                visible = 1 if bool(item.get("visible")) else 0
                display_order = order_map.get(field, 0) if visible else 0
                connection.execute(
                    """
                    UPDATE ui_table_columns
                    SET visible = ?, display_order = ?, sort_direction = ?,
                        updated_at = ?
                    WHERE table_setting_id = ? AND field_key = ? AND isDisable = 0
                    """,
                    (
                        visible,
                        display_order,
                        item["sort_direction"],
                        now,
                        setting_id,
                        field,
                    ),
                )

        self.store.run_transaction(_save)
        return self.get_layout(table_key)
