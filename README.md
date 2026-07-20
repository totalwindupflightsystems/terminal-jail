# Terminal Jail

Defense-in-depth terminal command containment for Hermes Agent. Three layers: systemd kernel-enforced PID namespace isolation (primary), Hermes plugin observability (metrics + logging), and a standalone CLI wrapper (portable fallback).

## Architecture

| Layer | Role | Mechanism |
|---|---|---|
| **systemd drop-in** | PRIMARY — PID namespace isolation | `PrivateUsers=true`, `ProtectProc=invisible`, `RestrictNamespaces=true`, `NoNewPrivileges=true`, `TasksMax=256`, `RestrictAddressFamilies` |
| **Hermes Plugin** | Observability only | `pre_tool_call` (command visibility), `transform_terminal_output` (output annotation), byte-budget enforcement, metrics export |
| **Standalone CLI** | Portable PID namespace wrapper | `unshare --pid --fork --mount-proc --kill-child=SIGKILL` for manual use outside Hermes or without systemd |

## How It Works

**The plugin does NOT wrap commands.** Hermes core has no pre-execution command-transform hook — `pre_tool_call` only supports block/allow decisions. The plugin observes terminal commands and exports metrics, but PID namespace isolation comes from the systemd layer.

```bash
# CLI only — the sole component that wraps commands:
./standalone/terminal-jail echo "I'm in a PID namespace"
# → unshare --pid --fork --mount-proc --kill-child=SIGKILL bash -c 'echo "I'"'"'m in a PID namespace"'
```

The `--kill-child=SIGKILL` flag ensures that when the namespace init exits, every descendant is immediately killed — even processes that double-fork or change session leaders.

## Components

| Component | Path | Purpose |
|---|---|---|
| systemd Drop-in | `systemd/90-terminal-jail-hardening.conf` | PRIMARY — kernel-enforced PID namespace isolation via `PrivateUsers`, `ProtectProc`, `RestrictNamespaces` |
| Hermes Plugin | `plugin/terminal_jail/` | Observability: `pre_tool_call` and `transform_terminal_output` hooks. Metrics, logging, byte-budget enforcement. Does NOT wrap commands. |
| Standalone CLI | `standalone/terminal-jail` | Portable `unshare` wrapper for use outside Hermes or without systemd |

## Quick Start

### CLI

```bash
./standalone/terminal-jail echo "I'm in a PID namespace"
./standalone/terminal-jail --help
./standalone/terminal-jail --version
```

### Plugin (Hermes)

The plugin registers two hooks for observability:

- `pre_tool_call` — visibility into terminal commands (can block/allow, cannot modify)
- `transform_terminal_output` — output annotation (appends jail status)

**Important:** The plugin's `transform_command()` and `transform_exec_command()` functions exist in the codebase and are tested (87 tests pass), but they are NOT wired to any execution hook. Hermes core has no pre-execution command-transform hook. See `specs/integration.md` for the full architectural rationale (HOOK-GAP-03).

Configuration via environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `HERMES_TERMINAL_JAIL_ENABLED` | `true` | Enable/disable plugin (`true`/`false`/`1`/`0`) |
| `HERMES_TERMINAL_JAIL_COMMAND` | `unshare` | Path to `unshare` binary |
| `HERMES_TERMINAL_JAIL_MAX_COMMAND_BYTES` | `131072` | Max command length for logging |
| `HERMES_TERMINAL_JAIL_LOG_LEVEL` | `WARNING` | Python logging level |

### systemd Hardening (PRIMARY isolation)

```bash
sudo cp systemd/90-terminal-jail-hardening.conf \
  /etc/systemd/system/hermes-gateway.service.d/
sudo systemctl daemon-reload
sudo systemctl restart hermes-gateway
```

## Install

```bash
curl -fsSL https://github.com/totalwindupflightsystems/terminal-jail/releases/download/v0.1.0/install.sh | sh
```

Or set a custom install directory:

```bash
TERMINAL_JAIL_INSTALL_DIR=/usr/local/bin curl -fsSL ... | sh
```

## Graceful Degradation

Every layer degrades independently:

- **systemd drop-in**: optional — gateway runs without it. When deployed, it is the authoritative containment boundary.
- **Plugin**: observes and logs. Returns command unchanged if disabled. Does not block execution.
- **CLI**: exits with code 2 and a message if `unshare` not found, not on Linux, or namespace creation fails.

## Requirements

- Linux (kernel 3.8+ for user namespaces, 4.3+ for `--kill-child`)
- `util-linux` 2.32+ (`unshare` with `--kill-child`)
- `bash`
- systemd (for the primary isolation layer)

## Host Limitations

`unshare --mount-proc` requires privileges unavailable in unprivileged user namespaces on some distributions. On Ubuntu 26.04 (kernel 7.0.0-27), the CLI and plugin wrapping functions will fail. This is a host kernel policy limitation, not a code defect. The systemd layer (`PrivateUsers=true`, `ProtectProc=invisible`) provides PID isolation independently of `unshare`.

## License

MIT
