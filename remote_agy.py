"""Fetch Antigravity quota through its official read-only CLI over SSH.

No credential files or private endpoints are accessed by agentdeck. See
docs/ANTIGRAVITY.md for the provisional payload contract and validation limits.
"""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone

from config import AGY_HOST

HOST = AGY_HOST

# Keep the existing remote Python transport and installation search paths.
# Version-gate before /usage: older CLIs could interpret slash commands as prompts.
REMOTE = r'''
import os, re, subprocess, sys

env = dict(os.environ, PATH=os.path.expanduser("~/.local/bin") + ":/opt/homebrew/bin:" + os.environ.get("PATH", ""))
try:
    version = subprocess.run(["agy", "--version"], stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=10, env=env, check=True)
    match = re.fullmatch(r"(?:agy\s+)?v?(\d+)\.(\d+)\.(\d+)\s*", version.stdout.strip())
    if not match or tuple(map(int, match.groups())) < (1, 1, 11):
        sys.exit(1)
    result = subprocess.run(["agy", "-p", "/usage", "--output-format", "json"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=60, env=env, check=True)
    sys.stdout.write(result.stdout)
except (OSError, subprocess.SubprocessError, UnicodeError):
    sys.exit(1)
'''


@dataclass
class Bucket:
    group: str
    window: str  # "5h" | "weekly"
    remaining: float  # 0~1
    reset: datetime | None


def parse_quota(payload: object) -> list[Bucket] | None:
    """Parse the provisional groups/buckets contract, failing closed on drift.

    This shape still needs comparison with a real CLI response. Do not guess
    wrappers or reinterpret ordinary headless token-count `usage` as quota.
    Missing/disabled buckets are unavailable, never fabricated as zero.
    """
    if not isinstance(payload, dict) or "error" in payload:
        return None
    groups = payload.get("groups")
    if not isinstance(groups, list):
        return None
    out = []
    for group in groups:
        if not isinstance(group, dict):
            return None
        if group.get("disabled") is True or group.get("enabled") is False:
            continue
        name, buckets = group.get("displayName"), group.get("buckets")
        if not isinstance(name, str) or not name.strip() or not isinstance(buckets, list):
            return None
        for bucket in buckets:
            if not isinstance(bucket, dict):
                return None
            if bucket.get("disabled") is True or bucket.get("enabled") is False:
                continue
            remaining = bucket.get("remainingFraction")
            if remaining is None:
                continue
            if (isinstance(remaining, bool) or not isinstance(remaining, (int, float))
                    or not 0 <= remaining <= 1 or not math.isfinite(remaining)):
                return None
            window = bucket.get("window")
            if window not in ("5h", "weekly"):
                return None
            reset = bucket.get("resetTime")
            if reset is not None:
                if not isinstance(reset, str):
                    return None
                try:
                    reset = datetime.fromisoformat(reset.replace("Z", "+00:00"))
                    if reset.tzinfo is None:
                        return None
                    reset = reset.astimezone(timezone.utc)
                except (ValueError, OverflowError):
                    return None
            out.append(Bucket(name, window, float(remaining), reset))
    return out or None


def agy_quota() -> list[Bucket] | None:
    if not HOST:
        return None
    try:
        result = subprocess.run(
            ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
             HOST, "python3", "-"],
            input=REMOTE, capture_output=True, text=True, timeout=90,
            check=True,
        )
        return parse_quota(json.loads(result.stdout))
    except (OSError, subprocess.SubprocessError, ValueError, UnicodeError):
        return None


if __name__ == "__main__":
    for b in agy_quota() or []:
        print(b)
