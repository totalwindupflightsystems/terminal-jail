from __future__ import annotations

from .plugin import transform_command, transform_exec_command

__manifest__ = {
    "name": "terminal-jail",
    "version": "0.1.0",
    "description": "Wrap Hermes terminal commands in a Linux PID namespace using unshare.",
    "hooks": {
        "terminal.command.transform": transform_command,
        "terminal.command.transform.exec": transform_exec_command,
    },
}

hooks = __manifest__["hooks"]

__all__ = [
    "__manifest__",
    "hooks",
    "transform_command",
    "transform_exec_command",
]
