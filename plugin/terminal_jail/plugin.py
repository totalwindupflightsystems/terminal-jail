from __future__ import annotations

import logging
import os
import shlex
import shutil
from typing import Final

LOGGER: Final[logging.Logger] = logging.getLogger("terminal_jail")

_TRUTHY: Final[set[str]] = {"1", "true", "yes", "on"}
_FALSY: Final[set[str]] = {"", "0", "false", "no", "off"}
_DEFAULT_MAX_COMMAND_BYTES: Final[int] = 131072


def _configure_logger() -> None:
    raw = os.environ.get("HERMES_TERMINAL_JAIL_LOG_LEVEL", "WARNING")
    try:
        level = getattr(logging, raw.upper(), None)
        if not isinstance(level, int):
            raise AttributeError
    except AttributeError:
        # Invalid level name — stay at WARNING and warn once.
        LOGGER.warning(
            "terminal-jail: invalid HERMES_TERMINAL_JAIL_LOG_LEVEL value %r; "
            "using WARNING",
            raw,
        )
        level = logging.WARNING
    LOGGER.setLevel(level)


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


def _max_command_bytes_from_environment() -> int:
    raw = os.environ.get("HERMES_TERMINAL_JAIL_MAX_COMMAND_BYTES")
    if raw is None:
        return _DEFAULT_MAX_COMMAND_BYTES
    stripped = raw.strip()
    try:
        value = int(stripped, 10)
    except (ValueError, TypeError):
        LOGGER.warning(
            "terminal-jail: invalid HERMES_TERMINAL_JAIL_MAX_COMMAND_BYTES "
            "value %r; using default %d",
            raw,
            _DEFAULT_MAX_COMMAND_BYTES,
        )
        return _DEFAULT_MAX_COMMAND_BYTES
    if value <= 0:
        LOGGER.warning(
            "terminal-jail: HERMES_TERMINAL_JAIL_MAX_COMMAND_BYTES must be "
            "positive (got %d); using default %d",
            value,
            _DEFAULT_MAX_COMMAND_BYTES,
        )
        return _DEFAULT_MAX_COMMAND_BYTES
    return value


def transform_command(command: str) -> str:
    """Transform a generic Hermes terminal command into a PID-namespace command."""
    _configure_logger()

    # Step 2: type guard — Hermes always provides str, but guard anyway.
    if not isinstance(command, str):
        LOGGER.warning(
            "terminal-jail: transform_command received non-str input; "
            "returning unchanged"
        )
        return command

    # Step 3: empty / whitespace-only → pass through silently.
    if command == "" or not command.strip():
        return command

    # Step 4: disabled?
    if not _enabled_from_environment():
        return command

    # Step 5: locate unshare.
    unshare_path = _unshare_executable_from_environment()
    if unshare_path is None:
        LOGGER.warning(
            "terminal-jail: unshare executable not found; "
            "PID namespace isolation unavailable, running command without jail"
        )
        return command

    # Step 6: build wrapped command.
    try:
        prefix = (
            f"{shlex.quote(unshare_path)} --pid --fork --mount-proc "
            "--kill-child=SIGKILL bash -c "
        )
        wrapped = prefix + shlex.quote(command)
    except Exception:
        LOGGER.warning(
            "terminal-jail: failed to build wrapped command",
            exc_info=True,
        )
        return command

    # Step 7–8: byte-budget check.
    try:
        budget = _max_command_bytes_from_environment()
        if len(wrapped.encode("utf-8")) > budget:
            LOGGER.warning(
                "terminal-jail: wrapped command exceeds byte budget "
                "(%d bytes); running command without jail",
                budget,
            )
            return command
    except Exception:
        LOGGER.warning(
            "terminal-jail: byte-budget check failed",
            exc_info=True,
        )
        return command

    # Step 9: return wrapped.
    return wrapped


def transform_exec_command(command: str) -> str:
    """Transform a Hermes terminal exec-path command into a PID-namespace command."""
    return transform_command(command)
