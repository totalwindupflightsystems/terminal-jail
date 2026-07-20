# Changelog

## [1.0.0] — 2026-07-20

### Plugin Core
- PID namespace isolation via `unshare --pid --fork --mount-proc --kill-child=SIGKILL`
- Observability-only plugin architecture (command wrapping lives in Hermes backend/CLI layers)
- Register-based Hermes hook manifest (`pre_tool_call`, `transform_terminal_output`)
- Configurable log levels via `HERMES_TERMINAL_JAIL_LOG_LEVEL`
- Graceful degrade when `unshare` is missing from PATH

### Standalone CLI
- Universal `terminal-jail` bash wrapper (56 lines)
- Works outside Hermes — wraps any command in a PID namespace
- `--help` and `--version` flags
- Byte-exact exit code propagation

### systemd Hardening
- Graduated `90-terminal-jail-hardening.conf` drop-in (14 directives)
- Safe directives active by default, dangerous ones commented
- Rollback procedure documented (<10s downtime)
- Defense-in-depth: `ProtectSystem=strict`, `PrivateUsers=true`, `RestrictNamespaces=~pid`

### Hermes Core Integration
- `--sandbox` CLI flag submitted as upstream PR (#68216)
- Backend-layer command wrapping (`tools/environments/local.py`)
- `terminal.jail_enabled` config key

### Testing
- 108 unit + integration tests (26 skipped — require real `unshare --mount-proc`)
- Real unshare integration tests: fork bomb containment, killall containment, exit code propagation, stdout/stderr integrity, nested jails, signal handling, performance benchmark, env var isolation
- Standalone CLI tests (15 tests)
- install.sh tests (11 tests)
- Metrics export tests (21 tests)
- Edge-case coverage: NUL bytes, non-str input, budget exceptions

### Observability
- Jail metrics counters (wrapped, passed-through, missing-unshare, crashes)
- Byte budget tracking and rejection logging
- Performance regression alerts (p99 > 50ms)
- DuckBrain metrics exporter

### Documentation
- 4 axiom-level specs (plugin, CLI, systemd, integration)
- 5 architecture decision records (ADR-001 through ADR-005)
- Threat-aware: all Phase 5-6 deployment tasks documented as BLOCKED by host limitations
- CONTRIBUTING.md
