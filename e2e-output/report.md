# E2E Verification Report — terminal-jail

**Tick:** #92 · **Date:** 2026-08-03 · **Type:** E2E-001 (CLI/API variant — twelfth run, 5 ticks after #87, first tick of window #92-97)
**Executor:** Foreman direct (operational CLI verification — project has no browser surface)
**Baseline:** 254 passed / 32 skipped (stable since tick #82's +12 killpg regression cases)

## Executive Summary

The Interruptor Bash command firewall works end-to-end. All 23 engine verdict
cases matched the built-in rule set (5 blocklist, 7 allow, 8 sandbox-modify,
3 parser), and the killpg probe (9 block vectors + 2 benign) returned 11/11
PASS — **GAP-04 remains closed**, with no new gaps found this run.
GAP-01/GAP-02/GAP-03 continue to hold. No code change this tick.

## 1. Engine Verdict Tests (bridge protocol)

23 cases via `interruptor_bridge.py` JSON protocol — all PASS:

| Category | Cases | Verdict | Result |
|---|---|---|---|
| Critical blocklist (prio 1000) | `rm -rf /`, fork bomb `:(){ :\|:& };:`, `kill -9 -1`, `curl\|sh`, `wget\|bash` | block (exit 126 path) | ✅ 5/5 |
| Always-allow (prio 500) | `ls`, `echo`, `git status`, plain `curl -o`, `npm install`, `apt-get update`, `docker ps` | allow | ✅ 7/7 |
| Auto-sandbox (prio 700) | pytest, `pip install`, `npm test`, `go test`, make, cargo, gcc, `./script.sh` | modify (unshare wrap) | ✅ 8/8 |
| Parser edge cases | pipe chain, cmd substitution, redirect | parsed, verdict allow | ✅ 3/3 |

Plus the killpg rule probe (9 vectors): `os.killpg(1)`, `os.kill(1)`,
`process.kill(-1)`, `kill(-1)`, `os.killpg(0)`, `os.kill(0)`, `kill(0)`,
`process.kill(0)`, `killpg(1,15)` → block; benign high-pid `os.killpg(12345)` /
`os.kill(456)` → allow. **11/11 PASS (GAP-04 fix holds).**

## 2. CLI Integration Tests (standalone/terminal-jail)

| Scenario | Expected | Actual | Result |
|---|---|---|---|
| `fdisk -l` (enforce) | block, formatted box, exit 126 | `COMMAND BLOCKED — builtin-fdisk` box, exit 126 | ✅ |
| `pytest --version` (enforce, argv-separated) | modify → sandboxed, executes in jail | `Modified: 'pytest' '--version' → sandboxed`, `pytest 9.1.1` printed from inside the namespace | ✅ |
| `--version` | 1.1.0 | `terminal-jail 1.1.0` | ✅ |

Usage note (not a regression): passing a whole command as ONE argv token
(e.g. `terminal-jail "pytest --version"`) double-quotes the command string and
the jail reports `command not found` — the wrapper is designed for
argv-separated invocation (`terminal-jail pytest --version`), per its own
usage text. The sandbox modify path is proven live with correct argv.

## 3. Gap-Fix Verification (prior ticks)

| Gap | Fix | Verified |
|---|---|---|
| E2E-001-GAP-01 | specs/integration.md:177 lists exactly the 8 sandbox rules; curl/wget/apt/docker explicitly NOT auto-sandboxed | ✅ holds |
| E2E-001-GAP-02 | `TestNoSandboxContract` (ALLOW param cases + blocklist pipe cases) | ✅ holds (17/17) |
| E2E-001-GAP-03 | Warn mode now prints would-have-blocked warning on stderr (fixed #77, `448e00a`) | ✅ holds |
| E2E-001-GAP-04 | killpg(0)/kill(0)/process.kill(0) own-process-group vectors blocked (fixed #82, `a5cb9bd`) | ✅ holds (probe 11/11) |

## 4. Performance Benchmarks (in-process, T11.17 targets)

| Metric | Tick #92 | Tick #87 | Target | Result |
|---|---|---|---|---|
| Cold start | 0.08 ms | 0.14 ms | <50 ms | ✅ |
| Warm (avg) | 0.027 ms | 0.052 ms | <5 ms | ✅ |
| 1KB parse | 0.289 ms | 0.461 ms | <10 ms | ✅ |
| 500-rule eval | 0.784 ms | 0.968 ms | <5 ms | ✅ |

(Back in the low-jitter band after tick #87's host-load elevation — host load
2.39 now vs 8.99 then; not a regression either way.)

## 5. Other Gates

- pytest: 254 passed / 32 skipped in 2.81s
- ruff: clean (0 findings, plugin/ + standalone/; 26 files formatted)
- GitReins guard: PASS 4/4 (secrets/lint/tests/static_analysis)
- Hilo: 147 edges / 27 files (live-verified)
- Version consistency: 1.1.0 everywhere (VERSION-001 holds)
- CI: 6/6 recent runs green (latest tick #91 push 12:02:25Z success); remote clean (0 unpushed, 0 remote commits); no open issues
- Scheduler: Enabled, CooldownS=1350 (external drift from pinned 900 at 2026-08-02T18:42:12Z — noted, no PUT; E2E fixture gates pause, not idle counter)
- Stale pytest lastfailed cache: all 3 cached node-ids `no tests ran` (params removed from source pre-#82) — conclusively stale, not regressions

## 6. Limitations (unchanged, environmental)

- PID-namespace unshare kernel-blocked on host for the NON-bridge path (32 skips) —
  the bridge's `unshare --user --pid` modify path is proven live on host.
- No browser surface (CLI/plugin project) — Playwright/screenshot N/A.
- Rule loader user-directory layer (Layer 4) stubbed by design (3 skips T-I38-40).

## 7. Verdict

**E2E PASS — 0 new gaps. GAP-01/GAP-02/GAP-03/GAP-04 all hold. Next E2E tick in window #97-102.**
