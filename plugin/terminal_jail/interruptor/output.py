"""Output formatting for the interruptor.

Provides box-drawing formatted output for blocked commands and sandbox
notices. Supports configurable theme (box-drawing vs plain ASCII).
"""

from __future__ import annotations

from .types import InterceptResult

# Box-drawing characters
_BOX = {
    "tl": "╔", "tr": "╗", "bl": "╚", "br": "╝",
    "h": "═", "v": "║",
}

_ASCII = {
    "tl": "+", "tr": "+", "bl": "+", "br": "+",
    "h": "-", "v": "|",
}

# 80-char width
_BOX_WIDTH = 66
_W = _BOX_WIDTH - 2  # content width inside borders


def _rule_line(chars: dict[str, str], left: str, right: str) -> str:
    """Build a horizontal rule line."""
    return f"{left}{chars['h'] * _BOX_WIDTH}{right}"


def _content_line(chars: dict[str, str], content: str, end: str = "") -> str:
    """Build a content line with vertical bars at each end."""
    # Strip ANSI-like content to measure visible width
    visible = len(content) if "\x1b" not in content else len(content)
    padding = _W - visible - len(end)
    if padding < 0:
        padding = 0
    return f"{chars['v']} {content}{' ' * padding}{end}{chars['v']}"


def format_blocked(result: InterceptResult, *, ascii: bool = False) -> str:
    """Format a blocked-command output box."""
    chars = _ASCII if ascii else _BOX
    title = f"COMMAND BLOCKED — {result.rule_id or 'unknown'}"
    msg = result.reason or "Command blocked by security policy."

    lines = [
        _rule_line(chars, chars["tl"], chars["tr"]),
        _content_line(chars, title),
        _rule_line(chars, f"{chars['v']}{chars['h']}", f"{chars['h']}{chars['v']}"),
        _content_line(chars, msg[:60]),
        _content_line(chars, ""),
        _content_line(chars, f"Command: {result.command[:60]}"),
        _content_line(chars, f"Rule: {result.rule_id or 'N/A'}"),
        _rule_line(chars, chars["bl"], chars["br"]),
    ]
    return "\n".join(lines)


def format_sandbox_notice(rule_id: str, *, ascii: bool = False) -> str:
    """Format a sandbox notice."""
    return f"[terminal-jail] Sandbox: running in isolated namespace ({rule_id})"


def format_modified_notice(original: str, modified: str, *, ascii: bool = False) -> str:
    """Format a command modification notice."""
    return f"[terminal-jail] Modified: {original[:40]}... → {modified[:40]}..."
