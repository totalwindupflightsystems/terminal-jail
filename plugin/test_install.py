from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SCRIPT = PROJECT_ROOT / "install.sh"

EXPECTED_SHEBANG = "#!/usr/bin/env bash"
FAKE_BINARY = EXPECTED_SHEBANG + "\necho 'terminal-jail v0.1.0'\n"


def _shutil_which(name: str) -> str | None:
    import shutil
    return shutil.which(name)


@pytest.fixture(scope="module")
def install_script() -> Path:
    assert INSTALL_SCRIPT.exists(), f"Installer not found: {INSTALL_SCRIPT}"
    return INSTALL_SCRIPT


def _run_install(
    script: Path,
    *,
    install_dir: str | None = None,
    extra_env: dict[str, str] | None = None,
    test_bin: str | None = None,
) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    env["HOME"] = os.environ.get("HOME", "/tmp")
    if install_dir:
        env["TERMINAL_JAIL_INSTALL_DIR"] = install_dir
    if extra_env:
        env.update(extra_env)
    if test_bin:
        env["PATH"] = test_bin

    return subprocess.run(
        ["sh", str(script)],
        capture_output=True,
        text=False,
        check=False,
        timeout=15,
        env=env,
    )


def _link_tools(test_bin: Path, *tools: str) -> None:
    """Symlink real tools into test_bin."""
    for tool in tools:
        real = _shutil_which(tool)
        if real:
            (test_bin / tool).symlink_to(real)


def _make_server_dir(tmp_path: Path, binary_content: str = FAKE_BINARY) -> Path:
    """Create a fake 'server' directory with terminal-jail and sha256 file."""
    server = tmp_path / "fake-server"
    server.mkdir(exist_ok=True)
    (server / "terminal-jail").write_text(binary_content)
    result = subprocess.run(
        ["sha256sum", str(server / "terminal-jail")],
        capture_output=True, text=True, check=False,
    )
    (server / "terminal-jail.sha256").write_text(result.stdout)
    return server


def _make_mock_curl(test_bin: Path, server_dir: Path) -> None:
    """Create a mock curl that copies from server_dir instead of downloading.

    Uses bash because the fallback parameter expansion needs it.
    """
    curl = test_bin / "curl"
    curl.write_text(
        "#!/bin/bash\n"
        "# Mock curl: copies from fake-server instead of real download\n"
        "# install.sh calls: curl -fsSL URL -o OUTFILE\n"
        "url=\"$2\"\n"
        "outfile=\"$4\"\n"
        f"srcdir='{server_dir}'\n"
        "# Extract filename from URL path\n"
        "filename=$(basename \"$url\")\n"
        "cp \"$srcdir/$filename\" \"$outfile\"\n"
    )
    curl.chmod(0o755)


# ── Basic behaviour ────────────────────────────────────────────────────────

@pytest.mark.standalone_cli
def test_installer_exists_and_is_executable(install_script: Path) -> None:
    assert install_script.exists()
    st = install_script.stat()
    assert st.st_mode & stat.S_IXUSR, "install.sh should be executable"


@pytest.mark.standalone_cli
def test_installer_syntax(install_script: Path) -> None:
    result = subprocess.run(["sh", "-n", str(install_script)], capture_output=True, check=False)
    assert result.returncode == 0, f"Syntax error: {result.stderr.decode()}"


# ── Error: no HOME ─────────────────────────────────────────────────────────

@pytest.mark.standalone_cli
def test_no_home(install_script: Path) -> None:
    result = _run_install(install_script, extra_env={"HOME": ""})
    assert result.returncode == 1
    stderr = result.stderr.decode("utf-8")
    assert "HOME is not set" in stderr


# ── Error: non-Linux OS ────────────────────────────────────────────────────

@pytest.mark.standalone_cli
def test_non_linux_os(install_script: Path, tmp_path: Path) -> None:
    test_bin = tmp_path / "testbin"
    test_bin.mkdir(exist_ok=True)
    _link_tools(test_bin, "bash", "sh")

    fake_uname = test_bin / "uname"
    fake_uname.write_text("#!/bin/sh\necho Darwin\n")
    fake_uname.chmod(0o755)

    result = _run_install(install_script, test_bin=str(test_bin))
    assert result.returncode == 1
    stderr = result.stderr.decode("utf-8")
    assert "requires Linux" in stderr


# ── Error: no downloader ───────────────────────────────────────────────────

@pytest.mark.standalone_cli
def test_no_downloader(install_script: Path, tmp_path: Path) -> None:
    test_bin = tmp_path / "testbin"
    test_bin.mkdir(exist_ok=True)
    _link_tools(test_bin, "bash", "sh", "uname")

    result = _run_install(
        install_script, test_bin=str(test_bin),
        install_dir=str(tmp_path / "install"),
    )
    assert result.returncode == 1
    stderr = result.stderr.decode("utf-8")
    assert "curl or wget" in stderr


# ── Error: no checksum tool ────────────────────────────────────────────────

@pytest.mark.standalone_cli
def test_no_checksum_tool(install_script: Path, tmp_path: Path) -> None:
    test_bin = tmp_path / "testbin"
    test_bin.mkdir(exist_ok=True)
    _link_tools(test_bin, "bash", "sh", "uname", "curl")

    result = _run_install(
        install_script, test_bin=str(test_bin),
        install_dir=str(tmp_path / "install"),
    )
    assert result.returncode == 1
    stderr = result.stderr.decode("utf-8")
    assert "sha256sum or shasum" in stderr


