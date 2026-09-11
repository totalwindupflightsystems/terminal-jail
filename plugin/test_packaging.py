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

import subprocess
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
PROBE_SCRIPT = PROJECT_ROOT / "scripts" / "pidns-capability-probe.py"


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


def test_shipped_rules_yaml_mirrors_engine_builtin_ids() -> None:
    """The shipped default rules file must mirror the engine's BUILTIN_* rules.

    TJ-GAP-032: 00-builtins.yaml shipped 28 ids while the engine documents 29
    (11 blocklist / 8 sandbox / 10 allow) — builtin-killpg-pid1 was missing
    from the YAML mirror, so an operator installing the default rules package
    got counts contradicting the README and a blocklist that didn't match the
    documented engine. The YAML and the Python BUILTIN_* constants must stay
    in sync (same rule IDs, same per-layer counts).
    """
    import yaml
    from terminal_jail.interruptor.allowlist import BUILTIN_ALLOWLIST
    from terminal_jail.interruptor.blocklist import BUILTIN_BLOCKLIST
    from terminal_jail.interruptor.sandbox import BUILTIN_SANDBOX
    rules_yaml = (
        PROJECT_ROOT / "plugin" / "terminal_jail" / "rules" / "00-builtins.yaml"
    )
    data = yaml.safe_load(rules_yaml.read_text())
    yaml_ids = {rule["id"] for rule in data["rules"]}

    engine_ids = {
        rule.id
        for rule in (
            list(BUILTIN_BLOCKLIST)
            + list(BUILTIN_SANDBOX)
            + list(BUILTIN_ALLOWLIST)
        )
    }

    assert yaml_ids == engine_ids, (
        "YAML mirror drifted from engine BUILTIN_* constants; "
        f"only-in-yaml: {sorted(yaml_ids - engine_ids)}, "
        f"only-in-engine: {sorted(engine_ids - yaml_ids)}"
    )

    # Per-layer counts must match the documented engine (11/8/10).
    block_ids = {r["id"] for r in data["rules"] if r.get("action") == "block"}
    sandbox_ids = {r["id"] for r in data["rules"] if r.get("action") == "sandbox"}
    allow_ids = {r["id"] for r in data["rules"] if r.get("action") == "allow"}
    assert len(block_ids) == len(BUILTIN_BLOCKLIST), (
        f"blocklist count {len(block_ids)} != engine {len(BUILTIN_BLOCKLIST)}"
    )
    assert len(sandbox_ids) == len(BUILTIN_SANDBOX), (
        f"sandbox count {len(sandbox_ids)} != engine {len(BUILTIN_SANDBOX)}"
    )
    assert len(allow_ids) == len(BUILTIN_ALLOWLIST), (
        f"allowlist count {len(allow_ids)} != engine {len(BUILTIN_ALLOWLIST)}"
    )


def test_shipped_rules_yaml_patterns_match_engine_builtins() -> None:
    """Every shipped YAML pattern must equal its engine builtin pattern.

    TJ-GAP-051: install.sh copies 00-builtins.yaml into
    ~/.config/terminal-jail/rules.d/, the engine loads that dir as USER rules,
    and same-id override REPLACES the builtin in its layer. So the YAML
    patterns ARE the live engine on any host that ran the documented install
    path. Three patterns (auto-script, builtin-fork-bomb, builtin-mkfs) had
    drifted WEAKER than their Python counterparts and flipped 12 verdicts from
    block/modify to allow — invisible to the id/count assertions above.

    The comparison is done on values produced by the engine's own RuleLoader
    (PyYAML escaping applied once, by the loader). Never compare by manually
    un-escaping YAML source: double-unescaping fabricates false mismatches.
    """
    from terminal_jail.interruptor.allowlist import BUILTIN_ALLOWLIST
    from terminal_jail.interruptor.blocklist import BUILTIN_BLOCKLIST
    from terminal_jail.interruptor.rules import RuleLoader
    from terminal_jail.interruptor.sandbox import BUILTIN_SANDBOX
    engine_rules = {
        rule.id: rule
        for rule in (
            list(BUILTIN_BLOCKLIST)
            + list(BUILTIN_SANDBOX)
            + list(BUILTIN_ALLOWLIST)
        )
    }
    rules_dir = PROJECT_ROOT / "plugin" / "terminal_jail" / "rules"
    # user_dir is pinned to a non-existent path so this probe can never be
    # fooled by a stale copy in the host's real user rules dir.
    loaded = RuleLoader(system_dir=str(rules_dir), user_dir="/nonexistent").load_all()

    missing = sorted(set(engine_rules) - {r.id for r in loaded.rules})
    assert not missing, f"shipped YAML is missing engine rule ids: {missing}"
    assert len(loaded.rules) == len(engine_rules), (
        f"shipped YAML loaded {len(loaded.rules)} rules, engine has "
        f"{len(engine_rules)}"
    )

    drift = []
    for rule_id in sorted(engine_rules):
        engine_pattern = engine_rules[rule_id].match.get("pattern", "")
        yaml_rule = loaded.by_id(rule_id)
        assert yaml_rule is not None  # covered by `missing` above
        yaml_pattern = yaml_rule.match.get("pattern", "")
        if yaml_pattern != engine_pattern:
            drift.append(
                f"{rule_id}:\n"
                f"      engine={engine_pattern!r}\n"
                f"      yaml  ={yaml_pattern!r}"
            )
    assert not drift, (
        "shipped YAML pattern drift vs engine BUILTIN_* constants — the YAML "
        "same-id override replaces the builtin, so a weaker mirror silently "
        "weakens live verdicts:\n  " + "\n  ".join(drift)
    )


def test_pidns_capability_probe_is_host_agnostic() -> None:
    """The battery's capability classifier must run on ANY host (TJ-GAP-042).

    It is a classifier, not a gate: exit 0 always, and the verdict is exactly
    one of FULL / DEGRADED / UNKNOWN. A capable host (CI runner) prints FULL,
    a host that refuses unprivileged PID namespaces prints DEGRADED, and any
    unexpected state must still be reported as UNKNOWN rather than crashing.
    """
    assert PROBE_SCRIPT.is_file(), f"probe script missing: {PROBE_SCRIPT}"
    result = subprocess.run(
        ["python3", str(PROBE_SCRIPT)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        f"probe must always exit 0; rc={result.returncode}, "
        f"stderr={result.stderr.strip()!r}"
    )
    verdict = result.stdout.strip()
    assert verdict in ("FULL", "DEGRADED") or verdict.startswith("UNKNOWN"), (
        f"probe printed unexpected verdict: {verdict!r}"
    )
