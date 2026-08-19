# Dogfood Log

Real-use runs of this project by the dogfood cron (coding-hermes-dogfood skill).
Verdicts here are based on actually USING the tool, not on test colors.

---

## 2026-08-10 — terminal-jail

- **Verdict:** 🟡 PROMISING-BUT-ROUGH (with P0 security gaps — see findings)
- **Promise:** "Defense-in-depth terminal command containment for Hermes
  Agent: systemd drop-in + observability plugin + standalone CLI (PID
  namespace via unshare) + an interruptor bash command firewall (27 rules,
  allow/block/modify, user-extensible via YAML rules)."
- **Time-to-first-success:** ~1 min (install.sh → `terminal-jail --version`,
  `--user echo` works on this host; plain unshare EPERM is documented).
- **Top 3 findings:**
  1. TJ-DF-001 (P0) — `rm -rf /` rule bypassable: `rm -rf --no-preserve-root /`
     (the form GNU rm actually honors), `rm -r -f /`, `rm --recursive --force /`,
     `rm -rf/` all ALLOWED.
  2. TJ-DF-002/003 (P0/P1) — `--seccomp` is broken in the installed layout
     (loader path resolution crash) AND can never install its filter
     unprivileged (missing PR_SET_NO_NEW_PRIVS) → seccomp layer is decorative
     as shipped.
  3. TJ-DF-004 (P1) — user-defined YAML rules are inert (decider Layer 4
     "Not yet implemented"); TJ-DF-005: README's rule table is fiction
     (mount/umount/su/passwd/apt/chown claimed sandboxed, actually uncontained).
- **What works (verified live):** install.sh local path + installed-binary
  bridge discovery; enforce/warn/disabled/--no-interruptor modes; fail-CLOSED
  when the bridge is missing or crashes (TJ-GAP-021 fix holds); exit-code and
  stdin passthrough; `--user` jail (nobody=65534); 11 builtin blocklist rules
  incl. fork-bomb/kill -9 -1/dd/mkfs/curl|sh; terminal-jail-sh from repo root
  (TJ-GAP-009 fix holds); warn-mode stderr surfacing (TJ-GAP-03 fix holds).
- **Friction count:** ~14 (see docs/dogfood/2026-08-10-integration.md).
- **Artifacts:** docs/dogfood/2026-08-10-integration.md,
  docs/dogfood/diagnostics.md, skills/terminal-jail-usage/SKILL.md,
  board tasks TJ-DF-001..009.
- **Foreman wake:** not needed (cooldown 7200s < 14400s; scheduler healthy).

---

## 2026-08-19 — terminal-jail

- **Verdict:** 🟡 PROMISING-BUT-ROUGH (improved — all 8 prior P0/P1 gaps
  verified FIXED live; 2 new security findings, 1 docs, 1 hygiene)
- **Promise (re-checked):** "Defense-in-depth terminal command containment
  for Hermes Agent: standalone CLI (PID namespace via unshare) + interruptor
  bash command firewall (29 rules, allow/block/modify, user-extensible via
  YAML rules) + observability plugin + lightweight systemd hardening."
- **Time-to-first-success:** < 1 min (install.sh → `--version` →
  `--user echo`; `--user --seccomp` filter verified active via
  /proc/self/status Seccomp: 2).
- **Prior-gap re-verification (all FIXED, live):** TJ-DF-001 rm -rf
  bypasses (7 variants) blocked; TJ-DF-002/003 installed-layout seccomp
  works unprivileged (mount → EPERM errno 1, Seccomp: 2); TJ-DF-004 user
  YAML rules enforced end-to-end (touch → rc=126); TJ-DF-005/010
  docs/packaging aligned (PyYAML declared, `import terminal_jail` works
  after pip install -e .); fail-closed, warn-mode surfacing,
  exit/stdin passthrough, --kill-child, auto-sandbox modify all hold.
- **Top 3 findings (new):**
  1. TJ-DF-011 (P0) — `chmod -R 777 /` (and --recursive/a+rwx/7777/-R
     /etc) ALLOWED: chmod rule pattern can't cross flag tokens — same bug
     class TJ-DF-001 fixed for rm but never applied to chmod; recursive
     world-writable is worse than the blocked plain form.
  2. TJ-DF-012 (P1) — same-ID user rule `action: warn` override is
     SILENT: `rm -rf /` executes with zero warning (Action.WARN unhandled
     in decider, reason dropped); env-mode warn works but rule-level warn
     doesn't.
  3. TJ-DF-013 (P2) — knowledge artifacts stale: usage skill still listed
     TJ-DF-001..008 as open; diagnostics said "user rules: NOT
     IMPLEMENTED" (both refreshed in this run); TJ-DF-014 (P3) — `--user`
     jail leaks $USER/$HOME env.
- **Friction count:** 5 (gateway hardline on probe data strings; install.sh
  invocation form; block-box 60-char truncation; env leak; warn-override
  silence).
- **Artifacts:** docs/dogfood/2026-08-19-integration.md, diagnostics.md
  refreshed (sections 1/4/5), skills/terminal-jail-usage/SKILL.md refreshed
  (v1.1.0), board tasks TJ-DF-011..014, dogfood-log entry.
- **Foreman wake:** YES — PUT CooldownS=900 (was 21600 ≥ 14400, board has
  real work again).
