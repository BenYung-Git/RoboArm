"""
Manual JAKA SDK diagnostic via the host process channel.

Usage (from project root, host venv is fine — it only launches the configured
JAKA Python worker):

  python tools/jaka_sdk_diag.py

Does not search controllers, does not login, does not leave DB changes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.equipment_connection_service import EquipmentConnectionService
from app.services.jaka_bridge_service import JakaBridgeService
from app.services.ui_service import UiService


def main() -> int:
    ui = UiService()
    bridge = JakaBridgeService(ui, EquipmentConnectionService(ui))
    result = bridge.run_sdk_diag()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
