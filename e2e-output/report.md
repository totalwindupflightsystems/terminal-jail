# E2E Verification Report — terminal-jail

**Tick:** #82 · **Date:** 2026-08-03 · **Type:** E2E-001 (CLI/API variant — tenth run, 5 ticks after #77, first tick of window #82-87)
**Executor:** Foreman direct (operational CLI verification — project has no browser surface)
**Baseline:** 254 passed / 32 skipped (was 242 — 12 killpg regression cases added this tick)

## Executive Summary

The Interruptor Bash command firewall works end-to-end. All 23 engine verdict
cases matched the built-in rule set (5 blocklist, 7 allow, 8 sandbox-modify,
3 parser), and the extended killpg probe (tick #72 rule) uncovered **one real
security gap, found and fixed this tick**: the `builtin-killpg-pid1` rule
blocked `killpg(1)` / `kill(-1)` / `os.kill(1)` but **not the own-process-group
vectors** — `killpg(0)`, `os.kill(0)`, `kill(0)`, `process.kill(0)` all pass a
signal to the caller's own process group (self-DoS / agent-session kill, the
same MagicMock incident class). Pattern extended from `[1]` to `[01]` targets
(commit `a5cb9bd`) with 12 new regression cases.
**GAP-01 and GAP-02 continue to hold. One new gap (GAP-04) found and closed.**

## 1. Engine Verdict Tests (bridge protocol)

23 cases via `interruptor_bridge.py` JSON protocol — all PASS:

| Category | Cases | Verdict | Result |
|---|---|---|---|
| Critical blocklist (prio 1000) | `rm -rf /`, fork bomb `:(){ :\|:& };:`, `kill -9 -1`, `curl\|sh`, `wget\|bash` | block (exit 126 path) | ✅ 5/5 |
| Always-allow (prio 500) | `ls`, `echo`, `git status`, plain `curl -o`, `npm install`, `apt-get update`, `docker ps` | allow | ✅ 7/7 |
| Auto-sandbox (prio 700) | pytest, `pip install`, `npm test`, `go test`, make, cargo, gcc, `./script.sh` | modify (unshare wrap) | ✅ 8/8 |
| Parser edge cases | pipe chain, cmd substitution, redirect | parsed, verdict allow | ✅ 3/3 |

Plus the tick-#72 killpg rule probe (9 vectors): `os.killpg(1)`, `os.kill(1)`,
`process.kill(-1)`, `kill(-1)` and **newly** `os.killpg(0)`, `os.kill(0)`,
`kill(0)`, `process.kill(0)` → block; benign high-pid `os.killpg(12345)` /
`os.kill(456)` → allow. **9/9 PASS after fix.**

## 2. CLI Integration Tests (standalone/terminal-jail)

| Scenario | Expected | Actual | Result |
|---|---|---|---|
| `fdisk -l` (enforce) | block, formatted box, exit 126 | `COMMAND BLOCKED — builtin-fdisk` box | ✅ |
| `pytest --version` (enforce) | modify → sandboxed | `[terminal-jail] Modified: ... → sandboxed` **and `pytest 9.1.1` executes inside the jail** | ✅ |
| `--version` | 1.1.0 | `terminal-jail 1.1.0` | ✅ |

## 3. Tick #82 Code Change (GAP-04 — own-process-group kill vectors)

| Change | File | Verified |
|---|---|---|
| `builtin-killpg-pid1` pattern extended: `(os.killpg\|killpg)([01])`, `os.kill([01])`, `process.kill(-?[01])`, `kill(-?[01])`, `kill([01], 9\|SIGKILL)` — killpg(0)/kill(0) target the caller's own process group, same incident class as killpg(1); message updated to cover both | `plugin/terminal_jail/interruptor/blocklist.py` | ✅ probe 9/9 |
| Regression cases: 8 block vectors + 2 safe (ALLOW/MODIFY) + 2 allowlist (exact ALLOW) | `plugin/test_interruptor.py` | ✅ 94/94 in file, 254/32 full suite |

## 4. Gap-Fix Verification (prior ticks)

| Gap | Fix | Verified |
|---|---|---|
| E2E-001-GAP-01 | specs/integration.md:177 lists exactly the 8 sandbox rules; curl/wget/apt/docker explicitly NOT auto-sandboxed | ✅ holds |
| E2E-001-GAP-02 | `TestNoSandboxContract` (ALLOW param cases + blocklist pipe cases) | ✅ holds (17/17) |
| E2E-001-GAP-03 | Warn mode now prints would-have-blocked warning on stderr (fixed #77, `448e00a`) | ✅ holds |
| E2E-001-GAP-04 (new, fixed #82) | killpg(0)/kill(0)/process.kill(0) own-process-group vectors now blocked | ✅ fixed + regression tests |

## 5. Performance Benchmarks (in-process, T11.17 targets)

| Metric | Tick #82 | Target | Result |
|---|---|---|---|
| Cold start | 0.08 ms | <50 ms | ✅ |
| Warm (avg) | 0.029 ms | <5 ms | ✅ |
| 1KB parse | 0.276 ms | <10 ms | ✅ |
| 500-rule eval | 0.812 ms | <5 ms | ✅ |

(Per-process bridge overhead ≈70-110 ms = interpreter startup; not the engine.)

## 6. Other Gates

- pytest: 254 passed / 32 skipped in 4.40s (+12 killpg regression cases)
- ruff: clean (0 findings, plugin/ + standalone/)
- Version consistency: 1.1.0 everywhere (VERSION-001 holds)
- CI: 3/3 recent runs green (latest tick #81 push 06:36:05Z success); remote clean (0 unpushed, 0 remote commits); no open issues
- Scheduler: Enabled, CooldownS=1350 (externally changed from pinned 900 at 2026-08-02T18:42:12Z — noted, no PUT; E2E fixture gates pause, not idle counter)

## 7. Limitations (unchanged, environmental)

- PID-namespace unshare kernel-blocked on host for the NON-bridge path (32 skips) —
  the bridge's `unshare --user --pid` modify path is proven live on host.
- No browser surface (CLI/plugin project) — Playwright/screenshot N/A.
- Rule loader user-directory layer (Layer 4) stubbed by design (3 skips T-I38-40).

## 8. Verdict

**E2E PASS — 1 new gap found and closed (GAP-04 own-process-group kill vectors),
GAP-01/GAP-02/GAP-03 hold. Next E2E tick in window #87-92.**
