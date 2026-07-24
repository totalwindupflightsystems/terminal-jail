# Changelog

## [1.1.0] — 2026-07-24

### Phase 11: Interruptor Bash Command Firewall

- **Parser**: Tokenizes shell commands — pipes, redirects, cmd substitution, heredocs, variable expansion, quoting. Fail-open to passthrough on parse errors.
- **Rule Loader**: YAML-based rules from `/etc/terminal-jail/rules.d/` and `~/.config/terminal-jail/rules.d/`. Lexical ordering, user rules override system.
- **Pattern Matcher**: 9 match types — pattern, command, pipeline, subcommand, path, composite, syscall, network, heredoc. Configurable per-rule.
- **Decider**: Blocklist-first, then allowlist, then auto-sandbox, then user rules. First match wins. 27 built-in rules (10 critical blocklist, 8 auto-sandbox, 9 always-allow).
- **Shell Integration**: JSON bridge (`interruptor_bridge.py`) — stdin/stdout protocol between bash CLI wrapper and Python engine. TERMINAL_JAIL_INTERRUPTOR_MODE: enforce/warn/disabled.
- **Testing**: 56 new Interruptor tests (T-I01 through T-I40), 6 integration tests for CLI compose.
- **Performance**: Cold start 0.08ms, warm start 0.027ms, 1KB parse 0.273ms, 500-rule eval 0.864ms.
- **Documentation**: Updated integration spec with 4-layer defense-in-depth diagram.

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
