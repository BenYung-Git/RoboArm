from typing import Any

from app.storage.config_store import load_app_config, resolve_path
from app.storage.json_store import load_json, save_json
from app.storage.sqlite_store import SqliteStore


class UiService:
    def __init__(self) -> None:
        self.config = load_app_config()
        if self.config["default_storage"] != "sqlite3":
            raise ValueError(
                f"Unsupported default_storage: {self.config['default_storage']}"
            )
        self.store = SqliteStore(resolve_path(self.config["sqlite_path"]))
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
        if self.store.count("menus") == 0:
            rows = load_json(resolve_path(self.config["seed_menus_path"]))
            self.store.executemany(
                """
                INSERT INTO menus (menu_key, route_path, sort_order, label_key)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        item["menu_key"],
                        item["route_path"],
                        item["sort_order"],
                        item["label_key"],
                    )
                    for item in rows
                ],
            )
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
        for key in ("host_menu_key", "tabs"):
            if key not in data:
                raise KeyError(f"Missing settings_tabs key: {key}")
        return data

    def build_page_context(self, menu_key: str) -> dict[str, Any]:
        prefs = self.get_prefs()
        language = prefs["language"]
        fonts = self.get_fonts_config()
        settings_tabs_config = self.get_settings_tabs_config()

        def translate(text_key: str) -> str:
            return self.t(text_key, language)

        settings_tabs = []
        if menu_key == settings_tabs_config["host_menu_key"]:
            for tab in settings_tabs_config["tabs"]:
                settings_tabs.append(
                    {
                        "tab_key": tab["tab_key"],
                        "table_key": tab["table_key"],
                        "label": self.t(tab["label_key"], language),
                    }
                )

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
            "is_virtual_demo": menu_key == self.config["virtual_demo_menu_key"],
            "t": translate,
        }

