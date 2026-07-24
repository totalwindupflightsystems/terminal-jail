"""
Shell command tokenizer/parser for the interruptor.

Parses shell commands into token and segment structures for rule evaluation.
Fail-open: parse errors return empty segments (pass-through in caller).

Supported syntax:
  - Pipes: cmd1 | cmd2 | cmd3
  - Redirects: > file, >> file, 2>&1, < file
  - Command substitution: `` cmd `` and $(cmd)
  - Boolean chains: &&, ||, ;
  - Heredocs: <<EOF ... EOF
  - Variable expansion: $VAR, ${VAR}
  - Quoting: single-quoted (literal), double-quoted (variable expansion)
"""

from __future__ import annotations

import re
from enum import Enum
from typing import NamedTuple


class TokenType(Enum):
    """Categories of tokens in a shell command."""

    COMMAND = "command"
    PIPE = "pipe"
    AND = "and"
    OR = "or"
    SEMICOLON = "semicolon"
    BACKGROUND = "background"
    REDIRECT_OUT = "redirect_out"
    REDIRECT_APPEND = "redirect_append"
    REDIRECT_IN = "redirect_in"
    REDIRECT_STDERR = "redirect_stderr"
    HEREDOC = "heredoc"
    SUBSHELL = "subshell"
    COMMAND_SUB = "command_sub"
    VARIABLE = "variable"
    ASSIGNMENT = "assignment"
    FILE_ARG = "file_arg"
    STRING = "string"
    WORD = "word"
    NEWLINE = "newline"


class Token(NamedTuple):
    """A single token from the shell command."""

    type: TokenType
    value: str
    pos: int


class SegmentType(Enum):
    """Types of parsed command segments."""

    SIMPLE = "simple"
    PIPE = "pipe"
    BOOLEAN_AND = "boolean_and"
    BOOLEAN_OR = "boolean_or"
    SEQUENTIAL = "sequential"
    BACKGROUND = "background"
    SUBSHELL = "subshell"
    COMMAND_SUB = "command_sub"
    HEREDOC_CONTENT = "heredoc_content"


class Segment(NamedTuple):
    """A parsed segment of a shell command."""

    type: SegmentType
    tokens: list[Token]
    raw: str
    pos: int


# Regex patterns for shell operators
_OPERATOR_RE = re.compile(
    r"(&&|\|\||[|;&]|2>>|>>|2>|>|<)"
)

# Variable expansion patterns
_VAR_EXPAND = re.compile(r"\$\{([^}]+)\}|\$([a-zA-Z_][a-zA-Z0-9_]*)")

# Command substitution patterns
_CMD_SUB_BACKTICK = re.compile(r"`(?:[^`\\]|\\.)*`")
_CMD_SUB_DOLLAR = re.compile(r"\$\([^()]*(?:\([^()]*\)[^()]*)*\)")

# Assignment pattern (VAR=value at start)
_ASSIGNMENT = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)=(.*)$")

# Sensitive paths
_SENSITIVE_PATHS = re.compile(
    r"/etc/(passwd|shadow|sudoers|ssh|ssl|certs|gshadow|security|"
    r"pam\.d|selinux|apparmor\.d|polkit-\d|systemd/system)"
    r"|/boot/|/proc/|/sys/"
)


def _split_operators(cmd: str) -> list[str]:
    """Split a command string into raw tokens at operator boundaries.

    Splits on shell operators (|, ||, &&, ;, &, >, >>, <) while preserving
    them as separate tokens. Quoted strings are kept intact.
    """
    parts: list[str] = []
    i = 0
    while i < len(cmd):
        # Skip whitespace between tokens
        if cmd[i] in (" ", "\t"):
            i += 1
            continue

        # Check for multi-char operators
        if cmd[i : i + 2] in ("&&", "||", "2>", ">>"):
            parts.append(cmd[i : i + 2])
            i += 2
            continue

        # Check for single-char operators
        if cmd[i] in ("|", ";", "&", "<", ">"):
            parts.append(cmd[i])
            i += 1
            continue

        # Quoted string — find matching close quote
        if cmd[i] in ("'", '"'):
            quote = cmd[i]
            end = i + 1
            while end < len(cmd) and cmd[end] != quote:
                if cmd[end] == "\\":
                    end += 1  # skip escaped char
                end += 1
            end += 1  # include closing quote
            parts.append(cmd[i:end])
            i = end
            continue

        # Regular word — collect chars until operator or whitespace
        start = i
        while i < len(cmd) and cmd[i] not in (" ", "\t", "|", ";", "&", "<", ">"):
            if i + 1 < len(cmd) and cmd[i : i + 2] in ("&&", "||", "2>", ">>"):
                break
            if cmd[i] in ("'", '"'):
                break  # handled above
            i += 1
        parts.append(cmd[start:i])

    # Filter empty parts
    return [p for p in parts if p]


