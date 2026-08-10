# Terminal Jail

Defense-in-depth terminal command containment for Hermes Agent. Three layers: a systemd drop-in with lightweight hardening (process-visibility, privilege, and cgroup bounds — the full PID-namespace profile is staged, not active), Hermes plugin observability (metrics + logging), and a standalone CLI wrapper (portable PID namespace containment).

> **New here?** Start with the [Quick Start guide](docs/quickstart.md) — it covers which component fits your use case, install + verify steps for every path, and a FAQ.

## Architecture

| Layer | Role | Mechanism |
|---|---|---|
| **systemd drop-in** | LIGHTWEIGHT — process-visibility, privilege, cgroup bounds (4 active directives: `ProtectProc=invisible`, `NoNewPrivileges=true`, `ProtectControlGroups=true`, `TasksMax=256`) | Does NOT create a PID namespace. The full profile (`PrivateUsers`, `RestrictNamespaces`, network/fs hardening) is commented out pending per-host verification |
| **Hermes Plugin** | Observability only | `pre_tool_call` (command visibility), `transform_terminal_output` (output annotation), byte-budget enforcement, metrics export |
| **Standalone CLI** | Portable PID namespace wrapper | `unshare --pid --fork --mount-proc --kill-child=SIGKILL` for manual use outside Hermes or without systemd |

## How It Works

**The plugin does NOT wrap commands.** Hermes core has no pre-execution command-transform hook — `pre_tool_call` only supports block/allow decisions. The plugin observes terminal commands and exports metrics, but PID namespace isolation comes from the systemd layer.

```bash
# CLI only — the sole component that wraps commands:
./standalone/terminal-jail echo "I'm in a PID namespace"
# → unshare --pid --fork --mount-proc --kill-child=SIGKILL bash -c 'echo "I'"'"'m in a PID namespace"'
# On hosts that deny unprivileged PID namespaces (unshare: Operation not
# permitted, EPERM), fall back to --user (runs as nobody=65534, /proc shows
# host PIDs):
./standalone/terminal-jail --user echo "I'm in a PID namespace"
```

The `--kill-child=SIGKILL` flag ensures that when the namespace init exits, every descendant is immediately killed — even processes that double-fork or change session leaders.

## Components

| Component | Path | Purpose |
|---|---|---|
| systemd Drop-in | `systemd/90-terminal-jail-hardening.conf` | LIGHTWEIGHT hardening — 4 active directives (process visibility, no-new-privileges, cgroup protection, task bound). NOT a PID namespace boundary; the full isolation profile is staged/commented. |
| Hermes Plugin | `plugin/terminal_jail/` | Observability: `pre_tool_call` and `transform_terminal_output` hooks. Metrics, logging, byte-budget enforcement. Does NOT wrap commands. |
| Standalone CLI | `standalone/terminal-jail` | Portable `unshare` wrapper for use outside Hermes or without systemd |
| Deploy Shim | `standalone/terminal-jail-sh` | SHELL replacement for the Hermes gateway: wraps every shell invocation with `setpriv --no-new-privs` + `--user --seccomp` + the interruptor. Deploy-specific — paths configurable via `TERMINAL_JAIL_HOME` / `TERMINAL_JAIL_BRIDGE` / `TERMINAL_JAIL_CLI` (defaults target `/usr/local/lib/terminal-jail`). See `docs/deploy-to-karahermes.md` |
| Interruptor Engine | `plugin/terminal_jail/interruptor/` | Bash command firewall — parser, matcher, decider, 29 built-in rules, JSON bridge for CLI integration |

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

### Built-in Rules (29 total)

Counts verified from the engine (`BUILTIN_BLOCKLIST` / `BUILTIN_SANDBOX` / `BUILTIN_ALLOWLIST` in
`plugin/terminal_jail/interruptor/`): **11 critical blocklist, 8 auto-sandbox, 10 always-allow**.
Rule IDs are stable — tests assert behavior by ID.

- **11 Critical Blocklist** (priority 1000, evaluated first, cannot be removed — only overridden to `warn` by a same-ID user rule):
  - `builtin-kill-all` — mass process kill (`kill -9 -1`)
  - `builtin-killpg-pid1` — process-group kill targeting PID 1 or own process group (`os.killpg(0/1, …)`, `kill(-1/0, …)`)
  - `builtin-fork-bomb` — fork bomb pattern (`:(){ :|:& };:`)
  - `builtin-rm-rf-root` — recursive root removal (`rm -rf /`; order-independent recursive + force flags, TJ-DF-001)
  - `builtin-dd-root` — raw device write (`dd of=/dev/sd*`)
  - `builtin-mkfs` — filesystem creation (`mkfs.*`)
  - `builtin-fdisk` — partition manipulation (`fdisk`)
  - `builtin-chmod-777-root` — world-writable root (`chmod 777 /`; `chmod 000 /` is NOT blocked — scope is the world-writable variant)
  - `builtin-echo-to-system` — redirect output to system paths (`echo … > /etc/…` etc.)
  - `builtin-curl-pipe-shell` — `curl|sh` / `wget|sh` pipe-to-shell
  - `builtin-sudo` — privilege escalation (`sudo`)
- **8 Auto-Sandbox** (wrapped in `unshare --user --pid --fork --kill-child=SIGKILL`):
  - `auto-pytest` — `pytest|tox|nose`
  - `auto-npm-test` — `npm test` / `npx vitest|jest`
  - `auto-go-test` — `go test`
  - `auto-make` — `make`
  - `auto-pip` — `pip install` / `pip3 install`
  - `auto-cargo` — `cargo build|test`
  - `auto-gcc` — `gcc|g++|clang++` compilation
  - `auto-script` — script execution (`./foo.sh`, `bash foo.py`, etc.)
