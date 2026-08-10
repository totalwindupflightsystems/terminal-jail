# Terminal Jail Quick Start

## 1. Problem statement

Hermes Agent (and any LLM agent) runs terminal commands with the privileges
of its host account. A single destructive command — `rm -rf /`, `dd
of=/dev/sda`, `mkfs.*`, a fork bomb, `curl | sh` — can destroy the host or
its data. **Terminal Jail** is a defense-in-depth toolkit that contains
terminal commands: it puts them in a PID namespace, filters dangerous
patterns before execution, drops privileges, and applies a seccomp filter.

It is *defense in depth*, not a full sandbox: each layer contributes a
specific property, and no single layer is a complete security boundary (see
[docs/threat-model.md](threat-model.md) for what is and is not guaranteed).

## 2. Which component is for you?

| You want to... | Use | How |
|---|---|---|
| Contain a single command in a PID namespace, manually | **Standalone CLI** (`standalone/terminal-jail`) | `terminal-jail <command> [args...]` |
| Block dangerous patterns before they run (firewall) | **Interruptor** (built into the CLI, on by default) | `terminal-jail rm -rf /` → blocked, exit 126 |
| Add privilege dropping + syscall filtering | **CLI flags** | `terminal-jail --user --seccomp <command>` |
| Observe + log Hermes terminal commands, enforce byte budgets | **Hermes plugin** (`plugin/terminal_jail/`) | See §4 |
| Harden the Hermes gateway service itself | **systemd drop-in** (`systemd/90-terminal-jail-hardening.conf`) | See §5 — lightweight (4 directives), NOT a PID namespace boundary |
| Replace the Hermes gateway shell with a jailed shell | **Deploy shim** (`standalone/terminal-jail-sh` + `docs/deploy-to-karahermes.md`) | Host-specific; hardcoded paths must be adjusted |

**TL;DR:** individual commands → standalone CLI. Firewall → interruptor
(default on). The gateway service → systemd drop-in + plugin. Full
PID-namespace containment for everything Hermes runs → deploy shim
(see the deploy guide).

## 3. Install and verify

### 3a. Standalone CLI

```bash
# From source (recommended until release assets are published)
git clone https://github.com/totalwindupflightsystems/terminal-jail.git
cd terminal-jail
./install.sh        # installs to ~/.local/bin/terminal-jail (no root needed)
```

Verify:

```bash
~/.local/bin/terminal-jail --version   # → terminal-jail 1.1.0
~/.local/bin/terminal-jail echo "in jail"          # runs in a PID namespace
~/.local/bin/terminal-jail rm -rf /                # → COMMAND BLOCKED, exit 126
```

If `~/.local/bin` is not on your PATH, run the export the installer printed,
or use the full path above.

### 3b. Interruptor modes

```bash
TERMINAL_JAIL_INTERRUPTOR_MODE=warn terminal-jail rm -rf /    # warns, allows
TERMINAL_JAIL_INTERRUPTOR_MODE=disabled terminal-jail rm -rf / # bypasses firewall
terminal-jail --no-interruptor echo "bypass"                   # same, per-invocation
```

### 3c. Privilege + syscall hardening

```bash
terminal-jail --user echo "runs as nobody (65534)"   # user namespace
terminal-jail --seccomp echo "seccomp BPF active"    # denies mount/pivot_root/...
```

### 3d. Hermes plugin

```bash
pip install -e .   # from the repo root (installs the plugin/ package tree)
```

(Or add `plugin/` to `HERMES_PLUGINS` — see `specs/plugin.md`.)

The plugin hooks `pre_tool_call` (command visibility, byte-budget
enforcement) and `transform_terminal_output` (jail-status annotation). It
does **not** wrap or modify commands — Hermes core has no pre-execution
command-transform hook. Verify with the plugin test suite:

```bash
python3 -m pytest plugin/test_plugin.py -q
```

### 3e. systemd drop-in (gateway hardening)

```bash
sudo cp systemd/90-terminal-jail-hardening.conf \
  /etc/systemd/system/hermes-gateway.service.d/
sudo systemctl daemon-reload
sudo systemctl restart hermes-gateway
sudo systemd-analyze security hermes-gateway.service   # see the score
```

