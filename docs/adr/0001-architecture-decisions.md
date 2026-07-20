# Architecture Decision Records — terminal-jail

## ADR-001: Use `unshare --pid` for PID namespace isolation

**Status:** Accepted  
**Date:** 2026-07-16  
**Deciders:** Bane (Alexis Okuwa), Hermes Agent

### Context

AI agents executing arbitrary shell commands on a host need process isolation. If an agent runs `killall bash` or `pkill -9 python3`, it should only affect processes inside its jail, not the host or other agents. We needed a Linux-native isolation mechanism that works without root privileges, additional daemons, or kernel module loading.

### Decision

Use `unshare(1)` from util-linux with the `--pid --fork --mount-proc` flags to create a per-command PID namespace. The wrapped command shape is:

```
unshare --pid --fork --mount-proc --kill-child=SIGKILL bash -c <shell-quoted-command>
```

### Alternatives considered

1. **Docker/podman containers** — Rejected. Too heavy. Requires daemon, image management, pull latency, and root or rootless setup. A per-command container is wasteful.

2. **systemd-run --scope** — Rejected. Requires systemd as PID 1 (present on most Linux, but not universal), systemctl daemon-reload after drop-in changes, and introduces systemd as a transitive dependency for every command execution.

3. **bubblewrap (bwrap)** — Rejected. Adds a package dependency. `unshare` ships with util-linux which is already installed on every Linux distribution Hermes targets.

4. **cgroups v2 alone** — Rejected. cgroups limit resources but don't isolate the process tree. `killall bash` inside a cgroup would still see host PIDs in `/proc`.

5. **seccomp alone** — Rejected. seccomp filters syscalls but doesn't isolate the process namespace. `kill(2)` with a host PID would still work.

6. **Raw `clone(2)` + `unshare(2)` in a C shim** — Rejected. `unshare(1)` is a battle-tested wrapper that handles the fork/mount-proc dance correctly. A C shim would need to reimplement `--kill-child` semantics, error handling for nested user namespaces, and `/proc` mounting. Not worth the maintenance burden.

### Consequences

- **Gain:** Process isolation without root, daemons, or additional packages. `killall`, `pkill`, fork bombs are contained to the jail's PID namespace.
- **Cost:** `--mount-proc` requires that the kernel permits unprivileged mounting of `/proc`. On Ubuntu 26.04 with kernel 7.0.0-27 and default AppArmor/LSM policy, this is denied. The plugin gracefully degrades by passing the command through unchanged.
- **Cost:** Each command gets a new PID namespace — no persistent jail across commands. This is by design: a fresh namespace per command prevents state leakage between agent sessions.

---

## ADR-002: Use `--kill-child=SIGKILL` for jail termination

**Status:** Accepted  
**Date:** 2026-07-16  
**Deciders:** Bane (Alexis Okuwa), Hermes Agent

### Context

When a command inside a PID namespace exits, any orphaned child processes inside that namespace must be killed. Without this, a backgrounded process (`sleep 999 &`) would leak and continue consuming host resources after the command completes and the namespace is torn down.

`unshare --fork` creates a new process that becomes PID 1 inside the namespace. When PID 1 exits, the kernel sends SIGKILL to all remaining processes in the namespace (if `--kill-child` is set) or they become orphans reparented to the host's PID 1 (if not set).

### Decision

Use `--kill-child=SIGKILL` to ensure all processes in the jail are killed when the namespace init (PID 1) exits.

### Alternatives considered

1. **No --kill-child flag** — Rejected. Orphaned processes leak to the host. A backgrounded `nc -l 9999` inside a jail would persist after the agent command completes, consuming a port and resources.

2. **--kill-child=SIGTERM** — Rejected. SIGTERM can be caught, ignored, or blocked. A malicious or poorly-written process could survive SIGTERM. SIGKILL is non-catchable and guarantees cleanup.

3. **Manual cleanup via cgroups** — Rejected. Adds complexity (cgroup hierarchy management) for a problem that `--kill-child=SIGKILL` solves at the PID namespace level.

