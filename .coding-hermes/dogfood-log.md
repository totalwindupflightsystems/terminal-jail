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
