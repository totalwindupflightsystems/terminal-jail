"""Pattern matching engine for the interruptor.

Supports 9 match types: pattern, command, pipeline, subcommand, path,
composite, syscall, network, heredoc.
"""

from __future__ import annotations

import re
from typing import Any

from .parser import Segment, SegmentType, is_sensitive_path


class MatchResult:
    """Result of a pattern match attempt."""

    __slots__ = ("matched", "matched_by", "details")

    def __init__(
        self,
        matched: bool = False,
        matched_by: str = "",
        details: str = "",
    ) -> None:
        self.matched = matched
        self.matched_by = matched_by
        self.details = details

    def __bool__(self) -> bool:
        return self.matched

    def __repr__(self) -> str:
        return (
            f"MatchResult(matched={self.matched}, "
            f"matched_by={self.matched_by!r})"
        )


class Matcher:
    """Matches parsed commands against rule match criteria."""

    def match_segment(self, segment: Segment, match_def: dict[str, Any]) -> MatchResult:
        """Check if a segment matches the given match definition.

        Args:
            segment: The parsed command segment to check.
            match_def: The match criteria from a rule (type + optional fields).

        Returns:
            MatchResult with match status and details.
        """
        match_type = match_def.get("type", "pattern")

        dispatch = {
            "pattern": self._match_pattern,
            "command": self._match_command,
            "pipeline": self._match_pipeline,
            "subcommand": self._match_subcommand,
            "path": self._match_path,
            "composite": self._match_composite,
            "syscall": self._match_syscall,
            "network": self._match_network,
            "heredoc": self._match_heredoc,
        }

        handler = dispatch.get(match_type)
        if handler is None:
            return MatchResult()

        return handler(segment, match_def)

    def _match_pattern(self, segment: Segment, match_def: dict[str, Any]) -> MatchResult:
        """Match against a regex pattern."""
        pattern_str = match_def.get("pattern", "") or match_def.get("regex", "")
        if not pattern_str:
            return MatchResult()

        try:
            regex = re.compile(pattern_str, re.IGNORECASE)
        except re.error:
            return MatchResult()

        if regex.search(segment.raw):
            return MatchResult(
                matched=True,
                matched_by="pattern",
                details=f"Pattern '{pattern_str}' matched '{segment.raw}'",
            )
        return MatchResult()

    def _match_command(self, segment: Segment, match_def: dict[str, Any]) -> MatchResult:
        """Match against the top-level command (first word)."""
        cmd_name = match_def.get("command", "")
        if not cmd_name:
            return MatchResult()

        first_word = segment.raw.split()[0].lower() if segment.raw else ""
        return MatchResult(
            matched=first_word == cmd_name.lower(),
            matched_by="command" if first_word == cmd_name.lower() else "",
            details=(
                f"Command '{cmd_name}' matched '{first_word}'"
                if first_word == cmd_name.lower()
                else ""
            ),
        )

    def _match_pipeline(self, segment: Segment, match_def: dict[str, Any]) -> MatchResult:
        """Match against pipeline segments."""
        if segment.type != SegmentType.PIPE:
            # For simple commands with pipe operators, check the raw text
            if "|" in segment.raw:
                parts = [p.strip() for p in segment.raw.split("|")]
                return self._check_pipeline_parts(parts, match_def)
            return MatchResult()

        # For pipe-type segments, split by pipe
        parts = [p.strip() for p in segment.raw.split("|")]
        return self._check_pipeline_parts(parts, match_def)

    def _check_pipeline_parts(
        self, parts: list[str], match_def: dict[str, Any]
    ) -> MatchResult:
        """Check pipeline parts against a pattern."""
        pattern_str = match_def.get("pattern", "")
        if not pattern_str:
            return MatchResult()

        try:
            regex = re.compile(pattern_str, re.IGNORECASE)
        except re.error:
            return MatchResult()

        for part in parts:
            if regex.search(part):
                return MatchResult(
                    matched=True,
                    matched_by="pipeline",
                    details=f"Pipeline part '{part}' matched '{pattern_str}'",
                )
        return MatchResult()

    def _match_subcommand(self, segment: Segment, match_def: dict[str, Any]) -> MatchResult:
        """Match against subcommands (e.g., git push --force)."""
        words = segment.raw.split()
        subcmd = match_def.get("subcommand", "")
        parent = match_def.get("parent", "")

        if not subcmd:
            return MatchResult()

        if parent and (not words or words[0].lower() != parent.lower()):
            return MatchResult()

        # Check if any word matches the subcommand
        for word in words:
            if word.lower() == subcmd.lower():
                return MatchResult(
                    matched=True,
                    matched_by="subcommand",
                    details=f"Subcommand '{subcmd}' found in '{segment.raw}'",
                )

        return MatchResult()

    def _match_path(self, segment: Segment, match_def: dict[str, Any]) -> MatchResult:
        """Match against file paths in arguments."""
        path_pattern = match_def.get("path", "")
        if not path_pattern:
            # Default: check for sensitive paths
            words = segment.raw.split()
            for word in words:
                if "/" in word and is_sensitive_path(word):
                    return MatchResult(
                        matched=True,
                        matched_by="path",
                        details=f"Sensitive path '{word}' detected",
                    )
            return MatchResult()

        try:
            regex = re.compile(path_pattern, re.IGNORECASE)
        except re.error:
            return MatchResult()

        for word in segment.raw.split():
            if "/" in word and regex.search(word):
                return MatchResult(
                    matched=True,
                    matched_by="path",
                    details=f"Path '{word}' matched '{path_pattern}'",
                )
        return MatchResult()

    def _match_composite(self, segment: Segment, match_def: dict[str, Any]) -> MatchResult:
        """Match composite AND/OR/NOT conditions."""
        conditions = match_def.get("conditions", [])
        operator = match_def.get("operator", "and").lower()
        not_condition = match_def.get("not", "")

        if not conditions and not not_condition:
            return MatchResult()

        # Check NOT condition first
        if not_condition:
            not_match = self._match_simple(segment, not_condition)
            if not_match.matched:
                return MatchResult()

        if not conditions:
            return MatchResult()

        results = [
            self._match_simple(segment, cond)
            for cond in conditions
        ]

        if operator == "and":
            if all(results):
                return MatchResult(
                    matched=True,
                    matched_by="composite_and",
                    details=f"All {len(conditions)} AND conditions matched",
                )
        elif operator == "or":
            if any(results):
                return MatchResult(
                    matched=True,
                    matched_by="composite_or",
                    details=f"At least one of {len(conditions)} OR conditions matched",
                )
        elif operator == "not":
            if not any(results):
                return MatchResult(
                    matched=True,
                    matched_by="composite_not",
                    details="None of the NOT conditions matched",
                )

        return MatchResult()

    def _match_simple(self, segment: Segment, condition: str | dict) -> MatchResult:
        """Match a simple condition (string or dict).

        Returns MatchResult (which is truthy on match).
        """
        if isinstance(condition, str):
            matched = condition.lower() in segment.raw.lower()
            return MatchResult(
                matched=matched,
                matched_by="condition" if matched else "",
                details=f"Condition '{condition}' {'matched' if matched else 'not found'}",
            )
        if isinstance(condition, dict):
            return self.match_segment(segment, condition)
        return MatchResult()

    def _match_syscall(self, segment: Segment, match_def: dict[str, Any]) -> MatchResult:
        """Match against likely syscall usage (heuristic)."""
        dangerous_commands = {
            "mount", "umount", "kexec", "insmod", "modprobe",
            "rmmod", "swapon", "swapoff", "sysctl", "dmesg",
            "reboot", "shutdown", "halt", "poweroff", "init",
        }
        words = set(w.lower() for w in segment.raw.split())
        matched = words & dangerous_commands

        if matched:
            return MatchResult(
                matched=True,
                matched_by="syscall",
                details=f"Dangerous syscall command(s) detected: {', '.join(matched)}",
            )
        return MatchResult()

    def _match_network(self, segment: Segment, match_def: dict[str, Any]) -> MatchResult:
        """Match against network addresses/URLs."""
        ip_pattern = match_def.get("network", r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")
        try:
            regex = re.compile(ip_pattern)
        except re.error:
            return MatchResult()

        for word in segment.raw.split():
            if regex.search(word):
                return MatchResult(
                    matched=True,
                    matched_by="network",
                    details=f"Network address '{word}' matched pattern",
                )
        return MatchResult()

    def _match_heredoc(self, segment: Segment, match_def: dict[str, Any]) -> MatchResult:
        """Match inside heredoc content."""
        pattern_str = match_def.get("pattern", "")
        if not pattern_str:
            return MatchResult()

        try:
            regex = re.compile(pattern_str, re.IGNORECASE)
        except re.error:
            return MatchResult()

        if segment.type == SegmentType.HEREDOC_CONTENT and regex.search(segment.raw):
            return MatchResult(
                matched=True,
                matched_by="heredoc",
                details=f"Heredoc content matched '{pattern_str}'",
            )
        return MatchResult()
