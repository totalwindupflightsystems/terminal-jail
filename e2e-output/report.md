# E2E Verification Report — terminal-jail

**Tick:** #77 · **Date:** 2026-08-02 · **Type:** E2E-001 (CLI/API variant — ninth run, 5 ticks after #72, first tick of window #77-82)
**Executor:** Foreman direct (operational CLI verification — project has no browser surface)
**Baseline:** 242 passed / 32 skipped (was 241 — 1 new regression case added this tick)

## Executive Summary

The Interruptor Bash command firewall works end-to-end. All 23 engine verdict
cases matched the built-in rule set (5 blocklist, 7 allow, 8 sandbox-modify,
3 parser). CLI integration paths behave per spec — **and one real gap was
found and fixed this tick**: warn mode (`TERMINAL_JAIL_INTERRUPTOR_MODE=warn`)
was a *silent* pass-through. The engine downgrades BLOCK→ALLOW in warn mode and
carries the warning in the bridge JSON `reason` field, but the CLI only printed
`reason` for block/modify actions — so a user in warn mode never saw that a
command would have been blocked. Spec `integration.md:412` requires a printed
warning. Fixed (commit `448e00a`) with a regression test.
**GAP-01 and GAP-02 continue to hold. One new gap (GAP-03) found and closed.**

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
| `pytest --version` (enforce) | modify → sandboxed | `[terminal-jail] Modified: ... → sandboxed` **and `pytest 9.1.1` executes inside the jail** | ✅ |
| `--version` | 1.1.0 | `terminal-jail 1.1.0` | ✅ |
| `fdisk -l` (warn) | print warning, do NOT block | `[terminal-jail] WARN: [WARN MODE] Would have blocked: Partition manipulation...` on stderr, no block box, no exit 126 | ✅ (GAP-03 fix) |
| `echo hi` (warn) | no spurious warning | clean pass-through (no WARN line) | ✅ |
| `echo hi` (disabled) | pass-through | interruptor bypassed (unshare EPERM is the documented host limitation) | ✅ |
| Dedicated CLI test files | pass | `test_interruptor_integration.py` + `test_standalone_cli.py` | ✅ (in 242) |

## 3. Tick #77 Code Change (GAP-03 — warn-mode silent pass-through)

| Change | File | Verified |
|---|---|---|
| Warn mode: surface engine `reason` on stderr when action=allow — engine downgrades BLOCK→ALLOW in warn mode carrying the warning in bridge JSON; CLI's block branch was unreachable in warn mode, so warnings were dropped | `standalone/terminal-jail` | ✅ stderr shows `[terminal-jail] WARN: [WARN MODE] Would have blocked: ...`; enforce block/modify paths unchanged (exit 126 + jail execution re-verified) |
| Regression test: `test_interruptor_warn_mode_surfaces_block_warning` — asserts WARN on stderr, no block box, exit != 126 | `plugin/test_interruptor_integration.py` | ✅ 242/32 pass |

## 4. Gap-Fix Verification (prior ticks)

| Gap | Fix | Verified |
|---|---|---|
| E2E-001-GAP-01 | specs/integration.md:177 lists exactly the 8 sandbox rules; curl/wget/apt/docker explicitly NOT auto-sandboxed | ✅ holds |
| E2E-001-GAP-02 | `TestNoSandboxContract` (ALLOW param cases + blocklist pipe cases) | ✅ holds (in 242 total) |
| E2E-001-GAP-03 (new, fixed #77) | Warn mode now prints would-have-blocked warning on stderr | ✅ fixed + regression test |

## 5. Performance Benchmarks (in-process, T11.17 targets)

| Metric | Tick #77 | Target | Result |
|---|---|---|---|
| Cold start | 0.08 ms | <50 ms | ✅ |
| Warm (avg) | 0.030 ms | <5 ms | ✅ |
| 1KB parse | 0.289 ms | <10 ms | ✅ |
| 500-rule eval | 0.767 ms | <5 ms | ✅ |

(Per-process bridge overhead ≈70-110 ms = interpreter startup; not the engine.)

## 6. Other Gates

- pytest: 242 passed / 32 skipped in 3.21s (+1 new regression case)
- ruff: clean (0 findings, plugin/ + standalone/)
- GitReins guard: PASS 4/4 (secrets / lint / tests / static_analysis)
- Version consistency: 1.1.0 everywhere, zero 1.0.0 stragglers (VERSION-001 holds)
- CI: 5/5 recent runs green (latest tick #76 push 03:34:48Z success); remote clean (0 unpushed, 0 remote commits); no open issues

## 7. Limitations (unchanged, environmental)

- PID-namespace unshare kernel-blocked on host for the NON-bridge path (32 skips) —
  the bridge's `unshare --user --pid` modify path is proven live on host.
- No browser surface (CLI/plugin project) — Playwright/screenshot N/A.
- Rule loader user-directory layer (Layer 4) stubbed by design (3 skips T-I38-40).
- Warn/disabled mode full command execution also hits host unshare EPERM (rc=1 after
  the WARN print); the firewall verdict itself (warn = allow + warning, disabled =
  bypass) is verified at the engine + CLI level.

## 8. Verdict

**E2E PASS — 1 new gap found and closed (GAP-03 warn-mode silent pass-through),
GAP-01/GAP-02 hold. Next E2E tick in window #82-87.**