- **10 Always-Allow** (skip further evaluation when matched):
  - `allow-echo` — `echo`
  - `allow-ls` — `ls`
  - `allow-pwd` — `pwd`
  - `allow-cat-safe` — `cat` on non-sensitive paths (not `/etc`, `/boot`, `/proc`, `/sys`)
  - `allow-grep` — `grep`
  - `allow-find-safe` — `find` without `-exec`/`-delete`
  - `allow-git-read` — `git status|log|diff`
  - `allow-python-version` — `python … --version`
  - `allow-which` — `which` / `command -v`
  - `allow-cd` — `cd`

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

> **Host limitation:** the first example requires an unprivileged PID
> namespace (`unshare --pid`). On hosts that deny it (e.g. this one —
> `unshare: unshare failed: Operation not permitted`, EPERM), use the `--user`
> fallback instead: `./standalone/terminal-jail --user echo "I'm in a PID
> namespace"` (runs as nobody=65534; `/proc` shows host PIDs). See
> [Host Limitations](#host-limitations).

### Plugin (Hermes)

The plugin registers two hooks for observability:

- `pre_tool_call` — visibility into terminal commands (can block/allow, cannot modify)
- `transform_terminal_output` — output annotation (appends jail status)

**Important:** The plugin is observability-only — Hermes core has no pre-execution command-transform hook, so the plugin cannot wrap commands. Former wrapping functions (`transform_command`/`transform_exec_command`) were removed in v1.1.x as dead code (TJ-GAP-010). See `specs/integration.md` for the full architectural rationale (HOOK-GAP-03).

Configuration via environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `HERMES_TERMINAL_JAIL_ENABLED` | `true` | Enable/disable plugin (`true`/`false`/`1`/`0`) |
| `HERMES_TERMINAL_JAIL_COMMAND` | `unshare` | Path to `unshare` binary |
| `HERMES_TERMINAL_JAIL_MAX_COMMAND_BYTES` | `131072` | Max command length for logging |
| `HERMES_TERMINAL_JAIL_LOG_LEVEL` | `WARNING` | Python logging level |
| `HERMES_TERMINAL_JAIL_USER_NS` | `false` | Enable user namespace isolation (`true`/`false`/`1`/`0`) |
| `TERMINAL_JAIL_SECCOMP` ⚠️ | `0` | Enable seccomp BPF filter (`1`/`true`/`yes`/`on`). **Note:** does not use `HERMES_TERMINAL_JAIL_` prefix — legacy naming from pre-plugin seccomp module. |

### systemd Hardening (LIGHTWEIGHT — 4 active directives)

**Important:** the shipped drop-in is *not* a PID namespace isolation boundary.
It activates only `ProtectProc=invisible`, `NoNewPrivileges=true`,
`ProtectControlGroups=true`, and `TasksMax=256` (process-visibility,
privilege, cgroup, and task-count hardening). The stronger directives
(`PrivateUsers=true`, `RestrictNamespaces=true`, network/fs hardening) are
commented out in the file with rationale — they require per-host verification
before activation. The full profile is specified in `specs/systemd.md` and the
staged activation procedure in `docs/deploy-to-karahermes.md`.

For actual PID namespace containment of terminal commands, use the standalone
CLI (`./standalone/terminal-jail <command>`) or a verified full-profile
deployment. See `docs/quickstart.md` for the decision tree.

```bash
sudo cp systemd/90-terminal-jail-hardening.conf \
  /etc/systemd/system/hermes-gateway.service.d/
sudo systemctl daemon-reload
sudo systemctl restart hermes-gateway
```

## Install

### From source (recommended)

```bash
git clone https://github.com/totalwindupflightsystems/terminal-jail.git
cd terminal-jail
./install.sh
```

The installer detects the repository checkout and installs the local
`standalone/terminal-jail` wrapper to `~/.local/bin/terminal-jail` (override
with `TERMINAL_JAIL_INSTALL_DIR`). It never requires root, and it prints the
exact PATH export to run if `~/.local/bin` is not on your PATH.

Release-mode installs (downloading the wrapper from a published release plus
its SHA-256 checksum, verified and atomically installed) are supported by
`install.sh` via `TERMINAL_JAIL_USE_RELEASE=1` with `TERMINAL_JAIL_BASE_URL`,
but no release assets are published yet and release mode is therefore
**opt-in only** — without the flag the installer refuses instead of hitting a
dead URL. The git-clone path above is the supported install path.

## Graceful Degradation

Every layer degrades independently:

- **systemd drop-in**: optional — gateway runs without it. Provides process-visibility/privilege/cgroup hardening only; it is NOT a PID namespace boundary (the stronger directives are staged).
- **Plugin**: observes and logs. Returns command unchanged if disabled. Does not block execution.
- **CLI**: exits with code 2 and a message if `unshare` not found, not on Linux, or namespace creation fails.

## Requirements

- Linux (kernel 3.8+ for user namespaces, 4.3+ for `--kill-child`)
- `util-linux` 2.32+ (`unshare` with `--kill-child`)
- `bash`
- systemd (for the primary isolation layer)

## Host Limitations

`unshare --mount-proc` requires privileges unavailable in unprivileged user namespaces on some distributions. On Ubuntu 26.04 (kernel 7.0.0-27), the CLI and plugin wrapping functions will fail. This is a host kernel policy limitation, not a code defect. The systemd layer provides process-visibility and privilege hardening (`ProtectProc=invisible`, `NoNewPrivileges=true`) independently of `unshare`, but it does not create a PID namespace (the shipped drop-in's `PrivateUsers`/`RestrictNamespaces` directives are commented out pending verification).

## License

MIT
