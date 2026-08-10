# Terminal Jail — Diagnostics Trail

*How the system is built, why, the errors hit along the way (ours AND the
project's own history), and the right way to do things. Written 2026-08-10
during the dogfood run. This is explanation, not raw logs.*

## 1. How it's built

- **`standalone/terminal-jail`** (~305 lines of bash): arg parsing
  (`--user/--seccomp/--interruptor/--no-interruptor`), then JSON-bridge call
  to the interruptor engine, then `exec unshare --pid --fork
  --kill-child=SIGKILL [--mount-proc | --user] bash -c 'exec "$@"'`.
  The `--kill-child=SIGKILL` flag kills all descendants when the namespace
  init exits (double-fork protection).
- **`plugin/terminal_jail/interruptor/`** (the real engine):
  `parser.py` (shell tokenizer → segments) → `decider.py` (priority:
  blocklist → allowlist → auto-sandbox → *user rules: NOT IMPLEMENTED*) →
  `matcher.py` (9 match types, regex-based). `interruptor_bridge.py` is the
  stdin/stdout JSON wrapper the CLI talks to.
- **`plugin/terminal_jail/seccomp.py`**: hand-built BPF (stdlib ctypes only,
  no libseccomp), default-allow with explicit denials (mount, pivot_root,
  kexec_load, ...), single-arch x86_64/aarch64. Applied via
  `prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER)`.
- **`plugin/__init__.py`**: Hermes plugin — registers `pre_tool_call`
  (observer/logs only) and `transform_terminal_output` (returns None).
- **`install.sh`**: local-checkout mode ships wrapper + plugin tree +
  seccomp loader to `~/.local/bin` + `~/.local/lib/terminal-jail/`.
- **systemd layer**: `systemd/90-terminal-jail-hardening.conf` — 4 ACTIVE
  directives (`ProtectProc=invisible`, `NoNewPrivileges=true`,
  `ProtectControlGroups=true`, `TasksMax=256`); `PrivateUsers`/
  `RestrictNamespaces`/fs-hardening commented out pending per-host
  verification (this was a P0 spec-vs-reality battle — PM-GAP-001,
  TJ-GAP-008/014/017/018/020 — and the docs now honestly say "lightweight").

## 2. Errors hit during the dogfood run, and what they meant

| Error | Meaning | Right way |
|---|---|---|
| `unshare: unshare failed: Operation not permitted` (rc=1) | host denies unprivileged PID namespaces (this host, Ubuntu 26.04/kernel 7.0.0-28) | documented; use `--user` |
| `ModuleNotFoundError: No module named 'terminal_jail'` from seccomp-loader (installed binary) | loader computes plugin dir as `dirname(dirname(loader))/plugin` = `<prefix>/lib/plugin`, but install.sh ships `<prefix>/lib/terminal-jail/plugin` | loader should walk up from its own file until it finds the package; installed-layout regression test needed (TJ-DF-002) |
| `prctl(PR_SET_SECCOMP) refused the filter: Permission denied (missing CAP_SYS_ADMIN or no_new_privs set?)` | seccomp without `no_new_privs` requires CAP_SYS_ADMIN in the INIT user namespace — never true for unprivileged users | call `prctl(PR_SET_NO_NEW_PRIVS, 1)` first; verified working unprivileged on this host (TJ-DF-003) |
| `COMMAND BLOCKED — interruptor-bridge-unavailable` (rc=126) | bridge not found / crashed → enforce mode fails closed | this is the CORRECT behavior (TJ-GAP-021 fix); `TERMINAL_JAIL_BRIDGE` overrides search |
| `fdisk: cannot open /dev/sda: Permission denied` inside `--user` jail | running as nobody=65534 — privilege drop working as intended | expected |
| `pip install -e .` OK but `import terminal_jail` → ModuleNotFoundError | setuptools find exposes `plugin` (include=`plugin*`), not `terminal_jail` | packaging fix (TJ-DF-006) |
| `terminal-jail: command blocked (builtin-fdisk): ...` rc=126 from `terminal-jail-sh` | shim path working from repo root (TJ-GAP-009 fix) | expected |

## 3. How the project got here (history lessons)

- **v1.0 → v1.1.0**: the plugin used to WRAP commands
  (`transform_command`/`transform_exec_command`). Hermes core has no
  pre-execution transform hook (HOOK-GAP-03), so those functions were dead
  code — removed in TJ-GAP-010 (v1.1.x). The plugin is observability-only
  TODAY; don't try to add command transformation to it, it can't be wired.
- **The interruptor was the pivot**: with the plugin unable to wrap, the
  firewall moved into the CLI as a bash↔python JSON bridge. The bridge
  protocol is the integration point to build on.
- **Quoting bypass (TJ-GAP-005)**: blocklist regexes were bypassed by
  wrapper-quoted argv (`'rm' '-rf' '/'`); fixed with quote-stripping
  normalization in the matcher. The CURRENT bypass class is different:
  flag-order variants of the same command (TJ-DF-001) and the fact that
  regex rules can't see argv structure. Lesson: pattern firewalls need
  token-level (argv) rules, not string regexes, for security-critical
  patterns.
- **BUG-001**: seccomp arch-check BPF jump offsets were inverted (jt/jf are
  relative-to-next), killing every wrapped command with SIGSYS — fixed and
  regressed. Lesson: BPF hand-rolled with ctypes needs live probes; the
  pentest plan (docs/pentest-plan.md PT-004) is the right venue.
- **Premature completion pattern (recurring)**: T11.2 "Rule loader" marked
  complete while the decider never calls it (TJ-DF-004); E2E-001-GAP-01 fixed
  specs but missed README's rule table (TJ-DF-005); TJ-GAP-021 fixed
  missing-bridge fail-open but engine errors still fail open through the
  bridge's `_emit_fail_open` → enforce mode silently runs unfiltered if
  `intercept()` ever raises. The bridge's fail-open design is documented,
  but the CLI never checks `reason` for `[bridge-error]` in enforce mode —
  worth a follow-up probe when user rules (TJ-DF-004) land, since that adds
  a new failure surface.

## 4. The right way to extend this system

1. **Add a rule**: edit the engine's `blocklist.py`/`sandbox.py`/`allowlist.py`
   (builtins) — do NOT rely on user rules until TJ-DF-004 lands.
2. **Add a match type**: `matcher.py`, keep `match_segment` returning the
   matched rule id; add engine tests + a bridge-level probe.
3. **Test the firewall**: engine-level via `intercept()` (fast, no kernel
   deps) + bridge-level via stdin JSON (no execution) + CLI-level only for
   the block box/exit codes (execution on this host needs `--user`).
4. **Verify seccomp work**: `--user --seccomp` + a ctypes `mount()` probe
   must die with SIGSYS once TJ-DF-003 lands; today it prints "running
   without seccomp".
5. **Never** trust README's rule tables without grepping the engine —
   they drifted twice already (TJ-DF-005, E2E-001-GAP-01).
