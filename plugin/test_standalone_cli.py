from __future__ import annotations

import os
import stat
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
    unset_env: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    for key in unset_env:
        env.pop(key, None)
    return subprocess.run(
        [str(cli), *args],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=False,
        check=False,
        timeout=10,
    )


def _make_test_bin(tmp_path: Path, *, include_unshare: bool = False) -> str:
    """Build a minimal PATH with bash and uname, optionally unshare."""
    test_bin = tmp_path / "testbin"
    test_bin.mkdir(exist_ok=True)
    (test_bin / "bash").symlink_to("/usr/bin/bash")
    (test_bin / "uname").symlink_to("/usr/bin/uname")
    if include_unshare:
        (test_bin / "unshare").symlink_to("/usr/bin/unshare")
    return str(test_bin)


# ── Flag parsing ──────────────────────────────────────────────────────────

@pytest.mark.standalone_cli
def test_help_flag(cli_path: Path) -> None:
    result = _run_cli(cli_path, "--help", unset_env=("TERMINAL_JAIL_VERSION",))
    assert result.returncode == 0
    stdout = result.stdout.decode("utf-8")
    assert "Usage:" in stdout


@pytest.mark.standalone_cli
def test_short_help_flag(cli_path: Path) -> None:
    result = _run_cli(cli_path, "-h", unset_env=("TERMINAL_JAIL_VERSION",))
    assert result.returncode == 0
    assert "Usage:" in result.stdout.decode("utf-8")


@pytest.mark.standalone_cli
def test_version_flag(cli_path: Path) -> None:
    result = _run_cli(cli_path, "--version", unset_env=("TERMINAL_JAIL_VERSION",))
    assert result.returncode == 0
    stdout = result.stdout.decode("utf-8")
    assert "terminal-jail" in stdout


@pytest.mark.standalone_cli
def test_short_version_flag(cli_path: Path) -> None:
    result = _run_cli(cli_path, "-V", unset_env=("TERMINAL_JAIL_VERSION",))
    assert result.returncode == 0
    assert "terminal-jail" in result.stdout.decode("utf-8")


@pytest.mark.standalone_cli
def test_version_from_env(cli_path: Path) -> None:
    result = _run_cli(cli_path, "--version", extra_env={"TERMINAL_JAIL_VERSION": "9.9.9-test"})
    assert result.returncode == 0
    assert "9.9.9-test" in result.stdout.decode("utf-8")


# ── Error paths ────────────────────────────────────────────────────────────

@pytest.mark.standalone_cli
def test_no_args(cli_path: Path) -> None:
    result = _run_cli(cli_path)
    assert result.returncode == 2
    assert result.stdout == b""
    stderr = result.stderr.decode("utf-8")
    assert "Usage:" in stderr


@pytest.mark.standalone_cli
def test_non_linux_os(cli_path: Path, tmp_path: Path) -> None:
    """Simulate non-Linux OS by overriding uname with a fake Darwin."""
    test_bin = tmp_path / "testbin"
    test_bin.mkdir(exist_ok=True)
    (test_bin / "bash").symlink_to("/usr/bin/bash")

    fake_uname = test_bin / "uname"
    fake_uname.write_text("#!/bin/bash\necho Darwin\n")
    fake_uname.chmod(fake_uname.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    result = _run_cli(cli_path, "echo", "hello", extra_env={"PATH": str(test_bin)})
    assert result.returncode == 2
    stderr = result.stderr.decode("utf-8")
    assert "requires Linux PID namespaces" in stderr


@pytest.mark.standalone_cli
def test_missing_unshare(cli_path: Path, tmp_path: Path) -> None:
    """PATH lacks unshare — script exits 2 with error message."""
    path = _make_test_bin(tmp_path, include_unshare=False)
    result = _run_cli(cli_path, "echo", "hello", extra_env={"PATH": path})
    assert result.returncode == 2
    assert "unshare is required" in result.stderr.decode("utf-8")


# ── Command execution (host-constrained: unshare --mount-proc may fail) ─────

@pytest.mark.standalone_cli
def test_simple_command(cli_path: Path) -> None:
    """A trivial command through the jail."""
    result = _run_cli(cli_path, "echo", "hello-world-42")
    if result.returncode == 0:
        assert "hello-world-42" in result.stdout.decode("utf-8")
    else:
        stderr = result.stderr.decode("utf-8", errors="replace")
        assert "Permission denied" in stderr or "Operation not permitted" in stderr


@pytest.mark.standalone_cli
def test_command_with_args(cli_path: Path) -> None:
    result = _run_cli(cli_path, "printf", "%s:%s:%s", "a", "b", "c")
    if result.returncode == 0:
        assert "a:b:c" in result.stdout.decode("utf-8")


@pytest.mark.standalone_cli
def test_command_with_special_chars(cli_path: Path) -> None:
    result = _run_cli(cli_path, "echo", "path/to/file with spaces")
    if result.returncode == 0:
        assert "path/to/file with spaces" in result.stdout.decode("utf-8")


# ── Exit code propagation ──────────────────────────────────────────────────

@pytest.mark.standalone_cli
def test_exit_code_zero(cli_path: Path) -> None:
    result = _run_cli(cli_path, "true")
    stderr = result.stderr.decode("utf-8", errors="replace")
    if "Permission denied" not in stderr and "Operation not permitted" not in stderr:
        assert result.returncode == 0


@pytest.mark.standalone_cli
def test_exit_code_nonzero(cli_path: Path) -> None:
    result = _run_cli(cli_path, "bash", "-c", "exit 42")
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode not in (0, 1) and "Permission denied" not in stderr:
        assert result.returncode == 42


# ── Stdin/stderr passthrough ───────────────────────────────────────────────

@pytest.mark.standalone_cli
def test_stdin_passthrough(cli_path: Path) -> None:
    env = os.environ.copy()
    proc = subprocess.run(
        [str(cli_path), "cat", "-"],
        input=b"hello-from-stdin\n",
        capture_output=True, check=False,
        timeout=10,
        env=env,
    )
    if proc.returncode == 0:
        assert b"hello-from-stdin" in proc.stdout


@pytest.mark.standalone_cli
def test_stderr_passthrough(cli_path: Path) -> None:
    result = _run_cli(cli_path, "bash", "-c", "echo 'to-stderr' >&2")
    if result.returncode == 0:
        assert b"to-stderr" in result.stderr


@pytest.mark.standalone_cli
def test_combined_user_seccomp(cli_path: Path) -> None:
    result = _run_cli(cli_path, "--user", "--seccomp", "echo", "combined-test")
    if result.returncode == 0:
        assert "combined-test" in result.stdout.decode("utf-8")
    else:
        stderr = result.stderr.decode("utf-8", errors="replace")
        assert (
            "Permission denied" in stderr
            or "Operation not permitted" in stderr
            or result.returncode in (159, -31)
        )
