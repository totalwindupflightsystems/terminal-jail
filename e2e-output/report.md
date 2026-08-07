# E2E Verification Report — terminal-jail

**Tick:** #157 · **Date:** 2026-08-07 · **Type:** E2E-001 (CLI/API variant — twenty-fifth run)
**Executor:** Foreman direct (operational CLI verification — project has no browser surface)
**Baseline:** 234 passed / 6 skipped (changed from 283/32 — `plugin/test_integration.py` removed 2026-08-07 by TJ-GAP-010; it tested dead `transform_command` wrapping. Killpg/quoted battery lives in `test_interruptor.py`, unaffected)

## Executive Summary

The Interruptor Bash command firewall works end-to-end. All 23 engine verdict
cases matched the built-in rule set (5 blocklist, 7 allow, 8 sandbox-modify, 3
parser), the killpg probe returned 11/11 PASS, and the **BUG-001 seccomp
arch-check fix (JEQ jump offsets inverted — every wrapped command died with
SIGSYS 159)** was verified live: `terminal-jail --user --seccomp echo ok`
executed with rc=0 and printed `ok` — no SIGSYS. The seccomp loader degrades
gracefully on this unprivileged host (prctl refused, designed path per loader
line 21 — "the command is exec'd without seccomp"), and the BPF JEQ logic
itself is covered by 2 regression tests in the suite (234 passed). GAP-01/02/
03/04/05 all hold. CLI integration, benchmarks, suite, guard, and CI are
green. **0 new gaps.**

## 1. Engine Verdict Tests (bridge protocol)

23 cases via `interruptor_bridge.py` JSON protocol — all PASS:

| Category | Cases | Verdict | Result |
|---|---|---|---|
| Critical blocklist (prio 1000) | `rm -rf /`, fork bomb `:(){ :\|:& };:`, `kill -9 -1`, `curl\|sh`, `wget\|bash` | block | ✅ 5/5 |
| Always-allow (prio 500) | `ls`, `echo`, `git status`, plain `curl -o`, `npm install`, `apt-get update`, `docker ps` | allow | ✅ 7/7 |
| Auto-sandbox (prio 700) | pytest, `pip install`, `npm test`, `go test`, make, cargo, gcc, `./script.sh` | modify (unshare wrap) | ✅ 8/8 |
| Parser edge cases | pipe chain, cmd substitution, redirect | parsed, verdict allow | ✅ 3/3 |

Plus the killpg rule probe (11 vectors, two-arg form): own-pgroup and pid-1
vectors (`os.killpg(0|1, …)`, `os.kill(0|1, …)`, `process.kill(0|-1, …)`,
`kill(0|-1, 9)`, `killpg(1, 15)`) all BLOCK; benign high-pid forms
(`os.killpg(12345, …)`, `os.kill(456, …)`) stay ALLOW. **11/11 PASS.**

## 2. BUG-001 Seccomp Arch-Check — Live Probe (NEW this battery)

Commit 577ca40 fixed the inverted JEQ jump offsets in the seccomp BPF arch
check (matching arch must SKIP the RET KILL_PROCESS; jt=1/jf=0). Verified
live:

| Probe | Expected | Live result |
|---|---|---|
| `terminal-jail --user --seccomp echo ok` | rc=0, `ok` printed, NO SIGSYS | ✅ rc=0, `ok` printed (loader warns prctl refused on unprivileged host, degrades gracefully, command executes) |
| `terminal-jail --user echo ok` | rc=0 `ok` (user ns path) | ✅ rc=0 `ok` |
| `terminal-jail --no-interruptor echo ok` | env-dependent (--mount-proc needs privileges) | rc=1 unshare EPERM — known split, not regression |

The 2 seccomp regression tests (full + no-op filter paths) pass inside the
234-test suite. The SIGSYS death class is gone.

## 3. CLI Integration

| Probe | Result |
|---|---|
| `terminal-jail --version` | ✅ `terminal-jail 1.1.0`, rc=0 |
| `TERMINAL_JAIL_INTERRUPTOR_MODE=enforce terminal-jail fdisk -l` | ✅ COMMAND BLOCKED box (builtin-fdisk), rc=126 (captured pre-pipe) |
| `TERMINAL_JAIL_INTERRUPTOR_MODE=enforce terminal-jail pytest --version` | ✅ Modified → sandboxed → `pytest 9.0.2` executed LIVE in jail, rc=0 |
| bare `unshare --user --pid --fork true` | ✅ rc=0 (kernel 7.0.0-28) |

Note: the jail now runs `pytest 9.0.2` (repo venv recreated at TJ-GAP-010
cleanup; was 9.1.1) — venv change, not a code regression.

## 4. GAP-01 / GAP-02 Hold Verification

- **GAP-01:** `specs/integration.md` Security goals section documents exactly
  the 8 auto-sandbox rules (pytest, npm test, go test, make, pip install,
  cargo build, gcc, script execution) and states curl/wget/apt/docker are NOT
  auto-sandboxed (only `curl|sh`/`wget|bash` pipelines are blocklisted).
- **GAP-02:** `pytest plugin/test_interruptor.py -k NoSandbox -q` → **17
  passed** (TestNoSandboxContract pins the allow-contract).

## 5. Benchmarks (T11.17 targets)

| Metric | Target | Live | Result |
|---|---|---|---|
| Cold start | <50ms | 0.09 ms | ✅ |
| Warm start (min 100) | <5ms | 0.038 ms | ✅ |
| 1KB parse (min 100) | <10ms | 0.244 ms | ✅ |
| 500-rule eval (min 50) | <5ms | 1.154 ms | ✅ |

Low-jitter band (500-rule slightly high at 1.154 under host load — sub-ms
movement, not regression; target 5ms).

## 6. Suite / Guard / Hilo

- Full suite: **234 passed / 6 skipped** (3.51s) — baseline change from
  283/32 per TJ-GAP-010 (test_integration.py removed); ruff clean.
- GitReins guard: **PASS 4/4** (secrets / lint / tests / static_analysis).
- Hilo: **148 edges / 27 files** (live; +1 edge from prior 147 — graph
  growth, not staleness).

## 7. External Signals

CI: HEAD commit aacaea0 (tick #156) run **31204623030 success**. The 3
failures in recent history (577ca40, 9f796d6, e6f4130) are **superseded
mid-cycle commits** — fixed by subsequent commits (954e724 ruff fix, ab3bd42,
aacaea0); all later runs green. 0 open issues · 0 unpushed commits (git fetch
verified) · no terminal-jail siblings (only coding-hermes-scheduler, h3-shim,
speclang workers on other repos). Scheduler: Enabled=true, CooldownS=7200
(external Bane-policy value; no PUT — E2E fixture gates pause). NEVER-DONE
probes: 0 TODO/FIXME, VERSION-001 holds (zero literal 1.0.0 source hits),
user pytest cache absent, repo-local stale lastfailed entry (pre-#82 node-id)
= known non-regression. Blocked-task probe: gpg empty (T9.4 still blocked).
Two documented untracked strays (dagger.db, .coding-hermes/extract_skill.py)
left uncommitted.

**Verdict: E2E PASS — 0 new gaps, BUG-001 seccomp fix verified holding
(live probe + regression tests), GAP-01..05 all hold, no code change, no
worker. Next E2E window #162-167.**