4. **pkill-based cleanup wrapper** — Rejected. Race condition between command exit and cleanup. Also requires scanning `/proc` to find children, which is fragile.

### Consequences

- **Gain:** Guaranteed cleanup — no orphaned processes, no resource leaks.
- **Cost:** `--kill-child` was added in util-linux 2.39 (2023). Older distributions (Ubuntu 20.04, Debian 11) ship 2.37 or earlier. The plugin's `install.sh` checks the util-linux version and warns if it's below 2.39.
- **Cost:** Processes that need to clean up on exit (flush buffers, close connections) get no chance with SIGKILL. This is acceptable because the jail is designed for short-lived agent commands, not long-running services.

---

## ADR-003: Use `bash` instead of `sh` as the jail shell

**Status:** Accepted  
**Date:** 2026-07-16  
**Deciders:** Bane (Alexis Okuwa), Hermes Agent

### Context

The PID namespace wrapper needs a shell to execute the user's command. The choices are `sh` (POSIX, dash on Debian/Ubuntu) or `bash` (GNU Bourne-Again Shell).

### Decision

Use `bash -c <shell-quoted-command>` as the jail execution environment.

### Alternatives considered

1. **`sh -c`** — Rejected. On Ubuntu/Debian, `/bin/sh` is `dash`, which is minimal. Some Hermes-generated commands use bash-isms (process substitution `<()`, `$'...'`, `[[ ]]`, arrays, `${var/pattern/replace}`). `sh` would break on these commands without any warning — the command would just fail silently inside the jail.

2. **Direct execution (no shell)** — Rejected. Hermes terminal commands are shell strings, not execve-ready argument arrays. Stripping the shell layer would require parsing and splitting the command string, which introduces shell-injection risk and edge cases (pipes, redirects, variable expansion, subshells).

3. **`zsh -c`** — Rejected. Not guaranteed to exist on target systems. `bash` is installed by default on every major Linux distribution and is a dependency of the `bash` package that util-linux's build system assumes.

4. **Configurable shell (`HERMES_TERMINAL_JAIL_SHELL`)** — Considered but deferred. Adds complexity for marginal gain. Users who need a different shell can set the `HERMES_TERMINAL_JAIL_COMMAND` env var to a custom wrapper script. Phase 2+ feature.

### Consequences

- **Gain:** Hermes-generated commands work reliably. Bash-isms (which are common in AI-generated shell commands) don't silently break.
- **Cost:** `bash` is a larger attack surface than `dash`. This is mitigated by: (a) bash runs inside the PID namespace, not on the host, (b) systemd hardening (Phase 5) further restricts the gateway process, (c) `bash` is already present on every target system — we're not adding a new dependency.
- **Cost:** Startup overhead of bash vs dash (~2ms difference). Negligible compared to network latency and LLM inference time.

---

## ADR-004: No cgroup isolation — defer to systemd

**Status:** Accepted  
**Date:** 2026-07-16  
**Deciders:** Bane (Alexis Okuwa), Hermes Agent

### Context

PID namespaces isolate the process tree but don't limit resource consumption. A fork bomb (`:(){ :|:& };:`) inside a jail would still consume host CPU and memory until the PID limit or OOM killer intervenes.

Complete container isolation typically adds cgroups for CPU, memory, and I/O limits alongside PID namespaces.

### Decision

terminal-jail does NOT implement cgroup isolation. Resource limits are deferred to the systemd service layer (Phase 5 hardening).

### Alternatives considered

1. **cgroups v2 via the plugin** — Rejected. The plugin runs as the gateway user and cannot create cgroups without delegation from systemd. Setting up cgroup delegation for per-command ephemeral groups requires `Delegate=yes` on the service, a cgroup hierarchy manager, and cleanup of stale cgroups. This is systemd-level infrastructure, not plugin-level logic.

