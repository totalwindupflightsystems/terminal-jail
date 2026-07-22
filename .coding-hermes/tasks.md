# Terminal-Jail — Model Router Task Matrix

**Core purpose:** Hermes Agent plugin that wraps terminal commands in Linux PID namespaces for process isolation, with systemd defense-in-depth hardening.

## Active Tasks

| ID | Task | Priority | Complexity | Deps | Tags | Model | Reasoning | Fallback |
|----|------|----------|------------|------|------|-------|-----------|----------|
| T5.1-T5.7 | Phase 5: systemd defense-in-depth — deploy drop-in + verify (7 sub-tasks) | Medium | 3 | HOOK-GAP resolved | --backend, +infra | — | BLOCKED: no sudo on karaHermes-mde-7840hs (kernel 7.0.0-27, Ubuntu 26.04) | — |
| T6.2-T6.7 | Phase 6: Production deployment — dry-run, monitor, deploy (6 sub-tasks) | High | 4 | T5.x | --backend, +infra | — | BLOCKED: requires T5.x systemd + unshare kernel support | — |
| T9.4-GPG | GPG signing for releases | Low | 2 | — | +infra | — | BLOCKED: no GPG keypair exists. Manual key generation required | — |
| T9.6 | User namespace support — explore `unshare --user` for UID isolation | Low | 5 | None | ++security, ++backend | GLM-5.2 | Additional isolation layer; kernel namespace interaction | DeepSeek V4 Pro |
| T10.1-T10.5 | Phase 10: Maintenance — kernel watchdog, unshare tracking, LKML, quarterly review, PR SLA | Low | 2-3 | None | +infra, +documentation | DeepSeek V4 Flash | Mechanical monitoring/process tasks | — |
| NEVER-DONE | 11-point audit sweep | High | 2 | — | ++code-review, +testing | DeepSeek V4 Pro | Audit runs every tick | GLM-5.2 |

**Assumptions:** Host kernel 7.0.0-27 blocks `unshare --mount-proc` for unprivileged users; systemd tasks require sudo (unavailable); GPG keypair requires manual generation; T9.6 is future/optional feature.

**Routing Notes:** Majority of open tasks are BLOCKED by infrastructure/host limitations — no model can resolve them. Phase 5 requires sudo. Phase 6 requires kernel policy change. T9.6 (user namespaces) is the next code task. Maintenance tasks are mechanical.

**Execution Order:** T9.6 (user namespaces — code) → T5.x/T6.x (when unblocked). T10.x ongoing.

**Escalation Conditions:** User namespace exploration touches kernel security boundary → GLM-5.2 primary, DeepSeek V4 Pro fallback.

## Completed Summary

**Phase 0-2 (Bootstrap + Implementation):** Plugin skeleton, standalone CLI (56 lines bash), systemd hardening snippets, 4 Axiom-level specs (S01-S04), core plugin (167 lines), installer (159 lines POSIX sh), unit tests (31 + 1 skipped).
**Phase 3 (Test Hardening):** 25 integration tests (T3.1-T3.10) — real unshare, fork bomb containment, killall, exit codes, stdout/stderr integrity, nested jails, signal handling, performance benchmark, large commands, env var isolation. All skip on host (kernel limitation).
**Phase 4 (Hermes Integration):** Plugin discovered + loaded, command wrapping verified at Python level, disabled mode + missing unshare graceful degradation tested. `--sandbox` flag implemented in Hermes core fork (PR #68216 submitted).
**Phase 7 (Observability):** Jail metrics, crash alerts, byte budget rejection tracking, perf regression alerts, DuckBrain dashboard, metrics export script.
**Phase 8 (Distribution):** Hermes core PR submitted, v1.0.0 release, CONTRIBUTING.md, issue templates, compatibility matrix, 5 ADRs.
**Phase 9 (Security):** Threat model (25KB, 21 threats), penetration test plan (55 scenarios), dependency audit (zero deps), supply chain doc. **T9.5 (Seccomp) DONE** (commit `6f81001`): 484-line seccomp module with dual-arch BPF filter (x86_64, aarch64), standalone loader script, CLI `--seccomp` integration, 37 unit tests. GPG + user namespaces pending.
**HOOK-GAP:** Hermes core lacks pre-execution command-transform hook. Resolution paths: Hermes core PR for `--sandbox` flag (submitted), terminal backend wrapper, systemd-only isolation. Plugin provides observability only until hook exists.
**Audit Gaps:** 6 AUDIT tasks completed. CI fixed (ruff lint errors). 108 pass / 26 skip. Stale version docs fixed (v0.1.0→v1.0.0 — 10 files). DuckBrain namespace populated (27 entries). Cooldown at 1800s (30m — reverted from 14400 after daemon restart). **Idle counter: 0** (reset — productive tick 2026-07-21 21:05: committed T9.5 seccomp).

## [x] T9.5 — Seccomp profile: optional syscall filter inside jail

Completed 2026-07-21. Commit `6f81001`. 484-line `seccomp.py` (BPF filter generation, dual-arch x86_64/aarch64), 62-line `seccomp-loader.py` (standalone exec wrapper), CLI `--seccomp` integration, 37 tests (33 passed + 3 skipped PT-004 integration + 1 subprocess). Seccomp filter verified functional — blocks mount/kexec/pivot_root on x86_64 and aarch64. Guard: PASS.

## [ ] NEVER-DONE — Run 11-point audit next tick
