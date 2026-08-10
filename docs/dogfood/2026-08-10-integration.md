# Terminal Jail — Real-Use Integration Report (2026-08-10)

Dogfood run by the coding-hermes-dogfood cron. This report is the answer to
"how do I actually USE terminal-jail, and what breaks?" — written from a
fresh install and real command runs on Ubuntu 26.04 (kernel 7.0.0-28), a host
that **denies unprivileged PID namespaces** (`unshare --pid` → EPERM, a
documented host limitation).

## 1. What it is (one paragraph)

Terminal Jail is a defense-in-depth toolkit for containing terminal commands
run by LLM agents (Hermes). Four layers: (1) a standalone CLI that wraps a
command in a PID namespace via `unshare`; (2) the **interruptor**, a bash
command firewall (11 builtin blocklist rules, 8 auto-sandbox rules, 10
allowlist rules) that decides allow/block/modify BEFORE execution; (3) a
Hermes plugin that only observes (logs command lengths); (4) a systemd
drop-in (4 active hardening directives; full isolation profile staged but
commented out). The interruptor is the layer that actually does something
today.

## 2. Install (the path that works)

```bash
git clone https://github.com/totalwindupflightsystems/terminal-jail.git
cd terminal-jail
./install.sh          # → ~/.local/bin/terminal-jail (no root)
```

Verified: installs the wrapper, the plugin bridge tree, and the seccomp
loader; prints PATH hint. The installed binary finds its bridge and blocks
(`~/.local/bin/terminal-jail fdisk /dev/sda` → exit 126 + COMMAND BLOCKED box).

**Do NOT use `pip install -e .` as a substitute** (quickstart §3d): it
installs the package as top-level `plugin`, so `import terminal_jail` fails
(TJ-DF-006). For the plugin, follow §3d but expect to import `plugin`.

## 3. The happy path (what a real user does)

```bash
TJ=~/.local/bin/terminal-jail
$TJ --version                                   # terminal-jail 1.1.0
$TJ --user echo "in jail"                       # runs as nobody (65534), rc=0
$TJ --user bash -c 'exit 7'; echo $?            # exit code passthrough → 7
echo hi | $TJ --user cat                        # stdin passthrough → hi
$TJ --user fdisk /dev/sda                       # COMMAND BLOCKED box, rc=126
TERMINAL_JAIL_INTERRUPTOR_MODE=warn $TJ --user fdisk /dev/sda   # warns + allows
$TJ --no-interruptor --user fdisk /dev/sda      # firewall off, command runs
```

**Host note:** plain `$TJ echo hi` (no `--user`) fails with `unshare:
Operation not permitted` on hosts that deny unprivileged PID namespaces —
this is documented; `--user` is the fallback.

## 4. The JSON bridge (firewall API — safe to script)

```bash
echo '{"command": "echo hello"}' | python3 plugin/terminal_jail/interruptor_bridge.py
# → {"action":"allow","command":"echo hello","modified":null,"rule_id":null,"reason":""}
echo '{"command": "rm -rf /"}' | python3 plugin/terminal_jail/interruptor_bridge.py
# → {"action":"block",...,"rule_id":"builtin-rm-rf-root",...}
```

The bridge reads ONE JSON line on stdin, writes one JSON line on stdout.
It only DECIDES — it never executes. Use it for testing rules safely.

## 5. What BROKE during real use (with fixes where they exist)

| # | Symptom | Cause | Fix direction |
|---|---|---|---|
| 1 | `rm -rf --no-preserve-root /` (and `rm -r -f /`, `rm --recursive --force /`, `rm -rf/`) execute | blocklist regex `rm\s+(-{1,2})?\s*-?rf\s+/` can't cross a flag token | rewrite rule token-aware (TJ-DF-001, P0) |
| 2 | `--user --seccomp echo ok` → `ModuleNotFoundError: No module named 'terminal_jail'`, rc=1 (installed binary) | seccomp-loader path resolution assumes repo layout; install.sh ships tree one level deeper | fix loader path walk / install layout (TJ-DF-002, P0) |
| 3 | `--seccomp` prints "seccomp not applied (… missing CAP_SYS_ADMIN or no_new_privs set?)" and runs WITHOUT the filter | seccomp.py never sets PR_SET_NO_NEW_PRIVS before PR_SET_SECCOMP | add `prctl(38,1)` before filter install — proven to work unprivileged on this host (TJ-DF-003, P1) |
| 4 | User rule file `~/.config/terminal-jail/rules.d/99-x.yaml` has zero effect | decider Layer 4 ("user rules … Not yet implemented") never loads rules | wire RuleLoader into Decider (TJ-DF-004, P1) |
| 5 | `chmod 000 /` allowed; `mount`/`su`/`passwd`/`apt install`/`chown` allowed | README's rule table ≠ engine (README claims these are blocked/sandboxed) | align docs or rules (TJ-DF-005, P1) |
| 6 | `pip install -e .` then `import terminal_jail` → ModuleNotFoundError | pyproject packages.find exposes `plugin`, not `terminal_jail` | fix packaging (TJ-DF-006, P1) |
| 7 | `TERMINAL_JAIL_SECCOMP=1` alone doesn't enable seccomp | env var only honored behind the `--seccomp` flag | honor env in CLI or fix docs (TJ-DF-008, P2) |

## 6. What surprised me (good)

- Enforce mode FAILS CLOSED when the bridge is missing or crashes (exit 126
  with an explanatory box) — the TJ-GAP-021 P0 fix genuinely holds.
- Warn mode prints `[terminal-jail] WARN: Would have blocked (rule): reason`
  on stderr — no silent pass-through.
- `--user` jail genuinely runs as nobody: `fdisk` inside the jail couldn't
  open /dev/sda (permission denied) — privilege dropping works.
- Auto-sandbox (modify) wraps test/build commands in a nested
  `unshare --user --pid` — verified via engine for pytest/make/go test/pip.
- The whole CLI is dependency-light: bash + unshare + python3 only.

## 7. What I'd fix first (if I had 1 hour of the maintainer's time)

1. **TJ-DF-001** — the rm -rf bypass is the product's headline promise; one
   regex rewrite + 4 regression tests.
2. **TJ-DF-002** — installed `--seccomp` crashes outright; one path fix.
3. **TJ-DF-003** — 2-line no_new_privs fix makes seccomp actually work
   unprivileged (validated live).
All three are small; all three are security-relevant; the E2E tick battery
should then re-run.

## 8. Reproduce everything

All probes used the REAL repo code (no test doubles) from
`/tmp/dogfood-terminal-jail/scratch/probe*.py`:
`probe1_engine_battery.py`, `probe2_bypasses.py`, `probe3_user_rules.py`,
`probe4_cli_battery.sh`, `probe5_seccomp.sh`. Board: TJ-DF-001..009.
