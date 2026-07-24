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
| Interruptor Engine | `plugin/terminal_jail/interruptor/` | Bash command firewall — parser, matcher, decider, 27 built-in rules, JSON bridge for CLI integration |

## Interruptor Bash Command Firewall (v1.1.0)

The Interruptor is a bash command firewall that sits between the LLM and shell execution. It intercepts every command, parses it, evaluates it against a rule set, and decides: **allow**, **block**, or **modify** (auto-sandbox).

### Quick Start

```bash
# Test the JSON bridge directly
echo '{"command": "echo hello"}' | python3 plugin/terminal_jail/interruptor_bridge.py
# → {"action":"allow","command":"echo hello",...}

echo '{"command": "rm -rf /"}' | python3 plugin/terminal_jail/interruptor_bridge.py
# → {"action":"block","command":"rm -rf /","rule_id":"I-BLOCK-001",...}

# Via standalone CLI with interruptor
USE_INTERRUPTOR=1 ./standalone/terminal-jail echo "hello"
TERMINAL_JAIL_INTERRUPTOR_MODE=warn ./standalone/terminal-jail rm -rf /
TERMINAL_JAIL_INTERRUPTOR_MODE=disabled ./standalone/terminal-jail --no-interruptor echo "test"
```

### Architecture

| Layer | Role | Mechanism |
|-------|------|-----------|
| **Parser** | Tokenize shell commands | Handles pipes, redirects, cmd substitution, heredocs, quoting, variable expansion |
| **Rule Loader** | Load YAML rules | `/etc/terminal-jail/rules.d/` (system) → `~/.config/terminal-jail/rules.d/` (user) in lexical order |
| **Pattern Matcher** | 9 match types | pattern, command, pipeline, subcommand, path, composite, syscall, network, heredoc |
| **Decider** | Evaluate priority | Blocklist (first) → allowlist → auto-sandbox → user rules. First match wins |

### Built-in Rules (27 total)

- **10 Critical Blocklist**: `rm -rf /`, `dd of=/dev/sda`, `mkfs.*`, `chmod 000 /`, `wget|curl pipe-to-shell`, `:(){ :|:& };:`, etc.
- **8 Auto-Sandbox**: `sudo`, `su`, `chown/chmod` on system paths, `mount/umount`, `passwd`, `apt/pacman install`
- **9 Always-Allow**: `echo`, `ls`, `cat`, `cd`, `pwd`, `which`, `head/tail`, `grep`, basic arithmetic `test/[`

### Modes

| Mode | Behavior |
|------|----------|
| `enforce` (default) | Blocked commands exit 126 with formatted block output |
| `warn` | Print warning message but allow command through |
| `disabled` | Bypass the interruptor entirely |

Set via `TERMINAL_JAIL_INTERRUPTOR_MODE` env var or `--no-interruptor` flag on the CLI.

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
| `HERMES_TERMINAL_JAIL_USER_NS` | `false` | Enable user namespace isolation (`true`/`false`/`1`/`0`) |
| `TERMINAL_JAIL_SECCOMP` ⚠️ | `0` | Enable seccomp BPF filter (`1`/`true`/`yes`/`on`). **Note:** does not use `HERMES_TERMINAL_JAIL_` prefix — legacy naming from pre-plugin seccomp module. |

### systemd Hardening (PRIMARY isolation)

```bash
sudo cp systemd/90-terminal-jail-hardening.conf \
  /etc/systemd/system/hermes-gateway.service.d/
sudo systemctl daemon-reload
sudo systemctl restart hermes-gateway
```

## Install

```bash
curl -fsSL https://github.com/totalwindupflightsystems/terminal-jail/releases/download/v1.0.0/install.sh | sh
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
