# Terminal-Jail — Model Router Task Matrix

> **Core purpose:** Hermes Agent Python plugin that wraps terminal commands in Linux PID namespaces for process isolation, with systemd defense-in-depth hardening. Now adding a Bash command firewall (Interruptor) that sits between LLM and bash execution.
> **Language:** Python/Bash | **CI:** GitHub Actions | **Status:** v1.0.0 released. Phase 11 active (Interruptor Bash Engine — 17 tasks).

## Active Tasks

| ID | Task | Pri | Cpx | Deps | Tags | Model | Lvl | Fallback |
|----|------|-----|-----|------|------|-------|-----|----------|
| **Phase 11.1: Core Engine** | | | | | | | | |
| T11.1 | ✅ Parser — tokenize shell commands (pipes, redirects, cmd substitution, heredocs, variable expansion, quoting). Fail-open to passthrough. | High | 5 | — | ++python, ++parsing, ++shell | MiniMax-M3 | High | DeepSeek V4 Pro |
| T11.2 | ✅ Rule loader — load YAML rules from /etc/terminal-jail/rules.d/ and ~/.config/terminal-jail/rules.d/ in lexical order. User rules override system. | High | 2 | — | ++python, ++yaml, ++config | MiniMax-M3 | Low | DeepSeek V4 Flash |
| T11.3 | ✅ Pattern matcher — match parsed commands against 9 match types: pattern, command, pipeline, subcommand, path, composite, syscall, network, heredoc | High | 4 | T11.1 | ++python, ++regex, ++pattern-matching | MiniMax-M3 | High | DeepSeek V4 Pro |
| T11.4 | ✅ Decider — evaluate rules in priority order (blocklist first, then allowlist, then auto-sandbox, then user rules). First match wins. | High | 3 | T11.2, T11.3 | ++python, ++logic | MiniMax-M3 | Medium | DeepSeek V4 Pro |
| T11.5 | ✅ Built-in rules — implement 27 hardcoded rules: 10 critical blocklist, 8 auto-sandbox, 9 always-allow | High | 3 | T11.4 | ++python, ++security | MiniMax-M3 | Medium | DeepSeek V4 Pro |
| **Phase 11.2: Shell Integration** | | | | | | | | |
| T11.6 | ✅ Shell wrapper — integrate interruptor into standalone/terminal-jail. JSON protocol between bash and Python. | High | 4 | T11.5 | ++bash, ++python, ++integration | DeepSeek V4 Pro | High | MiniMax-M3 |
| T11.7 | ✅ Output formatting — pretty-print blocked command box, sandbox notice. Configurable theme (box-drawing vs plain ASCII) | Low | 2 | T11.6 | ++python, ++ui-text | MiniMax-M3 | Low | DeepSeek V4 Flash |
| T11.8 | ✅ Mode switching — TERMINAL_JAIL_INTERRUPTOR_MODE: enforce/warn/disabled. Config loaded from env vars. | Medium | 2 | T11.6 | ++python, ++config | MiniMax-M3 | Low | DeepSeek V4 Flash |
| **Phase 11.3: Testing** | | | | | | | | |
| T11.9 | ✅ Blocklist tests (T-I01 through T-I10) — 10 critical block patterns | High | 2 | T11.5 | ++testing, ++python | Step 3.7 Flash | Medium | MiniMax-M3 |
| T11.10 | ✅ Auto-sandbox tests (T-I11 through T-I16) — 6 sandbox patterns | Medium | 2 | T11.5 | ++testing, ++python | Step 3.7 Flash | Medium | MiniMax-M3 |
| T11.11 | ✅ Allowlist tests (T-I17 through T-I26) — 10 always-allow patterns | Medium | 2 | T11.5 | ++testing, ++python | Step 3.7 Flash | Medium | MiniMax-M3 |
| T11.12 | ✅ Parser tests (T-I27 through T-I33) — 7 parser edge cases | Medium | 2 | T11.1 | ++testing, ++python | Step 3.7 Flash | Medium | MiniMax-M3 |
| T11.13 | ✅ Mode tests (T-I34 through T-I36) — 3 mode switching tests | Low | 1 | T11.8 | ++testing, ++python | Step 3.7 Flash | Minimal | MiniMax-M3 |
| T11.14 | ✅ Integration tests (T-I37 through T-I40) — interruptor + unshare compose, custom rules, priority ordering, hot-reload | Medium | 3 | T11.6 | ++testing, ++integration | Step 3.7 Flash | Medium | DeepSeek V4 Pro |
| **Phase 11.4: Distribution** | | | | | | | | |
| T11.15 | ✅ Default rules package — ship /etc/terminal-jail/rules.d/00-builtins.yaml | Low | 1 | T11.5 | ++python, ++packaging | MiniMax-M3 | Minimal | DeepSeek V4 Flash |
| T11.16 | ✅ S06 Integration spec — update specs/integration.md with interruptor layer, defense-in-depth diagram | Low | 2 | T11.6 | ++docs, ++spec | DeepSeek V4 Flash | Low | GPT-5.6 Terra |
| T11.17 | ✅ Performance benchmarks — cold start <50ms, warm start <5ms, 1KB parse <10ms, 500-rule eval <5ms. CI benchmark job | Medium | 3 | T11.6 | ++performance, ++benchmark | Step 3.7 Flash | Medium | DeepSeek V4 Pro |
| **Blocked (host-level)** | | | | | | | | |
| T5.1-T5.7 | Phase 5: systemd defense-in-depth (7 sub-tasks) | Medium | 3 | — | — | BLOCKED: no sudo on host | — | — |
| T6.2-T6.7 | Phase 6: Production deployment (6 sub-tasks) | High | 4 | T5.x | — | BLOCKED: requires T5.x + unshare kernel support | — | — |
| T9.4-GPG | GPG signing for releases | Low | 2 | — | — | BLOCKED: no GPG keypair. Manual generation required | — | — |
| **Continuous** | | | | | | | | |
| E2E-001 | E2E Testing Tick (self-improving loop) 🔁 Recurring every 5-10 ticks | High | 4 | — | ++browser, ++screenshots, ++verification | GPT-5.6 Luna | High | Step 3.7 Flash |
| NEVER-DONE | 12-point audit sweep | High | 2 | — | ++code-review, +testing | DeepSeek V4 Pro | Medium | GLM-5.2 |

