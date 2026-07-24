"""Built-in auto-sandbox rules for the interruptor.

These commands are automatically wrapped in an unshare namespace for
additional isolation. They are never blocked, only sandboxed.
"""

from __future__ import annotations

from .rules import Rule

BUILTIN_SANDBOX: list[Rule] = [
    Rule(
        rule_id="auto-pytest",
        description="Python test runner",
        priority=700,
        action="sandbox",
        block_message="Auto-sandboxed: pytest running in isolated namespace.",
        match={
            "type": "pattern",
            "pattern": r"pytest|tox|nose",
        },
    ),
    Rule(
        rule_id="auto-npm-test",
        description="JavaScript test runner",
        priority=700,
        action="sandbox",
        block_message="Auto-sandboxed: JS test runner in isolated namespace.",
        match={
            "type": "pattern",
            "pattern": r"npm\s+test|npx\s+(vitest|jest)",
        },
    ),
    Rule(
        rule_id="auto-go-test",
        description="Go test runner",
        priority=700,
        action="sandbox",
        block_message="Auto-sandboxed: Go test runner in isolated namespace.",
        match={
            "type": "pattern",
            "pattern": r"go\s+test",
        },
    ),
    Rule(
        rule_id="auto-make",
        description="Build system",
        priority=700,
        action="sandbox",
        block_message="Auto-sandboxed: build tool in isolated namespace.",
        match={
            "type": "pattern",
            "pattern": r"make\s|make$",
        },
    ),
    Rule(
        rule_id="auto-pip",
        description="Package installer",
        priority=700,
        action="sandbox",
        block_message="Auto-sandboxed: package installer in isolated namespace.",
        match={
            "type": "pattern",
            "pattern": r"pip\s+install|pip3\s+install",
        },
    ),
    Rule(
        rule_id="auto-cargo",
        description="Rust build tool",
        priority=700,
        action="sandbox",
        block_message="Auto-sandboxed: Rust build in isolated namespace.",
        match={
            "type": "pattern",
            "pattern": r"cargo\s+(build|test)",
        },
    ),
    Rule(
        rule_id="auto-gcc",
        description="C/C++ compilation",
        priority=700,
        action="sandbox",
        block_message="Auto-sandboxed: compilation in isolated namespace.",
        match={
            "type": "pattern",
            "pattern": r"gcc\s|g\+\+\s|clang\+\+\s",
        },
    ),
    Rule(
        rule_id="auto-script",
        description="Script execution",
        priority=700,
        action="sandbox",
        block_message="Auto-sandboxed: script execution in isolated namespace.",
        match={
            "type": "pattern",
            "pattern": r"\.(sh|py|rb)\s",
        },
    ),
]
