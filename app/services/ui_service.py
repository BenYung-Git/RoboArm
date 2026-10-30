from datetime import datetime, timezone
from typing import Any

from app.storage.config_store import load_app_config, resolve_path
from app.storage.json_store import load_json, save_json
from app.storage.sqlite_store import SqliteStore


class UiService:
    def __init__(
        self,
        sqlite_path: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        if config is not None:
            self.config = config
        else:
            self.config = load_app_config()
        if self.config["default_storage"] != "sqlite3":
            raise ValueError(
                f"Unsupported default_storage: {self.config['default_storage']}"
            )
        if sqlite_path is not None:
            if str(sqlite_path).strip() == "":
                raise ValueError("sqlite_path must not be empty")
            db_path = resolve_path(sqlite_path)
        else:
            if "sqlite_path" not in self.config:
                raise KeyError("Missing app config key: sqlite_path")
            db_path = resolve_path(self.config["sqlite_path"])
        self.store = SqliteStore(db_path)
        self.fonts_path = resolve_path(self.config["fonts_json_path"])
        self.prefs_path = resolve_path(self.config["prefs_json_path"])
        self.ensure_schema()
        self.ensure_seed_data()
        self.ensure_prefs()

    def table_column_names(self, table_name: str) -> set[str]:
        rows = self.store.fetchall(f"PRAGMA table_info({table_name})")
        return {row["name"] for row in rows}

    def next_txid(self, table_name: str) -> int:
        row = self.store.fetchone(
            f"SELECT COALESCE(MAX(TxId), 0) + 1 AS next_id FROM {table_name}"
        )
        if row is None:
            raise RuntimeError(f"Unable to allocate TxId for table: {table_name}")
        return int(row["next_id"])

    def ensure_schema(self) -> None:
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS languages (
                code TEXT PRIMARY KEY,
                sort_order INTEGER NOT NULL,
                label_key TEXT NOT NULL
            )
            """
        )
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS menus (
                menu_key TEXT PRIMARY KEY,
                route_path TEXT NOT NULL,
                sort_order INTEGER NOT NULL,
                label_key TEXT NOT NULL
            )
            """
        )
        self.ensure_ui_text_schema()
        self.ensure_inventory_schema()
        self.ensure_categories_schema()
        self.ensure_product_combinations_schema()
        self.ensure_product_combination_items_schema()
        self.ensure_workflows_schema()
        self.ensure_workflow_steps_schema()
        self.ensure_workflow_runs_schema()
        self.ensure_workflow_run_steps_schema()
        self.ensure_equipment_connection_schema()
        self.ensure_attachment_schema()
        self.retire_equipment_settings_feature()

    def ensure_categories_schema(self) -> None:
        """Idempotent categories table create (shared TxId / isDisable / Remark)."""
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                TxId INTEGER PRIMARY KEY,
                CategoryGroup TEXT NOT NULL,
                CategoryCode TEXT NOT NULL,
                zh_TW TEXT NOT NULL,
                en TEXT NOT NULL,
                zh_CN TEXT NOT NULL,
                isDisable INTEGER NOT NULL DEFAULT 0,
                Remark TEXT NOT NULL DEFAULT '',
                UNIQUE (CategoryGroup, CategoryCode)
            )
            """
        )

    def ensure_inventory_schema(self) -> None:
        """Idempotent inventory table create (common TxId / isDisable / Remark)."""
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory (
                TxId INTEGER PRIMARY KEY,
                ItemCode TEXT NOT NULL DEFAULT '',
                ItemName TEXT NOT NULL,
                ItemNameEn TEXT NOT NULL,
                Category INTEGER NOT NULL,
                Brand TEXT NOT NULL DEFAULT '',
                Model TEXT NOT NULL DEFAULT '',
                SerialNo TEXT NOT NULL DEFAULT '',
                Quantity REAL,
                Unit TEXT NOT NULL DEFAULT '',
                Location TEXT NOT NULL DEFAULT '',
                dimensions TEXT NOT NULL DEFAULT '',
                version_scb TEXT,
                version_controller TEXT,
                version_servo TEXT,
                isDisable INTEGER NOT NULL DEFAULT 0,
                Remark TEXT NOT NULL DEFAULT ''
            )
            """
        )
        columns = self.table_column_names("inventory")
        for field in ("version_scb", "version_controller", "version_servo"):
            if field not in columns:
                self.store.execute(
                    f"ALTER TABLE inventory ADD COLUMN {field} TEXT"
                )

    def retire_equipment_settings_feature(self) -> None:
        """Remove retired equipment_settings feature artifacts from existing DBs.

        Idempotent and narrowly scoped: only menu_key / table_key / text_key values
        that belonged to equipment_settings. Custom non-seed menus are untouched.
        """
        self.store.execute(
            "DELETE FROM menus WHERE menu_key = ?",
            ("equipment_settings",),
        )
        obsolete_keys = (
            "menu_equipment_settings",
            "maint_table_equipment_settings",
            "field_site_no",
            "field_site_name",
            "field_ip_address",
            "field_port",
            "field_connection_mode",
            "field_controller_version",
            "field_servo_version",
            "field_scb_version",
            "field_payload_kg",
            "field_desc_site_no",
            "field_desc_site_name",
            "field_desc_ip_address",
            "field_desc_port",
            "field_desc_connection_mode",
            "field_desc_controller_version",
            "field_desc_servo_version",
            "field_desc_scb_version",
            "field_desc_payload_kg",
            "table_ui_btn_detect_network_ip",
            "table_ui_msg_detect_network_ip_empty",
            "table_ui_label_ip_source_local",
            "table_ui_label_ip_source_neighbor",
        )
        placeholders = ", ".join("?" for _ in obsolete_keys)
        self.store.execute(
            f"DELETE FROM ui_text WHERE text_key IN ({placeholders})",
            obsolete_keys,
        )
        layout_table = self.store.fetchone(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'ui_table_settings'
            """
        )
        if layout_table is not None:
            setting = self.store.fetchone(
                "SELECT TxId FROM ui_table_settings WHERE table_key = ?",
                ("equipment_settings",),
            )
            if setting is not None:
                self.store.execute(
                    "DELETE FROM ui_table_columns WHERE table_setting_id = ?",
                    (setting["TxId"],),
                )
                self.store.execute(
                    "DELETE FROM ui_table_settings WHERE TxId = ?",
                    (setting["TxId"],),
                )
        self.store.execute("DROP TABLE IF EXISTS equipment_settings")

    def ensure_equipment_connection_schema(self) -> None:
        """Idempotent per-physical-equipment connection settings (not equipment_settings)."""
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS equipment_connection (
                EquipmentTxId INTEGER PRIMARY KEY,
                DriverType TEXT NOT NULL,
                ConnectionMode TEXT NOT NULL,
                HostAddress TEXT NOT NULL,
                Remark TEXT NOT NULL DEFAULT '',
                CreatedAt TEXT NOT NULL,
                UpdatedAt TEXT NOT NULL
            )
            """
        )

    def ensure_attachment_schema(self) -> None:
        """Idempotent attachment table: register existing files under model root."""
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS attachment (
                TxId INTEGER PRIMARY KEY,
                InventoryId INTEGER NOT NULL,
                Path TEXT NOT NULL DEFAULT '',
                File TEXT NOT NULL,
                Type TEXT NOT NULL DEFAULT '',
                Remark TEXT NOT NULL DEFAULT '',
                isDisable INTEGER NOT NULL DEFAULT 0,
                CreatedAt TEXT,
                UpdatedAt TEXT
            )
            """
        )

    def ensure_product_combinations_schema(self) -> None:
        """Idempotent product_combinations table create."""
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS product_combinations (
                TxId INTEGER PRIMARY KEY,
                CombinationCode TEXT NOT NULL UNIQUE,
                CombinationName TEXT NOT NULL,
                CombinationNameEn TEXT,
                Description TEXT,
                Remark TEXT,
                isDisable INTEGER NOT NULL DEFAULT 0,
                CreatedAt TEXT,
                UpdatedAt TEXT
            )
            """
        )

    def ensure_product_combination_items_schema(self) -> None:
        """Idempotent product_combination_items table create."""
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS product_combination_items (
                TxId INTEGER PRIMARY KEY,
                CombinationTxId INTEGER NOT NULL,
                ItemId REAL NOT NULL,
                EquipmentTxId INTEGER NOT NULL,
                ItemRole TEXT,
                Qty INTEGER NOT NULL DEFAULT 1,
                Remark TEXT,
                isDisable INTEGER NOT NULL DEFAULT 0,
                CreatedAt TEXT,
                UpdatedAt TEXT,
                UNIQUE (CombinationTxId, EquipmentTxId),
                UNIQUE (CombinationTxId, ItemId)
            )
            """
        )

    def ensure_workflows_schema(self) -> None:
        """Idempotent workflows table create."""
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS workflows (
                TxId INTEGER PRIMARY KEY,
                WorkflowCode TEXT NOT NULL UNIQUE,
                WorkflowName TEXT NOT NULL,
                CombinationTxId INTEGER NOT NULL,
                Version INTEGER NOT NULL DEFAULT 1,
                Status TEXT NOT NULL DEFAULT 'draft',
                Remark TEXT,
                isDisable INTEGER NOT NULL DEFAULT 0,
                CreatedAt TEXT,
                UpdatedAt TEXT
            )
            """
        )

    def ensure_workflow_steps_schema(self) -> None:
        """Idempotent workflow_steps table create."""
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_steps (
                TxId INTEGER PRIMARY KEY,
                WorkflowTxId INTEGER NOT NULL,
                StepNo REAL NOT NULL,
                StepName TEXT NOT NULL,
                CombinationItemTxId INTEGER,
                ActionType TEXT NOT NULL,
                TargetKey TEXT,
                Parameters TEXT,
                CompletionCondition TEXT,
                TimeoutSec REAL,
                Remark TEXT,
                isDisable INTEGER NOT NULL DEFAULT 0,
                CreatedAt TEXT,
                UpdatedAt TEXT,
                UNIQUE (WorkflowTxId, StepNo)
            )
            """
        )

    def ensure_workflow_runs_schema(self) -> None:
        """Idempotent workflow_runs table create (virtual execution records)."""
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_runs (
                TxId INTEGER PRIMARY KEY,
                WorkflowTxId INTEGER NOT NULL,
                WorkflowCode TEXT NOT NULL,
                Mode TEXT NOT NULL DEFAULT 'virtual',
                Status TEXT NOT NULL DEFAULT 'idle',
                CurrentStepNo REAL,
                CurrentStepName TEXT,
                ProgressDone INTEGER NOT NULL DEFAULT 0,
                ProgressTotal INTEGER NOT NULL DEFAULT 0,
                ErrorMessage TEXT,
                StartedAt TEXT,
                FinishedAt TEXT,
                Remark TEXT,
                CreatedAt TEXT,
                UpdatedAt TEXT
            )
            """
        )

    def ensure_workflow_run_steps_schema(self) -> None:
        """Idempotent workflow_run_steps table create."""
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_run_steps (
                TxId INTEGER PRIMARY KEY,
                RunTxId INTEGER NOT NULL,
                WorkflowStepTxId INTEGER,
                StepNo REAL NOT NULL,
                StepName TEXT NOT NULL,
                ActionType TEXT NOT NULL,
                TargetKey TEXT,
                Status TEXT NOT NULL DEFAULT 'pending',
                ResultMessage TEXT,
                StartedAt TEXT,
                FinishedAt TEXT,
                Remark TEXT,
                CreatedAt TEXT,
                UpdatedAt TEXT
            )
            """
        )

    def ensure_ui_text_schema(self) -> None:
        exists = self.store.fetchone(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'ui_text'
            """
        )
        if exists is None:
            self.store.execute(
                """
                CREATE TABLE ui_text (
                    TxId INTEGER PRIMARY KEY,
                    text_key TEXT NOT NULL UNIQUE,
                    zh_TW TEXT NOT NULL,
                    en TEXT NOT NULL,
                    zh_CN TEXT NOT NULL,
                    isDisable INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            return

        columns = self.table_column_names("ui_text")
        if "TxId" in columns and "isDisable" in columns:
            return

        self.store.execute(
            """
            CREATE TABLE ui_text_migrated (
                TxId INTEGER PRIMARY KEY,
                text_key TEXT NOT NULL UNIQUE,
                zh_TW TEXT NOT NULL,
                en TEXT NOT NULL,
                zh_CN TEXT NOT NULL,
                isDisable INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        rows = self.store.fetchall(
            "SELECT text_key, zh_TW, en, zh_CN FROM ui_text ORDER BY text_key ASC"
        )
        for index, row in enumerate(rows, start=1):
            self.store.execute(
                """
                INSERT INTO ui_text_migrated (TxId, text_key, zh_TW, en, zh_CN, isDisable)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (index, row["text_key"], row["zh_TW"], row["en"], row["zh_CN"]),
            )
        self.store.execute("DROP TABLE ui_text")
        self.store.execute("ALTER TABLE ui_text_migrated RENAME TO ui_text")

    def ensure_seed_data(self) -> None:
        if self.store.count("languages") == 0:
            rows = load_json(resolve_path(self.config["seed_languages_path"]))
            self.store.executemany(
                "INSERT INTO languages (code, sort_order, label_key) VALUES (?, ?, ?)",
                [(item["code"], item["sort_order"], item["label_key"]) for item in rows],
            )
        self.ensure_seed_menus()
        rows = load_json(resolve_path(self.config["seed_ui_text_path"]))
        for item in rows:
            existing = self.store.fetchone(
                "SELECT text_key FROM ui_text WHERE text_key = ?",
                (item["text_key"],),
            )
            if existing is None:
                self.store.execute(
                    """
                    INSERT INTO ui_text (TxId, text_key, zh_TW, en, zh_CN, isDisable)
                    VALUES (?, ?, ?, ?, ?, 0)
                    """,
                    (
                        self.next_txid("ui_text"),
                        item["text_key"],
                        item["zh_TW"],
                        item["en"],
                        item["zh_CN"],
                    ),
                )
            else:
                self.store.execute(
                    """
                    UPDATE ui_text
                    SET zh_TW = ?, en = ?, zh_CN = ?
                    WHERE text_key = ?
                    """,
                    (
                        item["zh_TW"],
                        item["en"],
                        item["zh_CN"],
                        item["text_key"],
                    ),
                )
        self.ensure_seed_workflow_demo()
        self.cleanup_workflow_test_rows()

    def ensure_seed_workflow_demo(self) -> None:
        """Idempotent demo workflow + steps (data maintenance only)."""
        existing = self.store.fetchone(
            "SELECT TxId FROM workflows WHERE WorkflowCode = ?",
            ("WF-DEMO-001",),
        )
        combo = self.store.fetchone(
            """
            SELECT TxId FROM product_combinations
            WHERE isDisable = 0
            ORDER BY TxId ASC
            LIMIT 1
            """
        )
        if combo is None:
            return
        item = self.store.fetchone(
            """
            SELECT TxId FROM product_combination_items
            WHERE CombinationTxId = ? AND isDisable = 0
            ORDER BY ItemId ASC
            LIMIT 1
            """,
            (combo["TxId"],),
        )
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        remark = self.t("wf_seed_remark", "zh_TW")
        step_remark = self.t("wf_step_seed_remark", "zh_TW")
        # TargetKey maps to virtual demo carry_vertical_1_inplace phases (not live TCP).
        steps = (
            (10, "下降取料", "move", "demo1_descend", 0.8),
            (20, "夾取工件", "gripper", "demo1_grasp_close", 0.5),
            (30, "垂直提升", "move", "demo1_lift", 0.8),
            (40, "放回原位", "move", "demo1_place", 0.8),
            (50, "向上退出", "move", "demo1_retract", 0.6),
            (60, "返回待機", "end", "demo1_standby", None),
        )
        item_txid = None if item is None else item["TxId"]
        if existing is None:
            wf_txid = self.next_txid("workflows")
            self.store.execute(
                """
                INSERT INTO workflows (
                    TxId, WorkflowCode, WorkflowName, CombinationTxId,
                    Version, Status, Remark, isDisable, CreatedAt, UpdatedAt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    wf_txid,
                    "WF-DEMO-001",
                    "Demo 1 原位垂直取放",
                    combo["TxId"],
                    1,
                    "draft",
                    remark,
                    now,
                    now,
                ),
            )
            for step_no, step_name, action_type, target_key, timeout in steps:
                self.store.execute(
                    """
                    INSERT INTO workflow_steps (
                        TxId, WorkflowTxId, StepNo, StepName, CombinationItemTxId,
                        ActionType, TargetKey, Parameters, CompletionCondition,
                        TimeoutSec, Remark, isDisable, CreatedAt, UpdatedAt
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        self.next_txid("workflow_steps"),
                        wf_txid,
                        float(step_no),
                        step_name,
                        item_txid,
                        action_type,
                        target_key,
                        None,
                        None,
                        timeout,
                        step_remark,
                        now,
                        now,
                    ),
                )
            return

        wf_txid = int(existing["TxId"])
        self.store.execute(
            """
            UPDATE workflows
            SET Remark = ?, UpdatedAt = ?
            WHERE TxId = ?
            """,
            (remark, now, wf_txid),
        )
        for step_no, step_name, action_type, target_key, timeout in steps:
            row = self.store.fetchone(
                """
                SELECT TxId, TargetKey FROM workflow_steps
                WHERE WorkflowTxId = ? AND StepNo = ?
                """,
                (wf_txid, float(step_no)),
            )
            if row is None:
                self.store.execute(
                    """
                    INSERT INTO workflow_steps (
                        TxId, WorkflowTxId, StepNo, StepName, CombinationItemTxId,
                        ActionType, TargetKey, Parameters, CompletionCondition,
                        TimeoutSec, Remark, isDisable, CreatedAt, UpdatedAt
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        self.next_txid("workflow_steps"),
                        wf_txid,
                        float(step_no),
                        step_name,
                        item_txid,
                        action_type,
                        target_key,
                        None,
                        None,
                        timeout,
                        step_remark,
                        now,
                        now,
                    ),
                )
                continue
            self.store.execute(
                """
                UPDATE workflow_steps
                SET StepName = ?, ActionType = ?, TargetKey = ?,
                    TimeoutSec = ?, Remark = ?, UpdatedAt = ?
                WHERE TxId = ?
                """,
                (
                    step_name,
                    action_type,
                    target_key,
                    timeout,
                    step_remark,
                    now,
                    row["TxId"],
                ),
            )

    def cleanup_workflow_test_rows(self) -> None:
        """Remove disposable smoke-test workflows (not WF-DEMO-001)."""
        rows = self.store.fetchall(
            """
            SELECT TxId FROM workflows
            WHERE WorkflowCode = 'WF-TEST-TMP'
            """
        )
        for row in rows:
            self.store.execute(
                "DELETE FROM workflow_steps WHERE WorkflowTxId = ?",
                (row["TxId"],),
            )
            self.store.execute(
                "DELETE FROM workflows WHERE TxId = ?",
                (row["TxId"],),
            )

    def ensure_seed_menus(self) -> None:
        """Upsert menus from seed so new menus appear on existing databases."""
        rows = load_json(resolve_path(self.config["seed_menus_path"]))
        for item in rows:
            existing = self.store.fetchone(
                "SELECT menu_key FROM menus WHERE menu_key = ?",
                (item["menu_key"],),
            )
            if existing is None:
                self.store.execute(
                    """
                    INSERT INTO menus (menu_key, route_path, sort_order, label_key)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        item["menu_key"],
                        item["route_path"],
                        item["sort_order"],
                        item["label_key"],
                    ),
                )
            else:
                self.store.execute(
                    """
                    UPDATE menus
                    SET route_path = ?, sort_order = ?, label_key = ?
                    WHERE menu_key = ?
                    """,
                    (
                        item["route_path"],
                        item["sort_order"],
                        item["label_key"],
                        item["menu_key"],
                    ),
                )

    def ensure_prefs(self) -> None:
        fonts = self.get_fonts_config()
        if not self.prefs_path.is_file():
            first_language = self.store.fetchone(
                "SELECT code FROM languages ORDER BY sort_order ASC LIMIT 1"
            )
            if first_language is None:
                raise RuntimeError("languages table is empty")
            save_json(
                self.prefs_path,
                {
                    "language": first_language["code"],
                    "font": fonts["default_font"],
                    "font_size": fonts["default_font_size"],
                },
            )
            return
        prefs = load_json(self.prefs_path)
        required_keys = ("language", "font", "font_size")
        for key in required_keys:
            if key not in prefs:
                raise KeyError(f"Missing ui prefs key: {key}")

    def get_fonts_config(self) -> dict[str, Any]:
        fonts = load_json(self.fonts_path)
        for key in ("default_font_size", "default_font", "font_sizes", "fonts"):
            if key not in fonts:
                raise KeyError(f"Missing fonts.json key: {key}")
        return fonts

    def get_prefs(self) -> dict[str, Any]:
        prefs = load_json(self.prefs_path)
        language = prefs["language"]
        font = prefs["font"]
        font_size = prefs["font_size"]
        self.require_language(language)
        self.require_font(font)
        self.require_font_size(font_size)
        return {
            "language": language,
            "font": font,
            "font_size": font_size,
        }

    def save_prefs(self, language: str, font: str, font_size: int) -> dict[str, Any]:
        self.require_language(language)
        self.require_font(font)
        self.require_font_size(font_size)
        prefs = {
            "language": language,
            "font": font,
            "font_size": font_size,
        }
        save_json(self.prefs_path, prefs)
        return prefs

    def require_language(self, language: str) -> None:
        row = self.store.fetchone(
            "SELECT code FROM languages WHERE code = ?", (language,)
        )
        if row is None:
            raise ValueError(f"Unknown language: {language}")

    def require_font(self, font_id: str) -> None:
        fonts = self.get_fonts_config()
        if not any(item["id"] == font_id for item in fonts["fonts"]):
            raise ValueError(f"Unknown font: {font_id}")

    def require_font_size(self, font_size: int) -> None:
        fonts = self.get_fonts_config()
        if font_size not in fonts["font_sizes"]:
            raise ValueError(f"Unknown font size: {font_size}")

    def t(self, text_key: str, language: str | None = None) -> str:
        lang = language if language is not None else self.get_prefs()["language"]
        self.require_language(lang)
        row = self.store.fetchone(
            f"SELECT {lang} AS value FROM ui_text WHERE text_key = ?",
            (text_key,),
        )
        if row is None:
            raise KeyError(f"Missing ui_text key: {text_key}")
        value = row["value"]
        if value is None or value == "":
            raise ValueError(f"Empty ui_text value for key={text_key}, language={lang}")
        return value

    def get_languages(self, language: str | None = None) -> list[dict[str, str]]:
        lang = language if language is not None else self.get_prefs()["language"]
        rows = self.store.fetchall(
            "SELECT code, label_key FROM languages ORDER BY sort_order ASC"
        )
        if not rows:
            raise RuntimeError("languages table is empty")
        return [
            {"code": row["code"], "label": self.t(row["label_key"], lang)}
            for row in rows
        ]

    def get_menus(self, language: str | None = None) -> list[dict[str, str]]:
        lang = language if language is not None else self.get_prefs()["language"]
        rows = self.store.fetchall(
            """
            SELECT menu_key, route_path, label_key
            FROM menus
            ORDER BY sort_order ASC
            """
        )
        if not rows:
            raise RuntimeError("menus table is empty")
        return [
            {
                "menu_key": row["menu_key"],
                "route_path": row["route_path"],
                "label": self.t(row["label_key"], lang),
            }
            for row in rows
        ]

    def get_menu(self, menu_key: str, language: str | None = None) -> dict[str, str]:
        lang = language if language is not None else self.get_prefs()["language"]
        row = self.store.fetchone(
            """
            SELECT menu_key, route_path, label_key
            FROM menus
            WHERE menu_key = ?
            """,
            (menu_key,),
        )
        if row is None:
            raise KeyError(f"Unknown menu_key: {menu_key}")
        return {
            "menu_key": row["menu_key"],
            "route_path": row["route_path"],
            "label": self.t(row["label_key"], lang),
        }

    def get_font_options(self, language: str | None = None) -> list[dict[str, str]]:
        lang = language if language is not None else self.get_prefs()["language"]
        fonts = self.get_fonts_config()
        options = []
        for item in fonts["fonts"]:
            options.append(
                {
                    "id": item["id"],
                    "css_family": item["css_family"],
                    "label": self.t(item["label_key"], lang),
                }
            )
        return options

    def get_font_css_family(self, font_id: str) -> str:
        fonts = self.get_fonts_config()
        for item in fonts["fonts"]:
            if item["id"] == font_id:
                return item["css_family"]
        raise ValueError(f"Unknown font: {font_id}")

    def build_window_title(self, menu_key: str, language: str | None = None) -> str:
        menu = self.get_menu(menu_key, language)
        return f"{self.config['app_name']} {menu['label']}"

    def get_settings_tabs_config(self) -> dict[str, Any]:
        data = load_json(resolve_path(self.config["settings_tabs_path"]))
        if "hosts" in data:
            if not isinstance(data["hosts"], list):
                raise KeyError("settings_tabs.hosts must be a list")
            return data
        for key in ("host_menu_key", "tabs"):
            if key not in data:
                raise KeyError(f"Missing settings_tabs key: {key}")
        return {
            "hosts": [
                {
                    "host_menu_key": data["host_menu_key"],
                    "tabs": data["tabs"],
                }
            ]
        }

    def get_maint_tabs_for_menu(
        self, menu_key: str, language: str | None = None
    ) -> list[dict[str, str]]:
        lang = language if language is not None else self.get_prefs()["language"]
        settings_tabs = []
        for host in self.get_settings_tabs_config()["hosts"]:
            if host.get("host_menu_key") != menu_key:
                continue
            for tab in host.get("tabs", []):
                settings_tabs.append(
                    {
                        "tab_key": tab["tab_key"],
                        "table_key": tab["table_key"],
                        "label": self.t(tab["label_key"], lang),
                    }
                )
        return settings_tabs

    def get_table_ui_hosts_config(self) -> dict[str, Any]:
        data = load_json(resolve_path(self.config["table_ui_hosts_path"]))
        if "hosts" not in data or not isinstance(data["hosts"], list):
            raise KeyError("Missing table_ui_hosts key: hosts")
        return data

    def get_table_ui_for_menu(
        self, menu_key: str, language: str | None = None
    ) -> dict[str, Any] | None:
        lang = language if language is not None else self.get_prefs()["language"]
        for host in self.get_table_ui_hosts_config()["hosts"]:
            if host.get("menu_key") != menu_key:
                continue
            if "tabs" in host:
                tabs_config = host["tabs"]
                if not isinstance(tabs_config, list) or not tabs_config:
                    raise KeyError(
                        f"table_ui host tabs must be a non-empty list: {menu_key}"
                    )
                tabs = []
                for tab in tabs_config:
                    for key in ("tab_key", "table_key", "label_key"):
                        if key not in tab:
                            raise KeyError(
                                f"Missing table_ui tab key {key} for menu: {menu_key}"
                            )
                    tabs.append(
                        {
                            "tab_key": tab["tab_key"],
                            "table_key": tab["table_key"],
                            "label": self.t(tab["label_key"], lang),
                        }
                    )
                return {
                    "menu_key": host["menu_key"],
                    "table_key": tabs[0]["table_key"],
                    "tabs": tabs,
                }
            if "table_key" not in host:
                raise KeyError(f"Missing table_ui host table_key for menu: {menu_key}")
            return {
                "menu_key": host["menu_key"],
                "table_key": host["table_key"],
                "tabs": [],
            }
        return None

    def build_page_context(self, menu_key: str) -> dict[str, Any]:
        prefs = self.get_prefs()
        language = prefs["language"]
        fonts = self.get_fonts_config()

        def translate(text_key: str) -> str:
            return self.t(text_key, language)

        table_ui = self.get_table_ui_for_menu(menu_key, language)
        is_system_setting = menu_key == "system_setting"
        settings_tabs = []
        if table_ui is None:
            settings_tabs = self.get_maint_tabs_for_menu(menu_key, language)

        return {
            "app_name": self.config["app_name"],
            "version": self.config["version"],
            "prefs": prefs,
            "languages": self.get_languages(language),
            "menus": self.get_menus(language),
            "font_options": self.get_font_options(language),
            "font_sizes": fonts["font_sizes"],
            "font_css_family": self.get_font_css_family(prefs["font"]),
            "current_menu": self.get_menu(menu_key, language),
            "window_title": self.build_window_title(menu_key, language),
            "settings_tabs": settings_tabs,
            "table_ui": table_ui,
            "is_virtual_demo": menu_key == self.config["virtual_demo_menu_key"],
            "is_system_setting": is_system_setting,
            "is_workflows": bool(
                table_ui and table_ui.get("table_key") == "workflows"
            ),
            "t": translate,
        }

