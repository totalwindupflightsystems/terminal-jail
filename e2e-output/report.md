# E2E Verification Report — terminal-jail

**Tick:** #112 · **Date:** 2026-08-03 · **Type:** E2E-001 (CLI/API variant — sixteenth run, first tick of window #112-117)
**Executor:** Foreman direct (operational CLI verification — project has no browser surface)
**Baseline:** 254 passed / 32 skipped (stable since tick #82's +12 killpg regression cases)

## Executive Summary

The Interruptor Bash command firewall works end-to-end. All 23 engine verdict
cases matched the built-in rule set (5 blocklist, 7 allow, 8 sandbox-modify,
3 parser), and the killpg probe (9 block vectors + 2 benign, two-arg `(pid,
signal)` form per the T-killpg contract) returned 11/11 PASS — **GAP-04
remains closed**, with no new gaps found this run.
GAP-01/GAP-02/GAP-03 continue to hold. No code change this tick.

## 1. Engine Verdict Tests (bridge protocol)

23 cases via `interruptor_bridge.py` JSON protocol — all PASS:

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
| Same mode `pytest --version` | ✅ `[terminal-jail] Modified … → sandboxed`, then `pytest 9.1.1` executes in jail |

Live unshare split (kernel 7.0.0-28): bare `unshare --user --pid --fork true`
rc=0 (expected per tick #97); jail modify path (echo allow probe) EPERM rc=1 —
expected split per tick #98, NOT a regression.

## 3. Performance Benchmarks

| Benchmark | This run | Target | Result |
|---|---|---|---|
| Cold start (first invocation) | 0.09 ms | < 50 ms | ✅ |
| Warm start (min of 100) | 0.031 ms | < 5 ms | ✅ |
| 1KB parse (min of 100) | 0.272 ms | < 10 ms | ✅ |
| 500-rule eval (min of 50) | 0.830 ms | < 5 ms | ✅ |

## 4. Regression Gates

| Gate | Result |
|---|---|
| Full pytest suite | ✅ 254 passed / 32 skipped (3.06s) |
| NoSandboxContract (GAP-02 lock) | ✅ 17 passed |
| Auto-sandbox spec (GAP-01 lock, integration.md:177) | ✅ exactly 8 rules |
| Ruff (plugin/, standalone/) | ✅ clean |
| GitReins guard | ✅ 4/4 PASS (secrets/lint/tests/static_analysis) |

## 5. External Signals

CI 3/3 green (latest: tick #111 push 22:55:22Z success) · 0 open issues ·
0 unpushed commits · no terminal-jail siblings. Scheduler: Enabled,
CooldownS=1350 (known external drift, no PUT). Verdict: **E2E PASS — 0 new
gaps, GAP-01/02/03/04 all hold.**
