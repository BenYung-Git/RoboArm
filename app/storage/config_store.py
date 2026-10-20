import json
from pathlib import Path
from typing import Any

from app.paths import CONFIG_PATH, PROJECT_ROOT


def load_app_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        raise FileNotFoundError(f"App config not found: {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    required_keys = (
        "app_name",
        "version",
        "default_storage",
        "sqlite_path",
        "fonts_json_path",
        "prefs_json_path",
        "seed_languages_path",
        "seed_menus_path",
        "seed_ui_text_path",
        "maint_tables_path",
        "settings_tabs_path",
        "virtual_demo_config_path",
        "virtual_demo_menu_key",
        "host",
        "port",
    )



    for key in required_keys:
        if key not in config:
            raise KeyError(f"Missing app config key: {key}")
    return config


def resolve_path(relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path
