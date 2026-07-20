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
    plugin_module.reset_metrics()


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


def test_t01_register_is_callable_and_exports_transforms() -> None:
    """register() is the Hermes plugin entry point; transforms are importable."""
    assert callable(plugin.register)
    assert callable(plugin.transform_command)
    assert callable(plugin.transform_exec_command)


def test_t02_transforms_are_distinct() -> None:
    """transform_command and transform_exec_command exist and are different callables."""
    assert plugin.transform_command is not plugin.transform_exec_command
    # But transform_exec_command delegates to transform_command at runtime.
    assert plugin.transform_exec_command("echo hi") == plugin.transform_command("echo hi")


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


# ---------------------------------------------------------------------------
# Phase 4 E2E tests — validate plugin behaviour without requiring unshare
# ---------------------------------------------------------------------------


class TestDisabledMode:
    """T4.3: Disabled mode E2E — verify commands pass through unwrapped."""

    def test_t31_disabled_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_ENABLED", "0")
        assert plugin_module.transform_command("echo hello") == "echo hello"

    def test_t32_disabled_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_ENABLED", "false")
        assert plugin_module.transform_command("echo hello") == "echo hello"

    def test_t33_disabled_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_ENABLED", "off")
        assert plugin_module.transform_command("echo hello") == "echo hello"

    def test_t34_disabled_no(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_ENABLED", "no")
        assert plugin_module.transform_command("echo hello") == "echo hello"

    def test_t35_disabled_unrecognised(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_ENABLED", "garbage")
        assert plugin_module.transform_command("echo hello") == "echo hello"


class TestMissingUnshare:
    """T4.4: Missing unshare E2E — verify graceful degrade."""

    def test_t36_missing_unshare_passthrough(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_COMMAND", "/nonexistent/unshare")
        assert plugin_module.transform_command("echo hello") == "echo hello"

    def test_t37_empty_command_passthrough(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_COMMAND", "")
        assert plugin_module.transform_command("echo hello") == "echo hello"


class TestLogLevel:
    """T4.7: Log level configuration."""

    def test_t38_log_level_debug(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_ENABLED", "0")
        plugin_module._configure_logger()
        assert plugin_module.LOGGER.getEffectiveLevel() == logging.DEBUG

    def test_t39_log_level_warning(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_LOG_LEVEL", "WARNING")
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_ENABLED", "0")
        plugin_module._configure_logger()
        assert plugin_module.LOGGER.getEffectiveLevel() == logging.WARNING

    def test_t40_log_level_invalid_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_LOG_LEVEL", "NOT_A_REAL_LEVEL")
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_ENABLED", "0")
        plugin_module._configure_logger()
        assert plugin_module.LOGGER.getEffectiveLevel() == logging.WARNING


class TestEdgeCases:
    """AUDIT-04: Cover the 7 uncovered statements in plugin.py.

    These are defensive code paths that guard against malicious input:
    NUL byte injection, non-str type confusion, and unexpected exceptions
    from the byte-budget check.
    """

    # ── NUL byte check (L58-63) ──────────────────────────────────────

    def test_t41_nul_byte_in_command_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If HERMES_TERMINAL_JAIL_COMMAND contains NUL, return None."""
        # os.environ blocks NUL bytes — mock environ.get to bypass OS guard.
        monkeypatch.setitem(
            os.environ, "HERMES_TERMINAL_JAIL_COMMAND", "safe-value"
        )
        original_get = os.environ.get

        def _fake_get(key: str, default: object = None) -> object:
            if key == "HERMES_TERMINAL_JAIL_COMMAND":
                return "unshare\x00malicious"
            return original_get(key, default)

        monkeypatch.setattr(os.environ, "get", _fake_get)
        result = plugin_module._unshare_executable_from_environment()
        assert result is None

    # ── Non-str type guard (L106-111) ────────────────────────────────

    def test_t42_non_str_input_passthrough_int(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """transform_command with int returns the int unchanged."""
        caplog.set_level(logging.WARNING)
        result = plugin_module.transform_command(42)  # type: ignore[arg-type]
        assert result == 42

    def test_t43_non_str_input_passthrough_bytes(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """transform_command with bytes returns the bytes unchanged."""
        caplog.set_level(logging.WARNING)
        result = plugin_module.transform_command(b"echo hello")  # type: ignore[arg-type]
        assert result == b"echo hello"

    def test_t44_non_str_input_passthrough_none(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """transform_command with None returns None unchanged."""
        caplog.set_level(logging.WARNING)
        result = plugin_module.transform_command(None)  # type: ignore[arg-type]
        assert result is None

    # ── Budget-check exception handler (L154-159) ────────────────────

    def test_t45_byte_budget_check_exception(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        tmp_path: Path,
    ) -> None:
        """If _max_command_bytes_from_environment raises unexpectedly,
        the command passes through unwrapped."""
        from unittest.mock import patch as mock_patch

        install_successful_unshare_shim(tmp_path, monkeypatch)
        monkeypatch.setenv(
            "HERMES_TERMINAL_JAIL_COMMAND", str(tmp_path / "unshare")
        )
        caplog.set_level(logging.WARNING)

        with mock_patch.object(
            plugin_module,
            "_max_command_bytes_from_environment",
            side_effect=RuntimeError("simulated failure"),
        ):
            result = plugin_module.transform_command("echo hi")
            assert result == "echo hi"


# ── T4.6: Gateway restart resilience ──────────────────────────────


class TestGatewayRestartResilience:
    """Verify the plugin survives Hermes gateway restarts (module reload)."""

    def test_t46_reload_preserves_register(
        self,
        clean_environment: None,
    ) -> None:
        """After a simulated reload, register() is preserved and transforms work."""
        import sys

        # Collect modules belonging to this plugin.
        plugin_keys = [
            k for k in sys.modules
            if k == "plugin" or k.startswith("plugin.")
        ]

        # Remove them from sys.modules.
        for key in plugin_keys:
            del sys.modules[key]

        try:
            # Reimport fresh.
            import importlib
            import plugin as plugin_reloaded

            importlib.reload(plugin_reloaded)

            assert callable(plugin_reloaded.register)
            assert callable(plugin_reloaded.transform_command)
            assert callable(plugin_reloaded.transform_exec_command)
        finally:
            # Restore modules so later tests are not affected.
            for key in plugin_keys:
                if key in sys.modules:
                    del sys.modules[key]
            import plugin as plugin_restored  # noqa: F401

    def test_t46_reload_preserves_transform_capability(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """After simulated reload, transform_command still wraps correctly."""
        import sys
        import importlib

        install_successful_unshare_shim(tmp_path, monkeypatch)

        plugin_keys = [
            k for k in sys.modules
            if k == "plugin" or k.startswith("plugin.")
        ]
        for key in plugin_keys:
            del sys.modules[key]

        try:
            import plugin as plugin_reloaded

            importlib.reload(plugin_reloaded)

            result = plugin_reloaded.transform_command("echo hello")
            assert "unshare" in result
            assert "--pid" in result
            assert "echo hello" in result
        finally:
            for key in plugin_keys:
                if key in sys.modules:
                    del sys.modules[key]
            import plugin  # noqa: F401

    def test_t46_idempotent_import(
        self,
        clean_environment: None,
    ) -> None:
        """Importing the plugin module twice does not corrupt register state."""
        import importlib

        import plugin as plugin_ref

        importlib.reload(plugin_ref)

        assert callable(plugin_ref.register)
        assert callable(plugin_ref.transform_command)
        assert callable(plugin_ref.transform_exec_command)


# ── T7.1–T7.4: Observability metrics ──────────────────────────────


class TestMetrics:
    """Verify observability counters (T7.1-T7.4)."""

    def test_t71_metrics_disabled_counter(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """T7.1: commands_passed_disabled increments when jail is off."""
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_ENABLED", "0")
        plugin_module.reset_metrics()

        plugin_module.transform_command("echo hi")
        metrics = plugin_module.get_metrics()
        assert metrics.commands_passed_disabled == 1
        assert metrics.commands_wrapped == 0

    def test_t71_metrics_no_unshare_counter(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """T7.1: commands_passed_no_unshare increments when unshare is missing."""
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_ENABLED", "1")
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_COMMAND", "nonexistent-unshare")
        plugin_module.reset_metrics()

        plugin_module.transform_command("echo hi")
        metrics = plugin_module.get_metrics()
        assert metrics.commands_passed_no_unshare == 1
        assert metrics.commands_wrapped == 0

    def test_t71_metrics_wrapped_counter(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """T7.1: commands_wrapped increments on successful wrap."""
        install_successful_unshare_shim(tmp_path, monkeypatch)
        plugin_module.reset_metrics()

        plugin_module.transform_command("echo hi")
        metrics = plugin_module.get_metrics()
        assert metrics.commands_wrapped == 1

    def test_t71_metrics_multiple_calls(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """T7.1: counters accumulate across multiple calls."""
        install_successful_unshare_shim(tmp_path, monkeypatch)
        plugin_module.reset_metrics()

        for _ in range(3):
            plugin_module.transform_command("echo hi")
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_ENABLED", "0")
        plugin_module.transform_command("echo no-jail")
        plugin_module.transform_command("echo no-jail-2")

        metrics = plugin_module.get_metrics()
        assert metrics.commands_wrapped == 3
        assert metrics.commands_passed_disabled == 2

    def test_t72_jail_crash_on_build_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """T7.2: jail_crashes increments when shlex.quote raises."""
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_ENABLED", "1")
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_COMMAND", "/bin/unshare")
        plugin_module.reset_metrics()

        # Monkeypatch shlex.quote to simulate a crash during wrapping.
        import shlex as shlex_mod

        original_quote = shlex_mod.quote
        try:
            shlex_mod.quote = lambda x: (_ for _ in ()).throw(
                RuntimeError("simulated crash")
            )
            result = plugin_module.transform_command("echo hi")
            assert result == "echo hi"  # Passes through on crash
        finally:
            shlex_mod.quote = original_quote

        metrics = plugin_module.get_metrics()
        assert metrics.jail_crashes == 1

    def test_t72_jail_crash_on_budget_exception(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """T7.2: jail_crashes increments when budget check throws."""
        install_successful_unshare_shim(tmp_path, monkeypatch)
        plugin_module.reset_metrics()

        original = plugin_module._max_command_bytes_from_environment
        try:
            plugin_module._max_command_bytes_from_environment = (
                lambda: (_ for _ in ()).throw(RuntimeError("simulated"))
            )
            result = plugin_module.transform_command("echo hi")
            assert result == "echo hi"
        finally:
            plugin_module._max_command_bytes_from_environment = original

        metrics = plugin_module.get_metrics()
        assert metrics.jail_crashes == 1

    def test_t73_byte_budget_rejection_counter(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """T7.3: byte_budget_rejections increments when command exceeds budget."""
        install_successful_unshare_shim(tmp_path, monkeypatch)
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_MAX_COMMAND_BYTES", "10")
        plugin_module.reset_metrics()

        result = plugin_module.transform_command("echo this is a long command")
        assert result == "echo this is a long command"  # Passes through
        metrics = plugin_module.get_metrics()
        assert metrics.byte_budget_rejections == 1

    def test_t73_byte_budget_under_limit_no_rejection(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """T7.3: no budget rejection when command fits."""
        install_successful_unshare_shim(tmp_path, monkeypatch)
        monkeypatch.setenv("HERMES_TERMINAL_JAIL_MAX_COMMAND_BYTES", "999999")
        plugin_module.reset_metrics()

        result = plugin_module.transform_command("echo hi")
        assert "unshare" in result
        metrics = plugin_module.get_metrics()
        assert metrics.byte_budget_rejections == 0
        assert metrics.commands_wrapped == 1

    def test_t74_performance_regression_below_threshold(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """T7.4: no alert when wrap overhead is below 50ms threshold."""
        install_successful_unshare_shim(tmp_path, monkeypatch)
        plugin_module.reset_metrics()

        # Run a command — wrap overhead is nanoseconds, well below 50ms.
        plugin_module.transform_command("echo hi")
        metrics = plugin_module.get_metrics()
        assert metrics.perf_regression_alert_count == 0
        assert metrics.wrap_count == 1
        assert metrics.wrap_time_ns_total > 0

    def test_t74_performance_timing_is_recorded(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """T7.4: wrap_time_ns_total and wrap_count are populated."""
        install_successful_unshare_shim(tmp_path, monkeypatch)
        plugin_module.reset_metrics()

        for _ in range(5):
            plugin_module.transform_command("echo hi")

        metrics = plugin_module.get_metrics()
        assert metrics.wrap_count == 5
        assert metrics.wrap_time_ns_total > 0
        # 5 sub-microsecond wraps should be well under 50ms.
        assert metrics.perf_regression_alert_count == 0

    def test_t74_performance_regression_triggers_above_threshold(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """T7.4: alert triggers when wrap overhead exceeds 50ms threshold."""
        install_successful_unshare_shim(tmp_path, monkeypatch)
        plugin_module.reset_metrics()

        # Prime with 100 fast wraps to establish a low average.
        for _ in range(100):
            plugin_module.transform_command("echo hi")

        # Simulate one slow wrap by directly calling _check_performance_regression.
        slow_ns = 60_000_000  # 60ms — above the 50ms threshold
        plugin_module._check_performance_regression(slow_ns)

        metrics = plugin_module.get_metrics()
        assert metrics.perf_regression_alert_count == 1

    def test_reset_metrics_clears_all(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """reset_metrics() clears all counters to zero."""
        install_successful_unshare_shim(tmp_path, monkeypatch)
        # Metrics already reset by fixture; accumulate some counts.
        plugin_module.transform_command("echo hi")
        assert plugin_module.get_metrics().commands_wrapped >= 1

        plugin_module.reset_metrics()
        metrics = plugin_module.get_metrics()
        assert metrics.commands_wrapped == 0
        assert metrics.commands_passed_disabled == 0
        assert metrics.commands_passed_no_unshare == 0
        assert metrics.jail_crashes == 0
        assert metrics.byte_budget_rejections == 0
        assert metrics.wrap_count == 0
        assert metrics.wrap_time_ns_total == 0
        assert metrics.perf_regression_alert_count == 0