## Completed

v1.0.0 released. All core features (PID namespace jail, seccomp, user namespaces, observability, distribution) complete. Phase 11 Interruptor Bash Engine: **17 of 17 tasks complete** (all tasks ✅).

| Phase | Purpose | Key outcomes |
|-------|---------|--------------|
| P0-2: Bootstrap | Plugin skeleton, CLI, systemd hardening, 4 specs, core plugin, installer | 31 unit tests |
| P3: Test hardening | Integration tests — unshare, fork bomb, killall, signals, performance | 25 skip on host |
| P4: Hermes integration | Plugin loaded, command wrapping, disabled mode, --sandbox PR | PR #68216 submitted |
| P7: Observability | Metrics, crash alerts, byte budget tracking, DuckBrain dashboard | Metrics export script |
| P8: Distribution | v1.0.0 release, CONTRIBUTING, issue templates, 5 ADRs | OSS ready |
| P9: Security | Threat model, pentest plan, seccomp (484 lines), user namespaces, supply chain doc | Zero deps, 37 seccomp tests |
| P10: Maintenance | Kernel watchdog, LKML monitoring guide, quarterly checklist, PR/issue SLA, ruff 0.16.0 CI fix (69ddcf5) | CI green |
| **P11: Interruptor** | **Bash command firewall — parser, matcher, decider, built-in rules, shell wrapper, output, config, tests, spec, benchmarks** | **213 tests, 14 modules, 56 spec tests, 4-layer integration spec** |
| U01: Audit | 6 gaps found, all fixed — version staleness, metrics gaps, test coverage, env var docs | 207 pass, 29 skip |

## Assumptions

- Host kernel 7.0.0-27 blocks `unshare --mount-proc` for unprivileged users
- Systemd tasks require sudo (unavailable on karaHermes-mde-7840hs)
- GPG keypair requires manual generation
- AppArmor blocks UID mapping (kernel.apparmor_restrict_unprivileged_userns=1)
- Zero external Python deps — no vulnerability surface
- Cooldown reversion persists (10+ daemon restart reversions) — fleet TOML root cause

## Routing Notes

- **Python implementation (T11.1-T11.8):** MiniMax-M3 primary (flat-rate prepaid) for bounded Python tasks. Escalate to V4 Pro for complex parsing/regex
- **Python testing (T11.9-T11.14):** Step 3.7 Flash primary ($0.09/1M, fastest budget test runner). Escalate to V4 Pro for integration debugging
- **Bash/packaging (T11.6):** V4 Pro — requires multi-language (Bash + Python integration), concurrency considerations
- **Docs/specs (T11.16):** V4 Flash for mechanical docs
- **Performance benchmarks (T11.17):** Tested locally — all 4 metrics PASS with wide margins
- **NEVER-DONE audit:** Foreman-direct (V4 Pro)
- BLOCKED tasks (T5.x, T6.x, T9.4) — no model can resolve host-level blockers

## Execution Order

1. ✅ T11.1 (Parser — foundational) → ✅ T11.2 + ✅ T11.3 (Rule loader + Matcher — parallel)
2. ✅ T11.4 (Decider) → ✅ T11.5 (Built-in rules)
3. ✅ T11.6 (Shell wrapper — integration point) → ✅ T11.7 + ✅ T11.8 (parallel)
4. ✅ T11.9 through ✅ T11.14 (all tests — parallel, after respective implementations)
5. ✅ T11.15 + ✅ T11.16 + ✅ T11.17 (Distribution — parallel, final)
6. **Phase 11 COMPLETE** — all 17/17 tasks ✅

## Escalation Conditions

- Parser (T11.1) complexity exceeds MiniMax-M3 range (>5) → escalate to V4 Pro
- Shell wrapper (T11.6) bash/Python integration fails → escalate to V4 Pro High
- Integration tests (T11.14) reveal sandbox escape → CRITICAL, escalate to GPT-5.6 Sol
- Host kernel/sudo blockers resolved → re-activate T5.x/T6.x with V4 Pro/GLM-5.2
- Performance benchmarks (T11.17) exceed 50ms cold start → investigate with V4 Pro
