"""Rule evaluation engine for the interruptor.

Evaluates parsed command segments against built-in and user-defined rules
in priority order. Algorithm:

1. Check against CRITICAL blocklist (always first)
2. Check against ALLOW list (skip further eval if matched)
3. Check against AUTO-SANDBOX patterns (wrap in unshare)
4. Evaluate user-defined rules in priority order
"""

from __future__ import annotations

import re
from typing import Any

from .parser import Segment, SegmentType
from .matcher import Matcher, MatchResult
from .config import Config
from .blocklist import BUILTIN_BLOCKLIST
from .allowlist import BUILTIN_ALLOWLIST
from .sandbox import BUILTIN_SANDBOX
from .types import Action, InterceptResult


class Decider:
    """Evaluates commands against the full rule set.

    Applies rules in the correct precedence order:
    1. Critical blocklist (always evaluated first)
    2. Allowlist (skip further evaluation if matched)
    3. Auto-sandbox (wrap in unshare)
    4. User-defined rules
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.matcher = Matcher()

    def evaluate(self, segments: list[Segment], original: str) -> InterceptResult:
        """Evaluate all segments of a command through the rule engine.

        Args:
            segments: Parsed command segments.
            original: The original command string.

        Returns:
            An InterceptResult with the final action decision.
        """
        if not segments:
            return InterceptResult(action=Action.ALLOW, command=original)

        # Check the full command against blocklist first (catches pipe chains)
        full_segment = Segment(
            type=SegmentType.SIMPLE,
            tokens=[],
            raw=original,
            pos=0,
        )
        for rule in BUILTIN_BLOCKLIST:
            match_result = self.matcher.match_segment(full_segment, rule.match)
            if match_result:
                return InterceptResult(
                    action=Action.BLOCK,
                    command=original,
                    rule_id=rule.id,
                    reason=rule.block_message,
                )

        # Then check each segment individually
        modified_segments: list[str] = []
        any_modified = False

        for segment in segments:
            result = self._evaluate_segment(segment)
            if result.action == Action.BLOCK:
                return result
            if result.action in (Action.MODIFY, Action.SANDBOX):
                any_modified = True
                modified_segments.append(result.modified or segment.raw)
            elif result.action == Action.ALLOW:
                modified_segments.append(segment.raw)
            else:
                # WARN / LOG — allow through
                modified_segments.append(segment.raw)

        if any_modified:
            modified_cmd = " ".join(modified_segments)
            return InterceptResult(
                action=Action.MODIFY,
                command=original,
                modified=modified_cmd,
                reason="Command modified by auto-sandbox",
            )

        return InterceptResult(action=Action.ALLOW, command=original)

    def _evaluate_segment(self, segment: Segment) -> InterceptResult:
        """Evaluate a single command segment against all rule layers."""
        raw = segment.raw

        # Layer 1: Critical blocklist — always evaluated first
        for rule in BUILTIN_BLOCKLIST:
            match_result = self.matcher.match_segment(segment, rule.match)
            if match_result:
                return InterceptResult(
                    action=Action.BLOCK,
                    command=raw,
                    rule_id=rule.id,
                    reason=rule.block_message,
                )

        # Layer 2: Allowlist — if matched, skip further evaluation
        for rule in BUILTIN_ALLOWLIST:
            match_result = self.matcher.match_segment(segment, rule.match)
            if match_result:
                return InterceptResult(action=Action.ALLOW, command=raw)

        # Layer 3: Auto-sandbox — wrap in unshare
        for rule in BUILTIN_SANDBOX:
            match_result = self.matcher.match_segment(segment, rule.match)
            if match_result:
                modified = f"unshare --user --pid --fork --kill-child=SIGKILL bash -c {_escape_for_shell(raw)}"
                return InterceptResult(
                    action=Action.MODIFY,
                    command=raw,
                    modified=modified,
                    rule_id=rule.id,
                    reason=f"Auto-sandbox: wrapped command in namespace isolation",
                )

        # Layer 4: User-defined rules would go here (loaded from RuleSet)
        # Not yet implemented — this tick only builds the core engine.

        return InterceptResult(action=Action.ALLOW, command=raw)


def _escape_for_shell(cmd: str) -> str:
    """Escape a command string for shell embedding.

    Uses single-quote wrapping with proper handling of embedded quotes.
    """
    # Replace single quotes with '\'' sequence
    escaped = cmd.replace("'", "'\\''")
    return f"'{escaped}'"
