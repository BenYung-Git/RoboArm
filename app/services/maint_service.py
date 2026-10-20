from typing import Any

from app.services.ui_service import UiService
from app.storage.config_store import resolve_path
from app.storage.json_store import load_json


class MaintService:
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
            columns.append(
                {
                    "field": column["field"],
                    "label": self.ui.t(column["label_key"], lang),
                    "field_type": column["field_type"],
                    "is_flag": column["is_flag"],
                    "editable": column["editable"],
                    "auto_gen": column["auto_gen"],
                    "required": column["required"],
                }
            )
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
                "actions": self.ui.t("maint_label_actions", lang),
                "form_add": self.ui.t("maint_form_add", lang),
                "form_edit": self.ui.t("maint_form_edit", lang),
                "icon_add": self.ui.t("maint_icon_add", lang),
                "icon_edit": self.ui.t("maint_icon_edit", lang),
                "icon_disable": self.ui.t("maint_icon_disable", lang),
                "icon_enable": self.ui.t("maint_icon_enable", lang),
                "icon_save": self.ui.t("maint_icon_save", lang),
                "icon_cancel": self.ui.t("maint_icon_cancel", lang),
            },
        }

    def _validate_field(self, table_def: dict[str, Any], field: str) -> str:
        allowed = {column["field"] for column in table_def["columns"]}
        if field not in allowed:
            raise ValueError(f"Invalid field: {field}")
        return field

    def list_rows(
        self,
        table_key: str,
        search: str | None = None,
        flag_filters: dict[str, str] | None = None,
        language: str | None = None,
    ) -> list[dict[str, Any]]:
        lang = language if language is not None else self.ui.get_prefs()["language"]
        table_def = self.get_table_def(table_key)
        db_table = table_def["db_table"]
        fields = [self._validate_field(table_def, column["field"]) for column in table_def["columns"]]

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
            search_cols = self.search_columns(table_def)
            if search_cols:
                clauses = []
                for column in search_cols:
                    clauses.append(f"CAST({column['field']} AS TEXT) LIKE ?")
                    params.append(f"%{search}%")
                sql += " AND (" + " OR ".join(clauses) + ")"

        sql += " ORDER BY TxId DESC"
        rows = self.store.fetchall(sql, tuple(params))
        result = []
        for row in rows:
            item = {field: row[field] for field in fields}
            item["isDisable"] = bool(item["isDisable"])
            item["isDisable_label"] = (
                self.ui.t("maint_status_disabled", lang)
                if item["isDisable"]
                else self.ui.t("maint_status_enabled", lang)
            )
            result.append(item)
        return result

    def get_row(self, table_key: str, txid: int) -> dict[str, Any] | None:
        table_def = self.get_table_def(table_key)
        db_table = table_def["db_table"]
        fields = [self._validate_field(table_def, column["field"]) for column in table_def["columns"]]
        row = self.store.fetchone(
            f"SELECT {', '.join(fields)} FROM {db_table} WHERE TxId = ?",
            (txid,),
        )
        if row is None:
            return None
        lang = self.ui.get_prefs()["language"]
        item = {field: row[field] for field in fields}
        item["isDisable"] = bool(item["isDisable"])
        item["isDisable_label"] = (
            self.ui.t("maint_status_disabled", lang)
            if item["isDisable"]
            else self.ui.t("maint_status_enabled", lang)
        )
        return item

    def create_row(self, table_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        table_def = self.get_table_def(table_key)
        db_table = table_def["db_table"]
        values: dict[str, Any] = {
            "TxId": self.ui.next_txid(db_table),
            "isDisable": 0,
        }
        for column in table_def["columns"]:
            field = column["field"]
            if column["auto_gen"] or field == "isDisable":
                continue
            if field not in payload:
                if column["required"]:
                    raise ValueError(f"Missing required field: {field}")
                continue
            value = payload[field]
            if column["required"] and (value is None or str(value).strip() == ""):
                raise ValueError(f"Empty required field: {field}")
            values[field] = value

        fields = list(values.keys())
        placeholders = ", ".join(["?"] * len(fields))
        sql = f"INSERT INTO {db_table} ({', '.join(fields)}) VALUES ({placeholders})"
        self.store.execute(sql, tuple(values[field] for field in fields))
        created = self.get_row(table_key, values["TxId"])
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

        updates: dict[str, Any] = {}
        for column in table_def["columns"]:
            field = column["field"]
            if not column["editable"]:
                continue
            if field not in payload:
                continue
            value = payload[field]
            if column["required"] and (value is None or str(value).strip() == ""):
                raise ValueError(f"Empty required field: {field}")
            updates[field] = value

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
