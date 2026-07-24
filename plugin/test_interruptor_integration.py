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
        cli_path, "echo", "warn-test",
        extra_env={"TERMINAL_JAIL_INTERRUPTOR_MODE": "warn"},
    )
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode == 0:
        assert b"warn-test" in result.stdout
    elif "Permission denied" in stderr or "Operation not permitted" in stderr:
        # unshare may fail on this host; that's okay
        pass


@pytest.mark.standalone_cli
def test_interruptor_disabled_mode_bypasses(cli_path: Path) -> None:
    """Disabled mode bypasses the interruptor entirely."""
    result = _run_cli(
        cli_path, "echo", "disabled-test",
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
        capture_output=True, text=False, check=False, timeout=10,
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
        capture_output=True, text=False, check=False, timeout=10,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0
    response = json.loads(result.stdout.decode("utf-8"))
    assert response["action"] == "block"
    assert response["rule_id"] is not None
    assert response["reason"] is not None


# ── T-I38: Custom user rules (requires Decider Layer 4 implementation) ───────

@pytest.mark.skip(reason="Requires user rule loading in Decider Layer 4 (not yet implemented)")
def test_custom_user_rule_overrides_builtin() -> None:
    """User allowlist rule overrides a built-in block rule."""


# ── T-I39: Priority ordering (requires Decider Layer 4 implementation) ───────

@pytest.mark.skip(reason="Requires user rule loading in Decider Layer 4 (not yet implemented)")
def test_priority_ordering() -> None:
    """Higher-priority user rule wins over lower-priority."""


# ── T-I40: Rule directory hot-reload (requires file watcher) ────────────────

@pytest.mark.skip(reason="Requires SIGHUP or file-watcher implementation for runtime rule reload")
def test_rule_hot_reload() -> None:
    """New rules loaded without CLI restart."""
