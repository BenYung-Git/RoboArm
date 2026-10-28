"""
Manual probe for jkrc.get_controller_ip() (no-arg call only).

Default: do NOT search the network. Print usage and exit.

Real probe (network side-effect possible):

  python tools/jaka_probe_controller_ip.py --run-search

Options:
  --run-search     Explicitly enable the real SDK call in a worker process.
  --timeout SEC    Parent timeout (default 30). Worker is killed on expiry.
  --sim SCENARIO   Offline simulation only: ok | type_error | nonzero
                   (does not call SDK search).

Constraints:
  - Uses the configured JAKA Python + project vendor SDK via the existing
    process channel.
  - Calls exactly jkrc.get_controller_ip() with no arguments.
  - Does not construct RC, login, or operate equipment.
  - On TypeError: records and stops (no alternate signature retry).
  - Does not save results or change equipment / verified flags.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.jaka.protocol import PROBE_GET_CONTROLLER_IP_TIMEOUT_SEC
from app.services.equipment_connection_service import EquipmentConnectionService
from app.services.jaka_bridge_service import JakaBridgeService
from app.services.ui_service import UiService

NETWORK_WARNING = (
    "WARNING: --run-search will start a JAKA worker that imports jkrc and calls "
    "jkrc.get_controller_ip() with no arguments. Per SDK Manual V2.1.11 §4.1.10 "
    "this may perform a network-segment controller search. "
    "No RC/login is used; results are printed only and not saved."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Probe jkrc.get_controller_ip() via the RoboArm JAKA worker channel. "
            "Default does not run a search."
        )
    )
    parser.add_argument(
        "--run-search",
        action="store_true",
        help="Explicitly run the real no-arg get_controller_ip() probe (network side-effect).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=PROBE_GET_CONTROLLER_IP_TIMEOUT_SEC,
        help=f"Parent timeout in seconds (default {PROBE_GET_CONTROLLER_IP_TIMEOUT_SEC}).",
    )
    parser.add_argument(
        "--sim",
        choices=("ok", "type_error", "nonzero"),
        default=None,
        help="Run an offline simulated probe response instead of a real SDK call.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.sim is not None and args.run_search:
        print(
            "Refuse: --sim and --run-search cannot be combined.",
            file=sys.stderr,
        )
        return 2

    if not args.run_search and args.sim is None:
        parser.print_help()
        print()
        print(
            "No search performed (default). "
            "Pass --run-search only after confirming a suitable test network, "
            "or use --sim for offline checks."
        )
        print(NETWORK_WARNING)
        return 0

    ui = UiService()
    bridge = JakaBridgeService(ui, EquipmentConnectionService(ui))

    if args.sim is not None:
        result = bridge.run_sim_probe_get_controller_ip(
            args.sim, timeout_sec=float(args.timeout)
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") or result.get("error_code") == "probe_type_error" else 1

    print(NETWORK_WARNING, file=sys.stderr)
    result = bridge.run_probe_get_controller_ip(timeout_sec=float(args.timeout))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # TypeError is a successful probe of the signature (recorded); exit 1 to signal failure path.
    if result.get("error_code") == "probe_type_error":
        return 1
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