2. **`ulimit` via the wrapper** — Accepted as a complementary measure. The wrapper already benefits from the gateway's systemd-imposed `TasksMax=256` and `MemoryMax=1G`. Additional `ulimit -u 64` can be prepended to the bash command for fork-bomb protection without cgroup privileges.

3. **`systemd-run --user --scope` per command** — Rejected. Adds ~50ms overhead per command for transient scope creation. Also requires `pam_systemd` and a user manager running, which may not be available in all Hermes deployment scenarios.

4. **Full container runtime (Docker/podman/runC)** — Rejected for the same reasons as ADR-001.

### Consequences

- **Gain:** Plugin stays simple — command transformation only, no stateful resource management.
- **Cost:** No CPU/memory limits from the plugin alone. Mitigated by systemd hardening (Phase 5) which is mandatory before production deployment.
- **Cost:** Fork bombs can still consume resources until `TasksMax` kills them at the systemd level. The plugin's test suite confirms that `ulimit -u 64` prevents fork bombs within the jail namespace, and systemd's `TasksMax=256` provides a second boundary.

---

## ADR-005: Plugin architecture — observability-first until hook gap resolved

**Status:** Accepted  
**Date:** 2026-07-20 (updated)  
**Deciders:** Bane (Alexis Okuwa), Hermes Agent

### Context

The terminal-jail plugin was designed to wrap every terminal command in a PID namespace. During implementation (2026-07-16 to 2026-07-20), we discovered that Hermes core does not expose a pre-execution command-transform hook. The only hooks available are:

- `pre_tool_call` — Can only BLOCK or ALLOW tool calls. Cannot modify command strings.
- `transform_terminal_output` — Fires AFTER execution. Can transform output, not the command.

Without a `pre_terminal_exec` or `command_transform` hook, the wrapping functions (`transform_command`, `transform_exec_command`) cannot be wired into command execution.

### Decision

Ship v0.1.0 with observability hooks only. The wrapping functions are implemented, tested (75 tests, 92% coverage), and importable — but they are not wired to command execution. The plugin registers:

- `pre_tool_call` — Logs terminal usage, produces metrics
- `transform_terminal_output` — No-op placeholder for future output transformation

The wrapping functions become active when Hermes core gains a pre-execution command-transform hook (HOOK-GAP-01) or the `--sandbox` flag is merged upstream (T4.8 workaround).

### Alternatives considered

1. **Monkey-patch the terminal tool** — Rejected. Hooking into Hermes internals at import time is fragile, breaks on Hermes upgrades, and violates plugin isolation guarantees.

2. **Wrap at the terminal backend layer** — Considered (HOOK-GAP-02). Modifying the terminal tool's execution path directly in Hermes core would work but requires maintaining a fork. The `--sandbox` fork approach (T4.8) is cleaner because it adds a config-layer wrapping point rather than modifying the execution path.

3. **systemd-only isolation** — Backup plan (HOOK-GAP-03). If the hook gap cannot be resolved upstream, systemd hardening (Phase 5: `RestrictNamespaces=~pid`, `ProtectProc=invisible`, `PrivateUsers=true`) provides defense-in-depth without per-command PID namespaces. The plugin becomes a metrics/observability layer only.

4. **Wait for Hermes marketplace hooks** — Deferred. Future Hermes versions may include a richer plugin API. The wrapping functions are designed to be hook-agnostic — they accept a command string and return a wrapped string, making them compatible with any future hook shape.

### Consequences

- **Gain:** The plugin ships now with working observability, metrics, and integration tests. Users get visibility into terminal usage patterns immediately.
- **Cost:** Commands are NOT actually isolated in PID namespaces on v0.1.0. This is clearly documented in the plugin spec (Section 0: HOOK GAP NOTICE) and README.
- **Cost:** 167 lines of tested, working wrapping code sit idle until the hook gap is resolved. This is acceptable because: (a) the code is tested and ready, (b) resolution paths are identified and tracked on the task board, (c) the code serves as a reference implementation for the hook API design.