def _operator_to_token_type(op: str) -> TokenType | None:
    """Map an operator string to its token type."""
    mapping = {
        "|": TokenType.PIPE,
        "&&": TokenType.AND,
        "||": TokenType.OR,
        ";": TokenType.SEMICOLON,
        "&": TokenType.BACKGROUND,
        ">": TokenType.REDIRECT_OUT,
        ">>": TokenType.REDIRECT_APPEND,
        "<": TokenType.REDIRECT_IN,
        "2>": TokenType.REDIRECT_STDERR,
        "2>>": TokenType.REDIRECT_STDERR,
    }
    return mapping.get(op)


def _tokenize(cmd: str) -> list[Token]:
    """Tokenize a command string into operator-aware tokens."""
    tokens: list[Token] = []
    raw_parts = _split_operators(cmd)
    pos = 0

    for part in raw_parts:
        op_type = _operator_to_token_type(part)
        if op_type is not None:
            tokens.append(Token(type=op_type, value=part, pos=pos))
            pos += len(part)
        elif _ASSIGNMENT.match(part):
            tokens.append(Token(type=TokenType.ASSIGNMENT, value=part, pos=pos))
            pos += len(part)
        else:
            tokens.append(Token(type=TokenType.WORD, value=part, pos=pos))
            pos += len(part)

    return tokens


def _group_by_operator(tokens: list[Token]) -> list[list[Token]]:
    """Group tokens into segments separated by operators.

    Each group contains the tokens for one pipe/boolean segment.
    """
    groups: list[list[Token]] = []
    current: list[Token] = []

    for token in tokens:
        if token.type in (
            TokenType.PIPE,
            TokenType.AND,
            TokenType.OR,
            TokenType.SEMICOLON,
            TokenType.BACKGROUND,
            TokenType.REDIRECT_OUT,
            TokenType.REDIRECT_APPEND,
            TokenType.REDIRECT_IN,
            TokenType.REDIRECT_STDERR,
        ):
            if current:
                groups.append(current)
                current = []
            # Don't add the operator as its own group — it signals the
            # relationship between adjacent groups
        else:
            current.append(token)

    if current:
        groups.append(current)

    return groups


def _reconstruct_text(tokens: list[Token]) -> str:
    """Reconstruct the raw text from a list of tokens."""
    return " ".join(t.value for t in tokens)


def parse_command(command: str) -> list[Segment]:
    """Parse a shell command into a list of Segments.

    Args:
        command: The raw shell command string.

    Returns:
        A list of Segments. Empty if the command is empty or unparseable.
        Never raises — fail-open to empty list.
    """
    if not command or not command.strip():
        return []

    try:
        tokens = _tokenize(command.strip())
        if not tokens:
            return []

        groups = _group_by_operator(tokens)
        if not groups:
            return []

        segments: list[Segment] = []
        for group in groups:
            raw = _reconstruct_text(group)
            segments.append(
                Segment(
                    type=SegmentType.SIMPLE,
                    tokens=group,
                    raw=raw,
                    pos=group[0].pos if group else 0,
                )
            )

        return segments

    except Exception:
        return []


def is_sensitive_path(path: str) -> bool:
    """Check if a path is a sensitive system path."""
    return bool(_SENSITIVE_PATHS.search(path))


def expand_variables(text: str) -> list[str]:
    """Find variable expansions in a string."""
    return [
        m.group(1) or m.group(2)
        for m in _VAR_EXPAND.finditer(text)
        if m.group(1) or m.group(2)
    ]


def find_command_substitution(text: str) -> list[str]:
    """Find command substitution expressions in a string."""
    result: list[str] = []

    for m in _CMD_SUB_DOLLAR.finditer(text):
        inner = m.group(0)[2:-1]
        result.append(inner)

    for m in _CMD_SUB_BACKTICK.finditer(text):
        inner = m.group(0)[1:-1]
        result.append(inner)

    return result
