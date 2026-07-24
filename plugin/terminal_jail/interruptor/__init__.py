"""
terminal-jail interruptor — Bash command firewall.

Sits between the LLM and shell execution, evaluating every command against
a rule engine. Entry point: ``intercept()``.
"""

from __future__ import annotations

from .parser import (
    Segment,
    SegmentType,
    parse_command,
)
from .config import Config
from .rules import RuleSet, RuleLoader
from .matcher import Matcher
from .decider import Decider

__all__ = [
    "intercept",
    "InterceptResult",
    "Action",
    "Segment",
    "SegmentType",
    "Token",
    "TokenType",
    "parse_command",
    "Config",
    "RuleSet",
    "RuleLoader",
    "Matcher",
    "Decider",
]

from .types import Action, InterceptResult


def intercept(command: str, *, config: Config | None = None) -> InterceptResult:
    """Evaluate a command against all rules and return a decision.

    Args:
        command: The raw shell command string to evaluate.
        config: Runtime configuration. If omitted, loaded from env vars.

    Returns:
        An InterceptResult with the action to take and metadata.
    """
    if config is None:
        config = Config.from_environ()

    # Disabled mode → pass through
    if config.mode == "disabled":
        return InterceptResult(action=Action.ALLOW, command=command)

    # Empty command → pass through
    stripped = command.strip()
    if not stripped:
        return InterceptResult(action=Action.ALLOW, command=command)

    # Parse the command into segments
    segments = parse_command(stripped)
    if not segments:
        # Unparseable → pass through with warning
        return InterceptResult(action=Action.ALLOW, command=command)

    # Evaluate each segment through the decider
    decider = Decider(config)
    result = decider.evaluate(segments, command)

    # Warn mode → override BLOCK to ALLOW
    if config.mode == "warn" and result.action == Action.BLOCK:
        return InterceptResult(
            action=Action.ALLOW,
            command=command,
            reason=f"[WARN MODE] Would have blocked: {result.reason}",
        )

    return result
