# E2E Verification Report — terminal-jail

**Tick:** #42 · **Date:** 2026-08-01 · **Type:** E2E-001 (CLI/API variant — second run, 6 ticks after #36)
**Executor:** Foreman direct (operational CLI verification — project has no browser surface)
**Baseline:** 227 passed / 32 skipped

## Executive Summary

The Interruptor Bash command firewall continues to work end-to-end. All 23 engine
verdict cases matched the built-in rule set (5 blocklist, 7 allow, 8 sandbox-modify,
3 parser). CLI integration paths behave per spec. **GAP-01 and GAP-02 fixes from
tick #37 hold** — spec now matches engine, contract tests pin the behavior.
**No new gaps found.** No worker needed; no code changed.

## 1. Engine Verdict Tests (bridge protocol)

23 cases via `interruptor_bridge.py` JSON protocol — all PASS:

| Category | Cases | Verdict | Result |
|---|---|---|---|
| Critical blocklist (prio 1000) | `rm -rf /`, fork bomb `:(){ :\|:& };:`, `kill -9 -1`, `curl\|sh`, `wget\|bash` | block (exit 126 path) | ✅ 5/5 |
| Always-allow (prio 500) | `ls`, `echo`, `git status`, plain `curl -o`, `npm install`, `apt-get update`, `docker ps` | allow | ✅ 7/7 |
| Auto-sandbox (prio 700) | pytest, `pip install`, `npm test`, `go test`, make, cargo, gcc, `./script.sh` | modify (unshare wrap) | ✅ 8/8 |
| Parser edge cases | pipe chain, cmd substitution, redirect | parsed, verdict allow | ✅ 3/3 |

Note: tick #36's report listed a `for`-loop fork bomb probe; the actual builtin
pattern is `:(){ :|:& };:` — verified blocking with the canonical pattern (probe
correction, not a regression).

## 2. CLI Integration Tests (standalone/terminal-jail)

| Scenario | Expected | Actual | Result |
|---|---|---|---|
| `fdisk -l` (enforce) | block, formatted box | `COMMAND BLOCKED — builtin-fdisk` box, exit path per spec | ✅ |
| `pytest --version` (enforce) | modify → sandboxed | `[terminal-jail] Modified: 'pytest'... → sandboxed` (unshare fails on host — env) | ✅ |
| `--version` | 1.1.0 | `terminal-jail 1.1.0` | ✅ |
| Dedicated CLI test files | pass | `test_interruptor_integration.py` + `test_standalone_cli.py` | ✅ (in 227) |

## 3. Gap-Fix Verification (tick #37)

| Gap | Fix | Verified |
|---|---|---|
| E2E-001-GAP-01 | specs/integration.md:177 now lists exactly the 8 sandbox rules and states curl/wget/apt/docker are NOT auto-sandboxed | ✅ (grep confirmed) |
| E2E-001-GAP-02 | `TestNoSandboxContract` (10 ALLOW param cases + blocklist pipe cases) in plugin/test_interruptor.py | ✅ (18 passed in -k filter; in 227 total) |

## 4. Performance Benchmarks (in-process, T11.17 targets)

| Metric | Tick #42 | Target | Result |
|---|---|---|---|
| Cold start | 0.044 ms | <50 ms | ✅ |
| Warm (avg) | 0.043 ms | <5 ms | ✅ |
| 1KB parse | 0.374 ms | <10 ms | ✅ |
| 500-rule eval | 0.511 ms | <5 ms | ✅ |

(Per-process bridge overhead ≈70-110 ms = interpreter startup; not the engine.)

## 5. Other Gates

- pytest: 227 passed / 32 skipped (unchanged from ticks #37-41)
- ruff: clean (0 findings, plugin/ + standalone/)
- GitReins guard: PASS (secrets / lint / tests / static_analysis)
- Hilo: 147 edges / 27 files (unchanged)
- Version consistency: 1.1.0 everywhere, zero 1.0.0 stragglers (VERSION-001 holds)
- TODO/stub scan: clean (no actionable stubs outside documented deferred features)
- CI: 4 recent runs green; remote clean (0 unpushed); no open issues

## 6. Limitations (unchanged, environmental)

- PID-namespace unshare kernel-blocked on host (32 skips) — namespacing verified
  via unit/integration tests, not live PID-jail execution.
- No browser surface (CLI/plugin project) — Playwright/screenshot N/A.
- Rule loader user-directory layer (Layer 4) stubbed by design (3 skips T-I38-40).

## 7. Verdict

**E2E PASS — 0 new gaps. GAP-01/GAP-02 fixes hold. Board idle (E2E-001 + NEVER-DONE
fixtures only). Next E2E tick in 5-10 ticks.**
