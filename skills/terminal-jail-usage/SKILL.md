---
name: terminal-jail-usage
description: >-
  How to USE the terminal-jail project for real: what it does, entry points,
  run commands, common pitfalls, and the right-way patterns. Load this skill
  before integrating with or extending terminal-jail. Written from the
  2026-08-10 dogfood run (real install + real command flows).
version: 1.0.0
category: software-development
---

# Terminal Jail — Usage Skill

Defense-in-depth terminal containment for Hermes/LLM agents. The interruptor
(bash command firewall) is the layer that actually does something; the plugin
is observability-only; the systemd drop-in is lightweight hardening (4
directives) — NOT a PID namespace boundary as shipped.

## Entry points

| Component | Path | What it does |
|---|---|---|
| Standalone CLI | `standalone/terminal-jail` (install → `~/.local/bin/terminal-jail`) | `unshare` PID-namespace wrapper + interruptor firewall. THE main tool. |
| Interruptor engine | `plugin/terminal_jail/interruptor/` | Pure-python rule engine: `intercept(cmd)` → allow/block/modify. |
| JSON bridge | `plugin/terminal_jail/interruptor_bridge.py` | stdin/stdout JSON wrapper over the engine — safe to script, never executes. |
| Hermes plugin | `plugin/__init__.py` | Observability hooks only (pre_tool_call logs, transform returns None). |
| Deploy shim | `standalone/terminal-jail-sh` | SHELL replacement for the Hermes gateway (setpriv + seccomp + interruptor). Host-specific. |
| systemd drop-in | `systemd/90-terminal-jail-hardening.conf` | 4 active directives; full profile commented out. |

## Quick start (real commands, verified on Ubuntu 26.04 / kernel 7.0.0-28)

```bash
./install.sh                                     # from a checkout — the supported path
TJ=~/.local/bin/terminal-jail
$TJ --version                                    # terminal-jail 1.1.0
$TJ --user echo hi                               # runs as nobody(65534); rc=0
$TJ --user bash -c 'exit 7'; echo $?             # exit codes pass through → 7
echo hi | $TJ --user cat                         # stdin passes through
$TJ --user fdisk /dev/sda                        # COMMAND BLOCKED box, rc=126
TERMINAL_JAIL_INTERRUPTOR_MODE=warn $TJ --user fdisk /dev/sda   # WARN + allow
TERMINAL_JAIL_INTERRUPTOR_MODE=disabled $TJ --user fdisk /dev/sda
$TJ --no-interruptor --user fdisk /dev/sda       # per-invocation firewall off
```

**Always use `--user` on hosts that deny unprivileged PID namespaces**
(plain `unshare --pid` → EPERM — this host, documented). `--user` trades
/proc isolation for UID isolation (host PIDs visible).

## Firewall probing (no execution — the safe way to test rules)

```bash
echo '{"command": "rm -rf /"}' | python3 plugin/terminal_jail/interruptor_bridge.py
# → {"action":"block","rule_id":"builtin-rm-rf-root",...}
echo '{"command": "echo hi"}' | python3 plugin/terminal_jail/interruptor_bridge.py
# → {"action":"allow",...}
```

Engine-level (fast, no subprocess):
```python
import sys; sys.path.insert(0, "plugin")
from terminal_jail.interruptor import intercept
r = intercept("sudo apt install cowsay")   # → block (builtin-sudo, priority 1000)
```

## Common pitfalls (all hit live on 2026-08-10)

1. **`rm -rf /`-family bypasses**: `rm -rf --no-preserve-root /`,
   `rm -r -f /`, `rm --recursive --force /`, `rm -rf/` are ALLOWED today
   (TJ-DF-001, P0, open). Don't rely on the firewall for these forms.
2. **`--seccomp` is broken as installed** (TJ-DF-002, P0): installed binary
   crashes `ModuleNotFoundError` in the loader. From a repo checkout it
   "works" but only degrades with a warning — the filter can't install
   unprivileged because `PR_SET_NO_NEW_PRIVS` is never set (TJ-DF-003).
   Treat seccomp as NOT ACTIVE until those land.
3. **User YAML rules do nothing** (TJ-DF-004, P1): `~/.config/terminal-jail/rules.d/`
   and `/etc/terminal-jail/rules.d/` are documented but unevaluated. Builtins
   only — edit `plugin/terminal_jail/interruptor/{blocklist,sandbox,allowlist}.py`.
4. **README rule tables are stale** (TJ-DF-005): `chmod 000 /` is NOT
   blocked (only `chmod 777 /`); `mount`/`su`/`passwd`/`apt install`/`chown`
   are NOT sandboxed (they run uncontained); sudo is BLOCKED, not sandboxed.
   Actual counts: 11 block + 8 sandbox + 10 allow = 29 rules.
5. **`pip install -e .` installs `plugin`, not `terminal_jail`** (TJ-DF-006):
   `import terminal_jail` fails after the documented plugin install. Use
   `import plugin` for now, or install via `./install.sh`.
6. **`TERMINAL_JAIL_SECCOMP=1` alone does nothing** (TJ-DF-008): the
   `--seccomp` flag is required.
7. **Enforce mode fails closed** when the bridge is missing/crashes (rc=126
   + box) — that's correct behavior, not a bug; fix the bridge path, don't
   switch to warn mode.

## Right-way patterns

- **Blocking test battery**: engine (`intercept`) → bridge (stdin JSON) →
  CLI (only for block box/exit codes). Never run the dangerous commands
  themselves — the bridge is the safe oracle.
- **Installed-binary testing**: always test BOTH repo layout and
  `TERMINAL_JAIL_INSTALL_DIR=/tmp/x ./install.sh` layout — they diverged
  twice (TJ-GAP-021, TJ-DF-002).
- **Seccomp verification** once TJ-DF-003 lands:
  `$TJ --user --seccomp python3 -c "import ctypes;c=ctypes.CDLL(None);c.mount(b'x',b'y',b'z',0,0)"`
  must exit 159 (SIGSYS). If it prints "running without seccomp", the filter
  didn't install.
- **Sandbox (modify) behavior**: auto-sandboxed commands (pytest, make,
  go test, pip install, ./script.sh) get re-wrapped in a NESTED
  `unshare --user --pid` by the bridge; the CLI must not double-wrap
  (MODIFIED=1 path) or you get EPERM.
- **Host constraint**: this host can't run plain `unshare --pid`; every
  execution test needs `--user`. CI/test suites know this (integration
  tests skip on hosts blocking --mount-proc).

## Board & history

- Board: `.coding-hermes/board/tasks.jsonl` (JSONL v2.1 — append rows in
  that schema; there is no tasks.md anymore).
- Active gaps at last dogfood: TJ-DF-001..009 (2026-08-10). E2E-001 is the
  recurring full-battery tick; NEVER-DONE the audit tick.
- Commits must carry `Co-authored-by: Alexis Okuwa <wojonstech@gmail.com>`
  and pass `gitreins guard` (see AGENTS.md).
