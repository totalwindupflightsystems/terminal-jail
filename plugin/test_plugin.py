from __future__ import annotations

import logging
import os
from pathlib import Path
import shlex
import shutil
import subprocess
from unittest.mock import Mock

import pytest

import plugin.terminal_jail.plugin as plugin_module
import plugin


ENVIRONMENT_VARIABLES = (
    "HERMES_TERMINAL_JAIL_ENABLED",
    "HERMES_TERMINAL_JAIL_COMMAND",
    "HERMES_TERMINAL_JAIL_MAX_COMMAND_BYTES",
    "HERMES_TERMINAL_JAIL_LOG_LEVEL",
)
FIXED_OPTIONS = "--pid --fork --mount-proc --kill-child=SIGKILL bash -c "


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    plugin_module.LOGGER.setLevel(logging.WARNING)


def expected_wrapped(command: str, executable: str = "/test/bin/unshare") -> str:
    return f"{shlex.quote(executable)} {FIXED_OPTIONS}{shlex.quote(command)}"


def install_successful_unshare_shim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shim = tmp_path / "unshare"
    shim.write_text(
        """#!/usr/bin/env bash
set -u

fail() {
    printf 'unshare-shim: %s\\n' "$1" >&2
    exit 126
}

[[ "$#" -eq 7 ]] || fail "expected exactly seven arguments"
args=("$@")
expected=(--pid --fork --mount-proc --kill-child=SIGKILL)
actual=("$1" "$2" "$3" "$4")
for index in 0 1 2 3; do
    [[ "${actual[$index]}" == "${expected[$index]}" ]] || fail "invalid option ordering"
done
shift 4
[[ "$#" -eq 3 ]] || fail "expected bash -c and one payload"
[[ "$1" == "bash" ]] || fail "expected bash"
[[ "$2" == "-c" ]] || fail "expected -c"

if [[ -n "${TERMINAL_JAIL_SHIM_RECORD:-}" ]]; then
    {
        printf 'argc=%s\\n' "$#"
        printf 'arg1=%s\\n' "$1"
        printf 'arg2=%s\\n' "$2"
        printf 'arg3=%s\\n' "$3"
    } > "$TERMINAL_JAIL_SHIM_RECORD"
fi

exec /bin/bash -c "$3"
""",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    return shim


def run_transformed(command: str) -> subprocess.CompletedProcess[bytes]:
    transformed = plugin_module.transform_command(command)
    return subprocess.run(
        transformed,
        shell=True,
        executable="/bin/bash",
        text=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_t01_generic_hook_registers() -> None:
    assert plugin.__manifest__["hooks"]["terminal.command.transform"] is plugin.transform_command
    assert plugin.hooks is plugin.__manifest__["hooks"]


def test_t02_exec_hook_registers() -> None:
    assert (
        plugin.__manifest__["hooks"]["terminal.command.transform.exec"]
        is plugin.transform_exec_command
    )
    assert plugin.transform_exec_command is not plugin.transform_command


def test_t03_default_wrapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugin_module.shutil, "which", lambda value: "/test/bin/unshare")

    assert plugin_module.transform_command("echo hello") == expected_wrapped("echo hello")


def test_t04_exec_delegates_once(monkeypatch: pytest.MonkeyPatch) -> None:
    transform = Mock(return_value="transformed")
    monkeypatch.setattr(plugin_module, "transform_command", transform)

    assert plugin_module.transform_exec_command("representative command") == "transformed"
    transform.assert_called_once_with("representative command")


def test_t05_shell_metacharacters_are_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = 'echo "$(id)"; true && printf x | tee /tmp/x > /dev/null'
    monkeypatch.setattr(plugin_module.shutil, "which", lambda value: "/test/bin/unshare")

    assert plugin_module.transform_command(raw) == expected_wrapped(raw)


def test_t06_nested_quotes_are_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = "printf '%s\\n' \"a b\""
    monkeypatch.setattr(plugin_module.shutil, "which", lambda value: "/test/bin/unshare")

    assert plugin_module.transform_command(raw) == expected_wrapped(raw)


def test_t07_embedded_newline_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = "printf first\nprintf second"
    monkeypatch.setattr(plugin_module.shutil, "which", lambda value: "/test/bin/unshare")

    transformed = plugin_module.transform_command(raw)

    assert transformed == expected_wrapped(raw)
    assert "\n" in transformed


def test_t08_leading_and_trailing_spaces_are_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = " echo ok "
    monkeypatch.setattr(plugin_module.shutil, "which", lambda value: "/test/bin/unshare")

    assert plugin_module.transform_command(raw) == expected_wrapped(raw)


def test_t09_empty_command_returns_without_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    lookup = Mock(side_effect=AssertionError("lookup must not run"))
    monkeypatch.setattr(plugin_module.shutil, "which", lookup)

    assert plugin_module.transform_command("") == ""
    lookup.assert_not_called()


def test_t10_whitespace_only_command_returns_exactly(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = " \t\n\u2003"
    lookup = Mock(side_effect=AssertionError("lookup must not run"))
    monkeypatch.setattr(plugin_module.shutil, "which", lookup)

    assert plugin_module.transform_command(raw) == raw
    lookup.assert_not_called()


def test_t11_disabled_feature_returns_without_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = "echo disabled"
    lookup = Mock(side_effect=AssertionError("lookup must not run"))
    monkeypatch.setenv("HERMES_TERMINAL_JAIL_ENABLED", "0")
    monkeypatch.setattr(plugin_module.shutil, "which", lookup)

    assert plugin_module.transform_command(raw) == raw
    lookup.assert_not_called()


def test_t12_invalid_feature_setting_warns_without_command(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    raw = "echo command-secret-t12"
    monkeypatch.setenv("HERMES_TERMINAL_JAIL_ENABLED", "perhaps")

    with caplog.at_level(logging.WARNING, logger="terminal_jail"):
        assert plugin_module.transform_command(raw) == raw

    messages = " ".join(caplog.messages)
    assert "HERMES_TERMINAL_JAIL_ENABLED" in messages
    assert raw not in messages


def test_t13_missing_unshare_warns_without_command(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    raw = "echo command-secret-t13"
    monkeypatch.setattr(plugin_module.shutil, "which", lambda value: None)

    with caplog.at_level(logging.WARNING, logger="terminal_jail"):
        assert plugin_module.transform_command(raw) == raw

    messages = " ".join(caplog.messages).lower()
    assert "isolation" in messages
    assert raw not in messages


def test_t14_empty_configured_executable_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    raw = "echo command-secret-t14"
    monkeypatch.setenv("HERMES_TERMINAL_JAIL_COMMAND", "   ")

    with caplog.at_level(logging.WARNING, logger="terminal_jail"):
        assert plugin_module.transform_command(raw) == raw

    assert caplog.records
    assert raw not in " ".join(caplog.messages)


def test_t15_unsafe_executable_setting_skips_lookup(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    raw = "echo command-secret-t15"
    lookup = Mock(side_effect=AssertionError("unsafe executable must not be looked up"))
    monkeypatch.setenv("HERMES_TERMINAL_JAIL_COMMAND", "unshare --user")
    monkeypatch.setattr(plugin_module.shutil, "which", lookup)

    with caplog.at_level(logging.WARNING, logger="terminal_jail"):
        assert plugin_module.transform_command(raw) == raw

    lookup.assert_not_called()
    assert caplog.records
    assert raw not in " ".join(caplog.messages)


def test_t16_resolved_custom_executable_path_is_quoted(monkeypatch: pytest.MonkeyPatch) -> None:
    resolved = "/tmp/a b/unshare"
    monkeypatch.setenv("HERMES_TERMINAL_JAIL_COMMAND", "custom-unshare")
    monkeypatch.setattr(plugin_module.shutil, "which", lambda value: resolved)

    assert plugin_module.transform_command("true") == expected_wrapped("true", resolved)


def test_t17_byte_budget_accepts_exact_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = "echo boundary"
    wrapped = expected_wrapped(raw)
    monkeypatch.setattr(plugin_module.shutil, "which", lambda value: "/test/bin/unshare")
    monkeypatch.setenv(
        "HERMES_TERMINAL_JAIL_MAX_COMMAND_BYTES", str(len(wrapped.encode("utf-8")))
    )

    assert plugin_module.transform_command(raw) == wrapped


def test_t18_byte_budget_rejects_one_byte_over_boundary(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    raw = "echo command-secret-t18"
    wrapped = expected_wrapped(raw)
    monkeypatch.setattr(plugin_module.shutil, "which", lambda value: "/test/bin/unshare")
    monkeypatch.setenv(
        "HERMES_TERMINAL_JAIL_MAX_COMMAND_BYTES",
        str(len(wrapped.encode("utf-8")) - 1),
    )

    with caplog.at_level(logging.WARNING, logger="terminal_jail"):
        assert plugin_module.transform_command(raw) == raw

    assert "byte" in " ".join(caplog.messages).lower()
    assert raw not in " ".join(caplog.messages)


@pytest.mark.parametrize("invalid_limit", ["not-a-number", "0", "-1"])
def test_t19_invalid_byte_budget_uses_default(
    invalid_limit: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = "echo valid-size"
    monkeypatch.setattr(plugin_module.shutil, "which", lambda value: "/test/bin/unshare")
    monkeypatch.setenv("HERMES_TERMINAL_JAIL_MAX_COMMAND_BYTES", invalid_limit)

    with caplog.at_level(logging.WARNING, logger="terminal_jail"):
        assert plugin_module.transform_command(raw) == expected_wrapped(raw)

    assert "HERMES_TERMINAL_JAIL_MAX_COMMAND_BYTES" in " ".join(caplog.messages)


def test_t20_budget_counts_utf8_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = "printf café"
    wrapped = expected_wrapped(raw)
    character_count = len(wrapped)
    byte_count = len(wrapped.encode("utf-8"))
    assert byte_count > character_count
    monkeypatch.setattr(plugin_module.shutil, "which", lambda value: "/test/bin/unshare")

    monkeypatch.setenv("HERMES_TERMINAL_JAIL_MAX_COMMAND_BYTES", str(character_count))
    assert plugin_module.transform_command(raw) == raw

    monkeypatch.setenv("HERMES_TERMINAL_JAIL_MAX_COMMAND_BYTES", str(byte_count))
    assert plugin_module.transform_command(raw) == wrapped


def test_t21_unexpected_quoting_failure_returns_raw_with_exception_info(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    raw = "echo command-secret-t21"
    monkeypatch.setattr(plugin_module.shutil, "which", lambda value: "/test/bin/unshare")
    monkeypatch.setattr(
        plugin_module.shlex, "quote", Mock(side_effect=RuntimeError("quote failed"))
    )

    with caplog.at_level(logging.WARNING, logger="terminal_jail"):
        assert plugin_module.transform_command(raw) == raw

    assert any(record.exc_info is not None for record in caplog.records)
    assert raw not in " ".join(caplog.messages)


def test_t22_exit_code_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_successful_unshare_shim(tmp_path, monkeypatch)

    result = run_transformed("true")

    assert result.returncode == 0


def test_t23_exit_code_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_successful_unshare_shim(tmp_path, monkeypatch)

    result = run_transformed("exit 7")

    assert result.returncode == 7


def test_t24_nested_shell_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_successful_unshare_shim(tmp_path, monkeypatch)

    result = run_transformed("sh -c 'exit 42'")

    assert result.returncode == 42


def test_t25_stdout_passthrough(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_successful_unshare_shim(tmp_path, monkeypatch)

    result = run_transformed("printf out")

    assert result.returncode == 0
    assert result.stdout == b"out"
    assert result.stderr == b""


def test_t26_stderr_passthrough(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_successful_unshare_shim(tmp_path, monkeypatch)

    result = run_transformed("printf err >&2")

    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b"err"


def test_t27_mixed_streams_are_unmodified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_successful_unshare_shim(tmp_path, monkeypatch)

    result = run_transformed("printf stdout-marker; printf stderr-marker >&2")

    assert result.returncode == 0
    assert result.stdout == b"stdout-marker"
    assert result.stderr == b"stderr-marker"


def test_t28_harmless_fork_bomb_simulation_has_required_structure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shim = install_successful_unshare_shim(tmp_path, monkeypatch)
    record = tmp_path / "shim-record"
    raw = "echo fork-bomb-simulation"
    monkeypatch.setenv("TERMINAL_JAIL_SHIM_RECORD", str(record))

    transformed = plugin_module.transform_command(raw)
    result = run_transformed(raw)

    assert transformed == expected_wrapped(raw, str(shim))
    assert result.returncode == 0
    assert result.stdout == b"fork-bomb-simulation\n"
    assert record.read_text(encoding="utf-8").splitlines() == [
        "argc=3",
        "arg1=bash",
        "arg2=-c",
        f"arg3={raw}",
    ]


@pytest.mark.integration
def test_t29_real_pid_namespace_process_view(monkeypatch: pytest.MonkeyPatch) -> None:
    real_unshare = shutil.which("unshare")
    if real_unshare is None:
        pytest.skip("unshare is not installed")

    probe = subprocess.run(
        [
            real_unshare,
            "--pid",
            "--fork",
            "--mount-proc",
            "--kill-child=SIGKILL",
            "bash",
            "-c",
            "true",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if probe.returncode != 0:
        pytest.skip("host policy does not permit the required PID namespace")

    monkeypatch.setenv("HERMES_TERMINAL_JAIL_COMMAND", real_unshare)
    result = run_transformed("test \"$(ps -o pid= -p $$ | tr -d ' ')\" = 1")

    assert result.returncode == 0, result.stderr.decode(errors="replace")


def test_t30_runtime_unshare_error_is_not_retried_raw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shim = tmp_path / "unshare"
    sentinel = tmp_path / "inner-command-ran"
    shim.write_text(
        "#!/usr/bin/env bash\nprintf 'unshare-shim: runtime error\\n' >&2\nexit 125\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    result = run_transformed(f"printf ran > {shlex.quote(str(sentinel))}")

    assert result.returncode == 125
    assert result.stdout == b""
    assert result.stderr == b"unshare-shim: runtime error\n"
    assert not sentinel.exists()
