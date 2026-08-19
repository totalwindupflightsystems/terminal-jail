---
name: terminal-jail-usage
description: >-
  How to USE the terminal-jail project for real: what it does, entry points,
  run commands, common pitfalls, and the right-way patterns. Load this skill
  before integrating with or extending terminal-jail. Written from the
  2026-08-10 dogfood run, refreshed 2026-08-19 (all TJ-DF-001..010 fixes
  verified live; new findings TJ-DF-011..014).
version: 1.1.0
category: software-development
---

# Terminal Jail — Usage Skill

Defense-in-depth terminal containment for Hermes/LLM agents. The interruptor
(bash command firewall) is the layer that actually does something; the plugin
is observability-only; the systemd drop-in is lightweight hardening (4
directives) — NOT a PID namespace boundary as shipped.

> **Before trusting any "known gap" list (including this file):** check the
> board (`.coding-hermes/board/tasks.jsonl`) for open tasks first. This
> project's knowledge artifacts went stale once already (TJ-DF-013) — the
> board is the source of truth, the skill is the quickstart.

## Entry points

| Component | Path | What it does |
|---|---|---|
| Standalone CLI | `standalone/terminal-jail` (install → `~/.local/bin/terminal-jail`) | `unshare` PID-namespace wrapper + interruptor firewall. THE main tool. |
| Interruptor engine | `plugin/terminal_jail/interruptor/` | Pure-python rule engine: `intercept(cmd)` → allow/block/modify. |
| JSON bridge | `plugin/terminal_jail/interruptor_bridge.py` | stdin/stdout JSON wrapper over the engine — safe to script, never executes. THE oracle for rule probes. |
| Hermes plugin | `plugin/__init__.py` | Observability hooks only (pre_tool_call logs, transform returns None). |
| Deploy shim | `standalone/terminal-jail-sh` | SHELL replacement for the Hermes gateway (setpriv + seccomp + interruptor). Host-specific. |
| systemd drop-in | `systemd/90-terminal-jail-hardening.conf` | 4 active directives; full profile commented out. |

## Quick start (real commands, verified on Ubuntu 26.04 / kernel 7.0.0-29)

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
/proc isolation for UID isolation (host PIDs visible). NOTE: `--user`
drops the uid to nobody but does NOT scrub `$USER`/`$HOME` env (TJ-DF-014).

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

## User rules (WORKING since TJ-DF-004 — verified live 2026-08-19)

```bash
mkdir -p ~/.config/terminal-jail/rules.d
cat > ~/.config/terminal-jail/rules.d/99-mine.yaml <<'EOF'
rules:
  - id: my-block-touch
    priority: 900
    action: block
    match: {type: command, command: touch}
EOF
$TJ --user touch /tmp/x   # → COMMAND BLOCKED, rc=126
```

- Same-ID rules REPLACE builtins in their layer (builtin-rm-rf-root can be
  overridden). **Pitfall:** an `action: warn` same-ID override currently
  allows SILENTLY with no warning (TJ-DF-012, open) — don't use warn
  overrides for visibility until that lands; env `TERMINAL_JAIL_INTERRUPTOR_MODE=warn`
  DOES surface warnings correctly.
- Rules load from `/etc/terminal-jail/rules.d/` (system) and
  `~/.config/terminal-jail/rules.d/` (user); install.sh ships
  `00-builtins.yaml` to the user dir (TJ-GAP-033).

## Common pitfalls (current as of 2026-08-19)

1. **`chmod -R 777 /` is ALLOWED** (TJ-DF-011, P0, OPEN): the
   world-writable-root rule pattern `chmod\s+777\s+/` can't cross flag
   tokens — `chmod -R 777 /`, `chmod --recursive 777 /`, `chmod a+rwx /`,
   `chmod 7777 /` all pass. The rm -rf family IS fixed (all variants
   blocked) — don't assume chmod got the same treatment.
2. **Same-ID `action: warn` override = silent allow** (TJ-DF-012, P1, OPEN):
   no warning, no reason. Use `TERMINAL_JAIL_INTERRUPTOR_MODE=warn` env for
   visible warnings instead.
3. **`--user` leaks `$USER`/`$HOME`** (TJ-DF-014, P3, OPEN): process runs
   as nobody but env says otherwise. Don't rely on $HOME inside the jail.
4. **seccomp works now** (TJ-DF-002/003 fixed, verified): filter installs
   unprivileged; denies via `SECCOMP_RET_ERRNO|EPERM` (NOT SIGSYS — a
   denied syscall returns EPERM, it doesn't kill). Verify with
   `grep Seccomp /proc/self/status` → `2`, or a ctypes `mount()` probe
   returning errno 1. `TERMINAL_JAIL_SECCOMP=1` alone still does nothing;
   the `--seccomp` flag is required.
5. **Enforce mode fails closed** when the bridge is missing/crashes
   (rc=126 + box) — correct behavior; fix the bridge path, don't switch to
   warn mode.
6. **install.sh local-checkout detection**: must be invoked as
   `./install.sh` (or `install.sh`); `bash /abs/path/install.sh` refuses
   (release mode is opt-in). Intentional, just don't be surprised.
7. **Auto-sandbox (modify)**: pytest/make/go test/pip/script runs get
   wrapped in a nested `unshare --user --pid` — the CLI prints
   `[terminal-jail] Modified: ... → sandboxed` and runs the wrapped
   command; the nested namespace works on this host (PID 1 inside).

## Right-way patterns

- **Blocking test battery**: engine (`intercept`) → bridge (stdin JSON) →
  CLI (only for block box/exit codes). Never run the dangerous commands
  themselves — the bridge is the safe oracle.
- **Installed-binary testing**: always test BOTH repo layout and
  `TERMINAL_JAIL_INSTALL_DIR=/tmp/x ./install.sh` layout — they diverged
  twice (TJ-GAP-021, TJ-DF-002) and are verified converged now.
- **Seccomp verification**: `$TJ --user --seccomp grep Seccomp /proc/self/status`
  must show `Seccomp: 2`; a ctypes mount probe must return errno 1 (EPERM).
- **Host constraint**: this host can't run plain `unshare --pid`; every
  execution test needs `--user`. CI/test suites know this (integration
  tests skip on hosts blocking --mount-proc).
- **Gateway interaction**: the Hermes gateway hardline may block probe
  commands containing literal dangerous tokens (`mkfs`, `dd of=/dev/...`)
  even as bridge DATA — build those strings at runtime in scratch files.

## Board & history

- Board: `.coding-hermes/board/tasks.jsonl` (JSONL v2.1 — append rows in
  that schema; there is no tasks.md anymore).
- Dogfood runs: 2026-08-10 (TJ-DF-001..010 — all complete, verified),
  2026-08-19 (TJ-DF-011..014 — 011/012 security, 013 docs, 014 hygiene).
  E2E-001 is the recurring full-battery tick; NEVER-DONE the audit tick.
- Commits must carry `Co-authored-by: Alexis Okuwa <wojonstech@gmail.com>`
  and pass `gitreins guard` (see AGENTS.md).
