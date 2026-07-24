"""Core types for the interruptor — shared across all modules."""

from __future__ import annotations


class Action:
    """Possible actions the interruptor can take after evaluating a command."""

    ALLOW = "allow"
    BLOCK = "block"
    MODIFY = "modify"
    WARN = "warn"
    LOG = "log"
    SANDBOX = "sandbox"


class InterceptResult:
    """Result of evaluating a command against the rule engine."""

    __slots__ = ("action", "command", "modified", "reason", "rule_id")

    def __init__(
        self,
        action: str = Action.ALLOW,
        command: str = "",
        modified: str | None = None,
        rule_id: str | None = None,
        reason: str = "",
    ) -> None:
        self.action = action
        self.command = command
        self.modified = modified
        self.rule_id = rule_id
        self.reason = reason

    def __repr__(self) -> str:
        return (
            f"InterceptResult(action={self.action!r}, "
            f"rule_id={self.rule_id!r}, reason={self.reason!r})"
        )
