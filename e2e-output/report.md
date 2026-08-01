# E2E Verification Report — terminal-jail

**Tick:** #36 · **Date:** 2026-08-01 · **Type:** E2E-001 (CLI/API variant — first-ever E2E tick, overdue from 5-10 tick cadence)
**Executor:** Foreman direct (operational CLI verification — project has no browser surface)
**Baseline:** 215 passed / 32 skipped (25 skips = host kernel blocks unprivileged PID namespaces — environmental, documented)

## Executive Summary

The Interruptor Bash command firewall works end-to-end. All 22 engine verdict cases
matched the built-in rule set. CLI integration paths (block/warn/disabled/modify) behave
per spec. **One spec-vs-implementation divergence found** (P2) — integration.md
overstates auto-sandbox coverage. One task created (E2E-001-GAP-01).

## 1. Engine Verdict Tests (bridge protocol)

22 cases via `interruptor_bridge.py` JSON protocol — all PASS:

| Category | Cases | Verdict | Result |
|---|---|---|---|
| Critical blocklist (prio 1000) | `rm -rf /`, fork bomb, `kill -9 -1`, `curl\|sh`, `wget\|bash` | block (exit 126 path) | ✅ 5/5 |
| Always-allow (prio 500) | `ls`, `echo`, `git status`, plain `curl -o`, `npm install`, `apt-get update`, `docker ps` | allow | ✅ 7/7 |
| Auto-sandbox (prio 700) | pytest, `pip install`, `npm test`, `go test`, make, cargo, gcc, `./script.sh` | modify (wrapped in `unshare --user --pid --fork --kill-child=SIGKILL bash -c '...'`) | ✅ 8/8 |
| Parser edge cases | pipe chain, cmd substitution, redirect | parsed, verdict allow | ✅ 3/3 |

## 2. CLI Integration Tests (standalone/terminal-jail)

| Scenario | Expected | Actual | Result |
|---|---|---|---|
| `fdisk -l` (enforce) | block, exit 126, formatted box | `COMMAND BLOCKED — builtin-fdisk`, box-drawing output, exit 126 | ✅ |
| `fdisk -l` (warn mode) | pass-through w/ warning | passes to unshare (fails on host — env), no block | ✅ |
| `fdisk -l` (disabled) | full pass-through | passes to unshare, no block | ✅ |
| `pytest --version` (enforce) | modify → sandboxed | `[terminal-jail] Modified: 'pytest'... → sandboxed` | ✅ |
| `--help` / `--version` | usage / version | both correct | ✅ |
| `--no-interruptor` flag | disable firewall | works (test suite) | ✅ |
| Dedicated CLI test files | 22 pass | `test_interruptor_integration.py` + `test_standalone_cli.py`: 22 passed, 3 skipped | ✅ |

## 3. Spec Compliance

| Spec | Verdict |
|---|---|
| S05 interruptor.md (T-I01..T-I40) | ✅ Implemented rules match; T-I37 sandbox example (pytest) is the real behavior |
| integration.md:176 auto-sandbox list | ⚠️ **DIVERGENCE** — see finding below |
| integration.md T-I37 (curl/wget sandbox target) | ⚠️ `curl`/`wget` downloads are ALLOWED, not sandboxed (only `curl\|sh` is blocked) |
| cli.md, plugin.md, systemd.md | ✅ No drift observed in exercised paths |

## 4. Finding

### E2E-001-GAP-01 (P2) — integration.md overstates auto-sandbox coverage

`specs/integration.md:176` states auto-sandbox (priority 700) wraps "network downloads
(`curl`, `wget`), package installers (`pip`, `apt`, `yum`), container commands
(`docker`, `podman`), compilation (`gcc`, `make`), etc." The actual implementation
(`interruptor/sandbox.py` + `rules/00-builtins.yaml`) ships exactly 8 sandbox rules:
**pytest/tox/nose, npm test/npx vitest|jest, go test, make, pip install/pip3 install,
cargo build|test, gcc/g++/clang++, `./script.sh|py|rb`**. Plain `curl -o file URL`,
`wget URL`, `apt-get update`, and `docker ps` all return ALLOW.

The S05 spec (T-I37) uses `pytest` as its sandbox example — consistent with the
implementation. integration.md is the drifted document.

**Options:** (a) fix integration.md:176 to list the actual 8 rules (doc-only, matches
S05); or (b) extend `BUILTIN_SANDBOX` with curl/wget/apt/docker rules (behavior change —
would sandbox ALL curl usage, likely too aggressive for normal agent downloads; the
`curl|sh` blocklist already covers the critical vector). **Recommendation: (a)** — align
the doc, keep the implementation's curated sandbox set; the critical network vector
(`curl | sh`) is already blocked at priority 1000.

## 5. Limitations

- PID-namespace unshare is kernel-blocked on this host (25 skips + CLI pass-through
  paths fail at unshare) — namespacing itself verified via unit/integration tests and
  user-ns availability, not live PID-jail execution. Environmental, unchanged from
  ticks #19-35.
- No browser surface exists (CLI/plugin project) — Playwright/screenshot checks N/A.
- Rule loader user-directory layer (Layer 4) is stubbed by design (3 skips: T-I38-40
  user rules / hot-reload) — known deferred feature, tracked as blocked/skip, not a
  regression.
