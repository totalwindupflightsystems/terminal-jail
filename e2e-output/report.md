# E2E Verification Report — terminal-jail

**Tick:** #72 · **Date:** 2026-08-02 · **Type:** E2E-001 (CLI/API variant — eighth run, 5 ticks after #67, first tick of window #72-77)
**Executor:** Foreman direct (operational CLI verification — project has no browser surface) + stewardship of orphaned prior-session WIP
**Baseline:** 241 passed / 32 skipped (was 227 — 14 new regression cases added this tick)

## Executive Summary

The Interruptor Bash command firewall works end-to-end. All 23 engine verdict
cases matched the built-in rule set (5 blocklist, 7 allow, 8 sandbox-modify,
3 parser). CLI integration paths behave per spec — **and a real bug was found
and fixed this tick**: the standalone CLI double-wrapped bridge-modified
commands in `unshare` (inner unshare → EPERM), so auto-sandboxed commands
never actually executed inside the jail. The fix (from a prior interactive
session that stalled mid-verification; stewarded by this tick) makes the
modify path run the bridge's already-namespaced command as-is. On this host
`pytest --version` now runs INSIDE the jail (previously it died at the
double-unshare). A second gap — `bash evil_script.sh` / `sh script.sh` /
`python3 deploy.py` were ALLOWED (only `./script.sh` matched the auto-script
pattern) — was also fixed and locked with 14 new regression tests.
**GAP-01 and GAP-02 continue to hold. No new gaps found beyond the two fixed.**

## 1. Engine Verdict Tests (bridge protocol)

23 cases via `interruptor_bridge.py` JSON protocol — all PASS:

| Category | Cases | Verdict | Result |
|---|---|---|---|
| Critical blocklist (prio 1000) | `rm -rf /`, fork bomb `:(){ :\|:& };:`, `kill -9 -1`, `curl\|sh`, `wget\|bash` | block (exit 126 path) | ✅ 5/5 |
| Always-allow (prio 500) | `ls`, `echo`, `git status`, plain `curl -o`, `npm install`, `apt-get update`, `docker ps` | allow | ✅ 7/7 |
| Auto-sandbox (prio 700) | pytest, `pip install`, `npm test`, `go test`, make, cargo, gcc, `./script.sh` | modify (unshare wrap) | ✅ 8/8 |
| Parser edge cases | pipe chain, cmd substitution, redirect | parsed, verdict allow | ✅ 3/3 |

## 2. CLI Integration Tests (standalone/terminal-jail)

| Scenario | Expected | Actual | Result |
|---|---|---|---|
| `fdisk -l` (enforce) | block, formatted box, exit 126 | `COMMAND BLOCKED — builtin-fdisk` box, exit 126 | ✅ |
| `pytest --version` (enforce) | modify → sandboxed | `[terminal-jail] Modified: ... → sandboxed` **and `pytest 9.1.1` executes inside the jail** (double-unshare fix landed — previously EPERM, command never ran) | ✅ |
| `--version` | 1.1.0 | `terminal-jail 1.1.0` | ✅ |
| Dedicated CLI test files | pass | `test_interruptor_integration.py` + `test_standalone_cli.py` | ✅ (in 241) |

## 3. Tick #72 Code Changes (stewardship)

| Change | File | Verified |
|---|---|---|
| `MODIFIED=1` flag — bridge-modified command already contains unshare prefix; skip re-wrapping (double unshare → EPERM) | `standalone/terminal-jail` | ✅ Docker nested test (prior session) + host `pytest --version` executes in jail |
| auto-script pattern extended: `bash|sh|dash|zsh|python3 <file>.sh/.py/.rb` → sandbox (was ALLOW — gap) | `plugin/terminal_jail/interruptor/sandbox.py` | ✅ pattern probe: 9 sandbox + 6 allow, no false positives |
| 14 regression tests: 9 positive (interpreter+script → MODIFY), 5 negative (interpreter flags/globs → ALLOW) | `plugin/test_interruptor.py` | ✅ 241/32 pass |

## 4. Gap-Fix Verification (tick #37 + this tick)

| Gap | Fix | Verified |
|---|---|---|
| E2E-001-GAP-01 | specs/integration.md:177 lists exactly the 8 sandbox rules and states curl/wget/apt/docker are NOT auto-sandboxed | ✅ (grep confirmed) |
| E2E-001-GAP-02 | `TestNoSandboxContract` (ALLOW param cases + blocklist pipe cases) | ✅ (17 ALLOW cases incl. 5 new interpreter-negative; in 241 total) |
| GAP (new, fixed #72) | `bash evil.sh` etc. bypassed auto-script (only `./` matched) | ✅ fixed + 9 positive regression cases |

## 5. Performance Benchmarks (in-process, T11.17 targets)

| Metric | Tick #72 | Target | Result |
|---|---|---|---|
| Cold start | 0.08 ms | <50 ms | ✅ |
| Warm (avg) | 0.026 ms | <5 ms | ✅ |
| 1KB parse | 0.242 ms | <10 ms | ✅ |
| 500-rule eval | 0.703 ms | <5 ms | ✅ |

(Per-process bridge overhead ≈70-110 ms = interpreter startup; not the engine.)

## 6. Other Gates

- pytest: 241 passed / 32 skipped in 2.56s (+14 new regression cases)
- ruff: clean (0 findings, plugin/ + standalone/)
- GitReins guard: PASS 4/4 (secrets / lint / tests / static_analysis)
- Hilo: 147 edges / 27 files (copied from tick #67, not re-verified — idle-tier)
- Version consistency: 1.1.0 everywhere, zero 1.0.0 stragglers (VERSION-001 holds)
- CI: 3/3 recent runs green; remote clean (0 unpushed before this tick); no open issues

## 7. Limitations (unchanged, environmental)

- PID-namespace unshare kernel-blocked on host for the NON-bridge path (32 skips) —
  the bridge's `unshare --user --pid` modify path is now proven live on host.
- No browser surface (CLI/plugin project) — Playwright/screenshot N/A.
- Rule loader user-directory layer (Layer 4) stubbed by design (3 skips T-I38-40).
- Leftover: docker container `tj-nested-test` from the stalled interactive session
  (idle, no exec attached) — left running in case the session resumes.

## 8. Verdict

**E2E PASS — 0 new gaps. GAP-01/GAP-02 hold. Two real bugs fixed (double-unshare
EPERM + bash-script sandbox bypass) via stewardship of orphaned prior-session WIP,
locked with 14 regression tests. Next E2E tick in window #77-82.**
