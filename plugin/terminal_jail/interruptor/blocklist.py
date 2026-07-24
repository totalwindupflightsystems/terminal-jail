"""Built-in critical blocklist rules for the interruptor.

These rules are ALWAYS active and cannot be removed — only overridden to
``warn`` level by user rules. They ship with the interruptor package.
"""

from __future__ import annotations

from .rules import Rule

BUILTIN_BLOCKLIST: list[Rule] = [
    Rule(
        rule_id="builtin-kill-all",
        description="Mass process kill",
        priority=1000,
        action="block",
        block_message="Mass process kill (kill -9 -1) is blocked.",
        match={
            "type": "pattern",
            "pattern": r"kill\s+-9\s+-1",
        },
    ),
    Rule(
        rule_id="builtin-fork-bomb",
        description="Fork bomb pattern",
        priority=1000,
        action="block",
        block_message="Fork bomb pattern detected and blocked.",
        match={
            "type": "pattern",
            "pattern": r":\s*\(\)\s*\{.*:\|:&\s*\}",
        },
    ),
    Rule(
        rule_id="builtin-rm-rf-root",
        description="Recursive root filesystem removal",
        priority=1000,
        action="block",
        block_message="Recursive root directory removal (rm -rf /) is blocked.",
        match={
            "type": "pattern",
            "pattern": r"rm\s+(-{1,2})?\s*-?rf\s+/",
        },
    ),
    Rule(
        rule_id="builtin-dd-root",
        description="Raw device write via dd",
        priority=1000,
        action="block",
        block_message="Raw device writes (dd to /dev/*) are blocked.",
        match={
            "type": "pattern",
            "pattern": r"dd\s+.*of=/dev/",
        },
    ),
    Rule(
        rule_id="builtin-mkfs",
        description="Filesystem creation",
        priority=1000,
        action="block",
        block_message="Filesystem creation commands (mkfs.*) are blocked.",
        match={
            "type": "pattern",
            "pattern": r"mkfs\.",
        },
    ),
    Rule(
        rule_id="builtin-fdisk",
        description="Partition manipulation",
        priority=1000,
        action="block",
        block_message="Partition manipulation (fdisk, parted, gdisk) is blocked.",
        match={
            "type": "pattern",
            "pattern": r"fdisk|parted|gdisk",
        },
    ),
    Rule(
        rule_id="builtin-chmod-777-root",
        description="World-writable root",
        priority=1000,
        action="block",
        block_message="Setting world-writable permissions on root (/) is blocked.",
        match={
            "type": "pattern",
            "pattern": r"chmod\s+777\s+/",
        },
    ),
    Rule(
        rule_id="builtin-echo-to-system",
        description="Redirect output to system paths",
        priority=1000,
        action="block",
        block_message="Writing to system paths (/etc/, /boot/) is blocked.",
        match={
            "type": "pattern",
            "pattern": r">\s*/etc/|>>\s*/etc/|>\s*/boot/|>>\s*/boot/",
        },
    ),
    Rule(
        rule_id="builtin-curl-pipe-shell",
        description="Curl/wget piping to shell",
        priority=1000,
        action="block",
        block_message="Piping downloads directly to a shell is blocked. Use package managers instead.",
        match={
            "type": "pattern",
            "pattern": r"(curl|wget)\b.*\|\s*(bash|sh|dash|zsh)",
        },
    ),
    Rule(
        rule_id="builtin-sudo",
        description="Privilege escalation via sudo",
        priority=1000,
        action="block",
        block_message="Privilege escalation (sudo) is blocked in the sandbox.",
        match={
            "type": "pattern",
            "pattern": r"\bsudo\s",
        },
    ),
]
