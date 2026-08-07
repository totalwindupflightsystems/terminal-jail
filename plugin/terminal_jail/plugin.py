from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from typing import Final

LOGGER: Final[logging.Logger] = logging.getLogger("terminal_jail")

_TRUTHY: Final[set[str]] = {"1", "true", "yes", "on"}
_FALSY: Final[set[str]] = {"", "0", "false", "no", "off"}


@dataclass
class Metrics:
    """Observability counters for terminal-jail plugin (T7.1-T7.4)."""

    commands_wrapped: int = 0
    commands_wrapped_user_ns: int = 0
    commands_passed_disabled: int = 0
    commands_passed_no_unshare: int = 0
    jail_crashes: int = 0
    byte_budget_rejections: int = 0
    wrap_time_ns_total: int = 0
    wrap_count: int = 0
    perf_regression_alert_count: int = 0


_metrics: Metrics = Metrics()


def get_metrics() -> Metrics:
    """Return the current metrics snapshot (for tests and observability)."""
    return _metrics


def reset_metrics() -> None:
    """Reset all metrics counters to zero (for tests)."""
    global _metrics
    _metrics = Metrics()


def _enabled_from_environment() -> bool:
    raw = os.environ.get("HERMES_TERMINAL_JAIL_ENABLED", "true")
    value = raw.strip().lower()
    if value in _FALSY:
        return False
    if value in _TRUTHY:
        return True
    # Unrecognised non-empty value → fail closed for config, open for command.
    LOGGER.warning(
        "terminal-jail: unrecognised value %r for "
        "HERMES_TERMINAL_JAIL_ENABLED; disabling jail",
        raw,
    )
    return False


def _unshare_executable_from_environment() -> str | None:
    raw = os.environ.get("HERMES_TERMINAL_JAIL_COMMAND", "unshare")
    configured = raw.strip()
    if not configured:
        LOGGER.warning(
            "terminal-jail: HERMES_TERMINAL_JAIL_COMMAND is empty; "
            "PID namespace isolation unavailable"
        )
        return None
    if "\x00" in configured:
        LOGGER.warning(
            "terminal-jail: HERMES_TERMINAL_JAIL_COMMAND contains NUL; "
            "PID namespace isolation unavailable"
        )
        return None
    # Shell whitespace check — reject values containing spaces or tabs.
    if any(c in configured for c in " \t"):
        LOGGER.warning(
            "terminal-jail: HERMES_TERMINAL_JAIL_COMMAND %r contains "
            "shell whitespace; refusing unsafe value",
            configured,
        )
        return None
    return shutil.which(configured)
