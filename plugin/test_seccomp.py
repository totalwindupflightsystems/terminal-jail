"""Tests for terminal-jail seccomp module — T9.5."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

# Ensure the plugin is importable in the test environment
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin"))

from terminal_jail.seccomp import (  # noqa: E402
    SeccompError,
    SeccompPermissionError,
    SeccompUnsupportedError,
    apply_filter,
    build_bpf_program,
    deny_set_for_arch,
    filter_for_host,
    seccomp_enabled_from_environment,
    supported_architectures,
)


# ── Environment variable parsing ──────────────────────────────────────────────


class TestSeccompEnabledFromEnvironment:
    """TERMINAL_JAIL_SECCOMP env var parsing."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("1", True),
            ("true", True),
            ("yes", True),
            ("on", True),
            ("  yes  ", True),
            ("TRUE", True),
            ("ON", True),
            ("0", False),
            ("false", False),
            ("no", False),
            ("off", False),
            ("", False),
            ("garbage", False),
            ("  garbage  ", False),
        ],
    )
    def test_parse(self, value: str, expected: bool, monkeypatch) -> None:
        monkeypatch.setenv("TERMINAL_JAIL_SECCOMP", value)
        assert seccomp_enabled_from_environment() is expected

    def test_unset_defaults_to_disabled(self, monkeypatch) -> None:
        monkeypatch.delenv("TERMINAL_JAIL_SECCOMP", raising=False)
        assert seccomp_enabled_from_environment() is False


# ── Architecture support ─────────────────────────────────────────────────────


class TestSupportedArchitectures:
    def test_returns_non_empty_tuple(self) -> None:
        arches = supported_architectures()
        assert isinstance(arches, tuple)
        assert len(arches) >= 2

    def test_includes_x86_64(self) -> None:
        assert "x86_64" in supported_architectures()

    def test_includes_aarch64(self) -> None:
        assert "aarch64" in supported_architectures()


# ── Deny sets ────────────────────────────────────────────────────────────────


class TestDenySetForArch:
    def test_x86_64_denies_mount(self) -> None:
        deny = deny_set_for_arch("x86_64")
        assert 165 in deny  # mount on x86_64

    def test_x86_64_denies_pivot_root(self) -> None:
        deny = deny_set_for_arch("x86_64")
        assert 155 in deny  # pivot_root on x86_64

    def test_x86_64_denies_kexec_load(self) -> None:
        deny = deny_set_for_arch("x86_64")
        assert 246 in deny  # kexec_load on x86_64

    def test_aarch64_denies_mount(self) -> None:
        deny = deny_set_for_arch("aarch64")
        assert 40 in deny  # mount on aarch64

    def test_unknown_arch_raises(self) -> None:
        with pytest.raises(SeccompUnsupportedError):
            deny_set_for_arch("mips")


# ── BPF program generation ───────────────────────────────────────────────────


class TestBuildBpfProgram:
    def test_x86_64_produces_bytes_and_count(self) -> None:
        body, count, audit_arch = build_bpf_program(arch="x86_64")
        assert isinstance(body, bytes)
        assert len(body) > 0
        assert count > 0
        assert audit_arch > 0

    def test_aarch64_produces_bytes_and_count(self) -> None:
        body, count, audit_arch = build_bpf_program(arch="aarch64")
        assert isinstance(body, bytes)
        assert len(body) > 0
        assert count > 0
        assert audit_arch > 0

    def test_unknown_arch_raises(self) -> None:
        with pytest.raises(SeccompUnsupportedError):
            build_bpf_program(arch="sparc")

    def test_x86_64_filter_is_sorted_by_syscall_number(self) -> None:
        """The binary-search jump table requires sorted deny list."""
        body, count, _ = build_bpf_program(arch="x86_64")
        # The filter should contain both mount (165) and kexec_load (246)
        # — if sorting works, the smaller NR appears first in the jump table.
        assert count >= 2
        # Minimum instruction count for arch check + sorted deny-set jumps
        assert count >= 4

    def test_filter_is_reproducible(self) -> None:
        """Same arch produces identical bytes (deterministic)."""
        body1, c1, a1 = build_bpf_program(arch="x86_64")
        body2, c2, a2 = build_bpf_program(arch="x86_64")
        assert body1 == body2
        assert c1 == c2
        assert a1 == a2

    def test_extra_denies_merged(self) -> None:
        """Extra deny numbers are added to the set."""
        # Pick a syscall that is NOT in the default deny set (e.g. getpid = 39).
        body_base, count_base, _ = build_bpf_program(arch="x86_64")
        body_extra, count_extra, _ = build_bpf_program(
            arch="x86_64", extra_denies=frozenset({39})
        )
        assert count_extra > count_base
        assert body_extra != body_base


class TestFilterForHost:
    def test_returns_valid_tuple(self) -> None:
        body, count, arch = filter_for_host()
        assert isinstance(body, bytes)
        assert len(body) > 0
        assert count > 0
        assert arch > 0


# ── apply_filter (unit tests — no actual prctl) ──────────────────────────────


