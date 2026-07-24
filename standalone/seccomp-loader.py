#!/usr/bin/env python3
"""
terminal-jail seccomp loader — T9.5.

Applies the seccomp BPF filter to the calling process, then exec's the
provided command.  Designed to be invoked from the standalone CLI when
``--seccomp`` is requested.

Usage:
  seccomp-loader.py [--] <command> [args...]

Environment:
  TERMINAL_JAIL_SECCOMP  — truthy (1/true/yes/on) enables the filter.
                            Default disabled.  The standalone CLI sets
                            this before invoking the loader.

Exit:
  If the filter is applied, the process exec's the command and inherits
  its exit code.
  If the filter cannot be applied, a warning is written to stderr and
  the command is exec'd without seccomp.
"""
from __future__ import annotations

import os
import sys


def _setup_path() -> None:
    """Add the plugin directory to sys.path so we can import terminal_jail."""
    # The plugin lives at plugin/terminal_jail/ relative to the repo root.
    # This script lives at standalone/; the repo root is one level up.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    plugin_dir = os.path.join(repo_root, "plugin")
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)


def _main() -> None:
    _setup_path()

    from terminal_jail.seccomp import seccomp_enabled_from_environment, try_apply

    if seccomp_enabled_from_environment():
        result = try_apply()
        if not result.applied:
            print(
                f"terminal-jail: seccomp not applied ({result.reason}); "
                f"running without seccomp",
                file=sys.stderr,
            )

    args = sys.argv[1:]
    if not args:
        print("Usage: seccomp-loader.py [--] <command> [args...]", file=sys.stderr)
        sys.exit(2)

    os.execvp(args[0], args)


if __name__ == "__main__":
    _main()