# ── Installation with mocked downloads ────────────────────────────────────

def _setup_full_testbin(tmp_path: Path, server_dir: Path) -> Path:
    """Create test_bin with all needed tools + mock curl."""
    test_bin = tmp_path / "testbin"
    test_bin.mkdir(exist_ok=True)
    _link_tools(test_bin,
        "sh", "bash", "uname", "unshare", "head", "awk", "mkdir",
        "mv", "chmod", "cat", "grep", "rm", "cp",
        "sha256sum", "basename", "dirname",
    )
    _make_mock_curl(test_bin, server_dir)
    return test_bin


@pytest.mark.standalone_cli
def test_successful_install(install_script: Path, tmp_path: Path) -> None:
    install_dir = tmp_path / "install-dir"
    install_dir.mkdir()
    server_dir = _make_server_dir(tmp_path)
    test_bin = _setup_full_testbin(tmp_path, server_dir)

    result = subprocess.run(
        ["sh", str(install_script)],
        capture_output=True, text=False, check=False, timeout=15,
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "PATH": str(test_bin),
            "TERMINAL_JAIL_INSTALL_DIR": str(install_dir),
            "TERMINAL_JAIL_BASE_URL": f"file://{server_dir}",
        },
    )

    stdout = result.stdout.decode("utf-8")
    stderr = result.stderr.decode("utf-8")
    assert result.returncode == 0, f"Install failed (rc={result.returncode}): stderr={stderr}"
    assert "installed to" in stdout
    assert "checksum OK" in stdout
    assert "done." in stdout

    installed = install_dir / "terminal-jail"
    assert installed.exists(), f"Binary not installed at {installed}"
    assert os.access(installed, os.X_OK), "Installed binary not executable"


@pytest.mark.standalone_cli
def test_bad_shebang_rejected(install_script: Path, tmp_path: Path) -> None:
    install_dir = tmp_path / "install-dir"
    install_dir.mkdir()
    server_dir = _make_server_dir(tmp_path, binary_content="#!/bin/false\necho bad\n")
    test_bin = _setup_full_testbin(tmp_path, server_dir)

    result = subprocess.run(
        ["sh", str(install_script)],
        capture_output=True, text=False, check=False, timeout=15,
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "PATH": str(test_bin),
            "TERMINAL_JAIL_INSTALL_DIR": str(install_dir),
            "TERMINAL_JAIL_BASE_URL": f"file://{server_dir}",
        },
    )

    assert result.returncode == 1
    stderr = result.stderr.decode("utf-8")
    assert "bad shebang" in stderr or "does not look like" in stderr


@pytest.mark.standalone_cli
def test_checksum_fail(install_script: Path, tmp_path: Path) -> None:
    install_dir = tmp_path / "install-dir"
    install_dir.mkdir()
    server_dir = _make_server_dir(tmp_path)
    test_bin = _setup_full_testbin(tmp_path, server_dir)

    # Corrupt the checksum file
    (server_dir / "terminal-jail.sha256").write_text(
        "0000000000000000000000000000000000000000000000000000000000000000  terminal-jail\n"
    )

    result = subprocess.run(
        ["sh", str(install_script)],
        capture_output=True, text=False, check=False, timeout=15,
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "PATH": str(test_bin),
            "TERMINAL_JAIL_INSTALL_DIR": str(install_dir),
            "TERMINAL_JAIL_BASE_URL": f"file://{server_dir}",
        },
    )

    assert result.returncode == 1
    stderr = result.stderr.decode("utf-8")
    assert "checksum verification FAILED" in stderr


@pytest.mark.standalone_cli
def test_creates_install_dir(install_script: Path, tmp_path: Path) -> None:
    install_dir = tmp_path / "nested" / "install-dir"
    server_dir = _make_server_dir(tmp_path)
    test_bin = _setup_full_testbin(tmp_path, server_dir)

    result = subprocess.run(
        ["sh", str(install_script)],
        capture_output=True, text=False, check=False, timeout=15,
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "PATH": str(test_bin),
            "TERMINAL_JAIL_INSTALL_DIR": str(install_dir),
            "TERMINAL_JAIL_BASE_URL": f"file://{server_dir}",
        },
    )

    assert result.returncode == 0
    assert install_dir.is_dir(), f"Install dir not created: {install_dir}"
    assert (install_dir / "terminal-jail").exists()


@pytest.mark.standalone_cli
def test_tmp_files_cleaned_after_install(install_script: Path, tmp_path: Path) -> None:
    install_dir = tmp_path / "install-dir"
    install_dir.mkdir()
    server_dir = _make_server_dir(tmp_path)
    test_bin = _setup_full_testbin(tmp_path, server_dir)

    result = subprocess.run(
        ["sh", str(install_script)],
        capture_output=True, text=False, check=False, timeout=15,
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "PATH": str(test_bin),
            "TERMINAL_JAIL_INSTALL_DIR": str(install_dir),
            "TERMINAL_JAIL_BASE_URL": f"file://{server_dir}",
        },
    )

    assert result.returncode == 0
    temps = list(install_dir.glob(".terminal-jail.*"))
    assert len(temps) == 0, f"Temp files left behind: {temps}"
