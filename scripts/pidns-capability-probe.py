#!/usr/bin/env python3
"""Classify whether this host can run bare-mode PID-namespace containment.

The E2E battery uses this probe to label each run FULL or DEGRADED
(TJ-GAP-042): a battery must never report ALL GREEN without having actually
verified the PID-namespace layer.

- FULL: bare mode (./standalone/terminal-jail true) succeeds — the host can
  create the PID namespace, so bare-mode containment tests actually run.
- DEGRADED: bare mode exits 2 with the wrapper's degradation message
  (TJ-GAP-034 fail-closed contract naming --user); the host refuses
  unprivileged PID namespace creation and bare-mode tests must skip.
- UNKNOWN: anything else (missing wrapper, timeouts, unexpected output).

Always exits 0: this is a classifier for the battery, not a gate.

Usage:
    python3 scripts/pidns-capability-probe.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CLI = _PROJECT_ROOT / "standalone" / "terminal-jail"

# The fail-closed degradation message (TJ-GAP-034) names the fallback.
_DEGRADATION_MARKERS = ("namespace creation failed", "try --user")


def _classify() -> str:
    try:
        result = subprocess.run(
            [str(_CLI), "true"],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except FileNotFoundError:
        return f"UNKNOWN: {_CLI} not found"
    except subprocess.TimeoutExpired:
        return "UNKNOWN: probe timed out after 15s"

    if result.returncode == 0:
        return "FULL"
    if result.returncode == 2 and any(
        marker in result.stderr for marker in _DEGRADATION_MARKERS
    ):
        return "DEGRADED"
    return (
        f"UNKNOWN: rc={result.returncode}, "
        f"stderr={result.stderr.strip()!r}"
    )


def main() -> None:
    print(_classify())


if __name__ == "__main__":
    main()
