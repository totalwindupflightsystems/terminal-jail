# Terminal Jail

Wrap any Hermes terminal command in a Linux PID namespace. Lightweight sandboxing that kills child processes with SIGKILL when the parent exits — no fork bombs, no orphaned processes, no pid-reuse races.

## How It Works

Terminal Jail wraps every command with `unshare --pid --fork --mount-proc --kill-child=SIGKILL`:

```bash
# Before
echo "hello"

# After (via plugin or CLI)
unshare --pid --fork --mount-proc --kill-child=SIGKILL bash -c 'echo "hello"'
```

The `--kill-child=SIGKILL` flag ensures that when the namespace init exits, every descendant is immediately killed — even processes that double-fork or change session leaders.

## Components

| Component | Path | Purpose |
|-----------|------|---------|
| Hermes Plugin | `plugin/terminal_jail/` | `terminal.command.transform` and `terminal.command.transform.exec` hooks |
| Standalone CLI | `standalone/terminal-jail` | Bash wrapper for use outside Hermes |
| systemd Drop-in | `systemd/90-terminal-jail-hardening.conf` | Defense-in-depth hardening for hermes-gateway.service |

## Quick Start

### CLI

```bash
./standalone/terminal-jail echo "I'm in a PID namespace"
./standalone/terminal-jail --help
./standalone/terminal-jail --version
```

### Plugin (Hermes)

The plugin registers two hooks that Hermes calls before every terminal command:

- `terminal.command.transform` — wraps arbitrary commands
- `terminal.command.transform.exec` — wraps exec-path commands

Configuration via environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `HERMES_TERMINAL_JAIL_ENABLED` | `true` | Enable/disable (`true`/`false`/`1`/`0`) |
| `HERMES_TERMINAL_JAIL_COMMAND` | `unshare` | Path to `unshare` binary |
| `HERMES_TERMINAL_JAIL_MAX_COMMAND_BYTES` | `131072` | Max wrapped command length |
| `HERMES_TERMINAL_JAIL_LOG_LEVEL` | `WARNING` | Python logging level |

### systemd Hardening

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

Every layer fails open when its dependency is missing:

- **Plugin**: returns command unchanged if `unshare` not on PATH or disabled via env
- **CLI**: exits with code 2 and a message if `unshare` not found or not on Linux
- **systemd**: drop-in is optional — gateway runs without it

## Requirements

- Linux (kernel 3.8+ for user namespaces, 4.3+ for `--kill-child`)
- `util-linux` 2.32+ (`unshare` with `--kill-child`)
- `bash`

## License

MIT
