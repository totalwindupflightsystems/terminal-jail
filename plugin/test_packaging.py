"""Packaging contract tests (TJ-DF-006).

Fast, network-free guard that ``pip install -e .`` exposes ``terminal_jail``
as the installed TOP-LEVEL package. Parses pyproject.toml directly via
tomllib (stdlib) — no subprocess, no venv, no network — so it runs in CI in
well under 2s.

If this test fails, the packaging config was reverted or drifted. The
consequences of that are concrete:

- standalone/terminal-jail L97 bridge fallback #4
  (``import terminal_jail.interruptor_bridge``) can never resolve via pip;
- standalone/seccomp-loader.py:61 (``from terminal_jail.seccomp import ...``)
  can never resolve via pip;
- ``[tool.setuptools.package-data] "terminal_jail" = ["rules/*.yaml"]`` is
  keyed on a package that is not installed, so rules/*.yaml never ships in a
  wheel.

The full fresh-venv install probe lives in test_install.py as an integration
test; this module is the fast guard that runs on every CI pass.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


@pytest.fixture(scope="module")
def pyproject() -> dict:
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


def test_packages_find_exposes_terminal_jail_as_top_level(pyproject: dict) -> None:
    """The finder must discover terminal_jail as a TOP-LEVEL package.

    ``where = ["plugin"]`` + ``include = ["terminal_jail*"]`` makes the
    package at plugin/terminal_jail/ install as top-level ``terminal_jail``
    (not ``plugin.terminal_jail``), which is what the standalone bridge
    fallback and seccomp-loader import.
    """
    find = pyproject["tool"]["setuptools"]["packages"]["find"]
    assert find["where"] == ["plugin"], (
        f"packages.find.where = {find['where']!r}; expected ['plugin'] so "
        "plugin/terminal_jail is discovered as top-level terminal_jail"
    )
    include = find["include"]
    assert "terminal_jail*" in include, (
        f"packages.find.include = {include!r}; expected it to contain "
        "'terminal_jail*'"
    )


def test_package_data_keyed_on_terminal_jail(pyproject: dict) -> None:
    """rules/*.yaml must be keyed on the package that actually ships."""
    package_data = pyproject["tool"]["setuptools"]["package-data"]
    assert "terminal_jail" in package_data, (
        "package-data must be keyed on 'terminal_jail' (the installed "
        "top-level package)"
    )
    assert "rules/*.yaml" in package_data["terminal_jail"]


def test_package_data_rules_exist_on_disk() -> None:
    """The rules dir the package-data glob refers to must exist."""
    rules = PROJECT_ROOT / "plugin" / "terminal_jail" / "rules"
    assert rules.is_dir(), f"rules dir missing: {rules}"
    assert list(rules.glob("*.yaml")), f"no rules/*.yaml under {rules}"


def test_terminal_jail_package_exists_at_plugin_dir() -> None:
    """The package the finder must discover actually exists."""
    pkg = PROJECT_ROOT / "plugin" / "terminal_jail"
    assert (pkg / "__init__.py").is_file(), (
        f"plugin/terminal_jail/__init__.py missing: {pkg}"
    )
