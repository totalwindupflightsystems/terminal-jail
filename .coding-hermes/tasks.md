# Terminal-Jail Task Board

## Phase 0: Bootstrap
- [x] Plugin skeleton (`plugin/__init__.py`)
- [x] Standalone CLI script
- [x] systemd hardening snippets
- [x] DuckBrain namespace populated
- [x] Scheduler DB registered, cron paused

## Phase 1: SPEC — Write Axiom-Level Specs (BLOCKS all implementation)
Each spec must be exhaustive: exact interfaces, error paths, edge cases, test scenarios. A worker agent given the spec must produce compilable code with zero clarifying questions.

- [x] **S01: Plugin spec** (`specs/plugin.md`)
  - Hook signatures: `terminal.command.transform` and `terminal.command.transform.exec`
  - Input: raw command string → Output: wrapped command string
  - Wrapping: `unshare --pid --fork --mount-proc --kill-child=SIGKILL bash -c <command>`
  - Exit code preservation, stdout/stderr passthrough
  - Graceful degrade when `unshare` not on PATH
  - Error paths: command too long, special chars, nested quotes
  - Test scenarios

- [x] **S02: Standalone CLI spec** (`specs/cli.md`)
  - Interface: `terminal-jail <command> [args...]`
  - Same unshare flags as plugin
  - Preserve stdin/stdout/stderr, preserve exit code
  - `set -e`, `--help`, `--version`
  - Install: `curl .../install.sh | sh`
  - Test scenarios: killpg(1), fork bomb, killall, pip malware

- [x] **S03: systemd hardening spec** (`specs/systemd.md`)
  - Each directive with rationale: ProtectProc, PrivateUsers, RestrictNamespaces, NoNewPrivileges, RestrictAddressFamilies, ProtectSystem, CloseOnExec
  - ReadWritePaths for Hermes writable dirs
  - Compatibility: Ubuntu 24.04/26.04
  - Drop-in file format, load order
  - Verification: `systemd-analyze security`, `systemctl show`

- [x] **S04: Integration spec** (`specs/integration.md`)
  - Defense-in-depth: how plugin + CLI + systemd compose
  - Attack vectors covered by each layer
  - Graceful degradation when a layer is missing
  - Installation order: systemd → plugin → CLI
  - Verification per layer: commands to confirm isolation working

## Phase 2: Implementation
- [x] Write plugin `__init__.py` per S01
- [x] Write standalone CLI per S02
- [x] Write systemd drop-in per S03
- [x] Write install.sh

## Phase 3: Distribution
- [ ] Publish to GitHub
- [ ] Submit PR to Hermes core (opt-in sandbox flag)
- [ ] Publish to Hermes plugin marketplace
