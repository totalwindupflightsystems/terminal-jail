
## Dogfood Findings (2026-09-01)
Verdict: PROMISING-BUT-ROUGH
Promise: {"entry_point":"Standalone CLI wrapper: standalone/terminal-jail (56-line bash script wrapping `unshare --pid --fork --mount-proc --kill-child=SIGKILL bash -c 'exec "$@"'`); plus a JSON bridge firewall API (plugin/terminal_jail/interruptor_bridge.py, reads one JSON command on stdin, returns allow/

- [P1] Firewall bridge fail-open on malformed input is undocumented — Invalid JSON / empty stdin on the interruptor bridge returns action=allow (fail-open) — security-relevant default for a command firewall, documented only in bridge source, absent from README/quickstar
- [P1] Quickstart verify block fails out of the box on this host — 2nd verify command (bare `terminal-jail echo "in jail"`) exits 2 on this EPERM host; the --user fallback is buried in a blockquote and scripts/pidns-capability-probe.py exists but is never surfaced. A
- [P1] Re-running install.sh clobbers customized user rules — install.sh unconditionally overwrites ~/.config/terminal-jail/rules.d/00-builtins.yaml — user rule edits lost on reinstall with no backup or prompt. Also hardcodes $HOME/.local/bin into the PATH-appen
- [P2] Stale rule_id in quickstart bridge example (promise broken) — README/quickstart shows output rule_id "I-BLOCK-001" but the engine emits "builtin-rm-rf-root" — grep target doesn't exist, so doc-driven validation of the firewall fails. One of two explicitly broken
- [P2] warn mode wording misleading on EPERM hosts; --user PATH inheritance undocumented — "warn mode warns, allows" is false on EPERM hosts: firewall passes the command but the namespace layer still exits 2 unless --user is also added. --user jail scrubs USER/LOGNAME/HOME but inherits call
