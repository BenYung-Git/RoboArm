"""Read-only local/neighbor IPv4 discovery (no active scan, no SDK)."""

from __future__ import annotations

import re
import socket
import subprocess
from typing import Any


def _is_ipv4(value: str) -> bool:
    parts = value.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False


def _local_ipv4_addresses() -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    hostname = socket.gethostname()
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror:
        infos = []
    for info in infos:
        ip = info[4][0]
        if not _is_ipv4(ip) or ip.startswith("127."):
            continue
        found[ip] = {
            "ip": ip,
            "source": "local",
            "interface": hostname,
        }
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("8.8.8.8", 80))
            ip = probe.getsockname()[0]
            if _is_ipv4(ip) and not ip.startswith("127."):
                found.setdefault(
                    ip,
                    {"ip": ip, "source": "local", "interface": hostname},
                )
        finally:
            probe.close()
    except OSError:
        pass
    return list(found.values())


def _neighbor_ipv4_from_arp() -> list[dict[str, Any]]:
    try:
        completed = subprocess.run(
            ["arp", "-a"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Unable to read ARP/neighbor table: arp command not found"
        ) from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            "Unable to read ARP/neighbor table"
            + (f": {detail}" if detail else "")
        )
    output = completed.stdout or ""
    if not output.strip():
        raise RuntimeError("Unable to read ARP/neighbor table: empty output")
    found: dict[str, dict[str, Any]] = {}
    pattern = re.compile(
        r"\b(\d{1,3}(?:\.\d{1,3}){3})\b.*\b([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})\b"
    )
    for line in output.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        ip = match.group(1)
        if not _is_ipv4(ip) or ip.startswith("127."):
            continue
        found[ip] = {"ip": ip, "source": "neighbor", "interface": None}
    return list(found.values())


def detect_network_ips() -> list[dict[str, Any]]:
    """Return local + ARP neighbor IPv4 list. Raises if ARP cannot be read."""
    local_items = _local_ipv4_addresses()
    neighbor_items = _neighbor_ipv4_from_arp()
    merged: dict[str, dict[str, Any]] = {}
    for item in local_items:
        merged[item["ip"]] = item
    for item in neighbor_items:
        if item["ip"] not in merged:
            merged[item["ip"]] = item
    return sorted(merged.values(), key=lambda row: tuple(int(p) for p in row["ip"].split(".")))