**Note:** the shipped drop-in activates only 4 directives
(`ProtectProc=invisible`, `NoNewPrivileges=true`,
`ProtectControlGroups=true`, `TasksMax=256`). It is lightweight hardening,
**not** a PID namespace boundary. The stronger directives
(`PrivateUsers=true`, `RestrictNamespaces=true`, network/fs hardening) are
commented out pending per-host verification — follow
[docs/deploy-to-karahermes.md](deploy-to-karahermes.md) to stage them.

Verify the drop-in is loaded:

```bash
systemctl show hermes-gateway.service -p ProtectProc -p NoNewPrivileges
```

### 3f. Full gateway containment (advanced)

For actual PID-namespace containment of every command the gateway runs,
follow [docs/deploy-to-karahermes.md](deploy-to-karahermes.md) — it installs
`/usr/local/bin/terminal-jail-sh` as the gateway's `SHELL`, wrapping every
shell invocation with `setpriv --no-new-privs` + the CLI's
`--user --seccomp` flags plus the interruptor firewall.

## 4. FAQ / Troubleshooting

**`unshare` fails with "Operation not permitted"?**
The host kernel or container policy denies namespace creation. The CLI
passes `unshare`'s error through unchanged. Workarounds: use `--user`
(requires user-namespace support), or deploy the systemd drop-in (which does
not need `unshare`). Known limitation on Ubuntu 26.04 (kernel 7.0.0-27):
`--mount-proc` fails in unprivileged user namespaces — see README "Host
Limitations".

**`terminal-jail: unshare is required`?**
Install util-linux (`sudo apt install util-linux` or your distro's package).

**A command I expected to be blocked ran anyway?**
Check the mode: `TERMINAL_JAIL_INTERRUPTOR_MODE` (default `enforce`). In
`warn` mode the firewall prints `WARN: would have blocked` but allows
execution. Also, only commands matching the 27 built-in rules are blocked —
the interruptor is a pattern firewall, not a policy sandbox (see
`specs/interruptor.md`).

**The interruptor bridge is not available (warning or block on stderr)?**
The CLI resolves `plugin/terminal_jail/interruptor_bridge.py` in this order:
`TERMINAL_JAIL_BRIDGE` (explicit path), `../plugin/` next to the wrapper
(repository checkout), the installed lib layout
(`~/.local/lib/terminal-jail/plugin/` — shipped by `./install.sh`), then the
Python module path (`pip install -e .` from the repo root makes the bridge
importable). If the bridge is genuinely missing, enforce mode FAILS CLOSED
(exits 126 with a `COMMAND BLOCKED` box) instead of running unguarded; use
`TERMINAL_JAIL_INTERRUPTOR_MODE=warn` only if you explicitly accept the risk.

**Why does `--user` show host PIDs in `/proc`?**
User namespaces cannot mount a namespace-local `/proc` unprivileged. This is
documented behavior — `--user` trades `/proc` isolation for UID isolation.

**Does the plugin block commands?**
No. `pre_tool_call` can block/allow at the Hermes level, but the plugin is
observability-first; the interruptor in the CLI/shim is the command
firewall.

**How do I roll back the systemd drop-in?**
```bash
sudo rm /etc/systemd/system/hermes-gateway.service.d/90-terminal-jail-hardening.conf
sudo systemctl daemon-reload && sudo systemctl restart hermes-gateway
```
The file itself contains the full rollback procedure.

**Where are the rules defined?**
27 built-in rules in the engine; user rules load from
`/etc/terminal-jail/rules.d/` and `~/.config/terminal-jail/rules.d/`
(lexical order, user overrides system). See `specs/interruptor.md`.

## 5. Next steps

- [specs/integration.md](specs/integration.md) — architecture & defense-in-depth layers
- [docs/threat-model.md](threat-model.md) — what Terminal Jail does and does not prevent
- [docs/supply-chain.md](supply-chain.md) — release & supply-chain integrity
- [docs/pentest-plan.md](pentest-plan.md) — adversarial verification plan
- [docs/COMPATIBILITY.md](COMPATIBILITY.md) — host/kernel compatibility matrix