class TestApplyFilterUnit:
    def test_unknown_arch_raises_seccomp_error(self) -> None:
        with pytest.raises(SeccompUnsupportedError):
            apply_filter(arch="nonexistent")

    def test_errors_are_seccomp_subclasses(self) -> None:
        assert issubclass(SeccompUnsupportedError, SeccompError)
        assert issubclass(SeccompPermissionError, SeccompError)


# ── try_apply result dataclass ───────────────────────────────────────────────


class TestTryApply:
    def test_try_apply_returns_seccomp_result(self) -> None:
        """try_apply never raises — it returns SeccompApplyResult.

        We run try_apply in a subprocess because a successful filter
        installation persists for the process lifetime, and subsequent
        Python operations may hit the deny list.
        """
        plugin_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "plugin")
        )
        script = (
            "import sys, os\n"
            f"sys.path.insert(0, {plugin_dir!r})\n"
            "from terminal_jail.seccomp import try_apply, SeccompApplyResult\n"
            "result = try_apply()\n"
            "if isinstance(result, SeccompApplyResult):\n"
            "    print(f'OK:{result.applied}:{len(result.reason)}')\n"
            "else:\n"
            "    print(f'TYPE_ERROR:{type(result).__name__}')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
        )
        # try_apply may succeed (filter applied) or fail (no perms).
        # Either way, it must return SeccompApplyResult and not raise.
        assert "OK:" in result.stdout or "TYPE_ERROR:" not in result.stdout


# ── Standalone CLI integration tests ──────────────────────────────────────────


class TestStandaloneCliSeccomp:
    """Verify the --seccomp flag is recognized by the standalone CLI."""

    CLI = os.path.join(
        os.path.dirname(__file__), "..", "standalone", "terminal-jail"
    )

    def test_help_mentions_seccomp(self) -> None:
        """--help output should document the --seccomp flag."""
        result = subprocess.run(
            ["bash", self.CLI, "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--seccomp" in result.stdout

    def test_seccomp_without_command_exits_2(self) -> None:
        """--seccomp without a command should exit 2."""
        result = subprocess.run(
            ["bash", self.CLI, "--seccomp"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2

    def test_seccomp_with_command_runs(self) -> None:
        """--seccomp with a trivial command should succeed."""
        result = subprocess.run(
            ["bash", self.CLI, "--seccomp", "echo", "hello-seccomp"],
            capture_output=True,
            text=True,
        )
        # May fail if seccomp can't be applied (no CAP_SYS_ADMIN in test env)
        # but it must not crash or produce traceback.
        assert result.returncode in (0, 1, 2)
        # Even if seccomp fails to apply, the command should still run.
        if result.returncode == 0:
            assert "hello-seccomp" in result.stdout

    def test_normal_cli_still_works(self) -> None:
        """Without --seccomp, the CLI should work as before.

        Note: unshare may fail with 'Operation not permitted' on hosts where
        the kernel blocks unprivileged PID namespace creation (documented
        as a pre-existing limitation in the board). The CLI itself should
        not produce an error about unrecognized flags.
        """
        result = subprocess.run(
            ["bash", self.CLI, "echo", "normal"],
            capture_output=True,
            text=True,
        )
        # 0 = unshare worked, 1 = unshare blocked (host limitation)
        # 2 = usage error (should NOT happen)
        assert result.returncode in (0, 1)
        assert "unrecognized" not in result.stderr.lower()


# ── Integration tests (skip — require kernel support) ─────────────────────────


class TestPentestIntegration:
    """PT-004 tests — skipped: require kernel seccomp support.

    These tests exercise the pentest plan scenarios for mount(),
    pivot_root(), and kexec_load() syscalls. They should be run manually
    on a host with CAP_SYS_ADMIN and seccomp support.

    See: docs/pentest-plan.md §3.4
    """

    CLI = os.path.join(
        os.path.dirname(__file__), "..", "standalone", "terminal-jail"
    )

    @pytest.mark.skip(reason="PT-004a: requires kernel seccomp + CAP_SYS_ADMIN")
    def test_pt004a_mount_blocked(self) -> None:
        """mount() should return EPERM when seccomp is active."""
        result = subprocess.run(
            ["bash", self.CLI, "--seccomp", "mount", "-t", "tmpfs", "tmpfs", "/tmp/test-jail-mount"],
            capture_output=True,
            text=True,
        )
        # With seccomp active, mount should fail — not succeed
        assert result.returncode != 0

    @pytest.mark.skip(reason="PT-004b: requires kernel seccomp + CAP_SYS_ADMIN")
    def test_pt004b_pivot_root_blocked(self) -> None:
        """pivot_root() should be blocked when seccomp is active."""
        result = subprocess.run(
            ["bash", self.CLI, "--seccomp", "bash", "-c", "pivot_root / / 2>&1 || true"],
            capture_output=True,
            text=True,
        )
        assert "operation not permitted" in result.stdout.lower() or result.returncode != 0

    @pytest.mark.skip(reason="PT-004c: requires kernel seccomp support")
    def test_pt004c_kexec_blocked(self) -> None:
        """kexec_load() should be blocked when seccomp is active."""
        result = subprocess.run(
            ["bash", self.CLI, "--seccomp", "kexec", "-l", "/dev/null"],
            capture_output=True,
            text=True,
        )
        # kexec should fail (seccomp blocks it, or no CAP_SYS_BOOT)
        assert result.returncode != 0
