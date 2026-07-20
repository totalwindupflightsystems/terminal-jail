# terminal-jail Compatibility Matrix

## Kernel Compatibility

| Kernel Version | User Namespaces | PID Namespaces | --mount-proc | Status |
|---------------|-----------------|----------------|--------------|--------|
| 5.4 LTS | ✅ | ✅ | ✅ | Supported |
| 5.10 LTS | ✅ | ✅ | ✅ | Supported |
| 5.15 LTS | ✅ | ✅ | ✅ | Supported |
| 6.1 LTS | ✅ | ✅ | ✅ | Supported |
| 6.6 LTS | ✅ | ✅ | ✅ | Supported |
| 7.0+ | ✅ | ✅ | ⚠️ Varies by distro | Conditional |

**Key:** ✅ = Works, ⚠️ = May require configuration, ❌ = Not supported

### Kernel Configuration Requirements

For the plugin's PID namespace isolation to work, the following kernel parameters may need to be enabled:

```bash
# Required on some distributions (Debian, Ubuntu ≥ 23.10)
kernel.unprivileged_userns_clone=1

# May be restricted by LSM (AppArmor/SELinux)
# Check with: sysctl kernel.unprivileged_userns_clone
```

### Known Host Limitations

- **Ubuntu 26.04 (kernel 7.0.0-27):** `unshare --mount-proc` requires privileges unavailable in unprivileged user namespaces. The plugin wraps commands correctly but actual PID namespace isolation fails at the OS level. The standalone CLI and systemd drop-in remain viable alternatives.
- **Debian 12 (kernel 6.1):** Works with `kernel.unprivileged_userns_clone=1`.
- **Arch Linux (kernel 6.x+):** User namespaces enabled by default. Full functionality.

## Hermes Agent Compatibility

| Hermes Version | Plugin Discovery | pre_tool_call Hook | --sandbox Flag | Status |
|---------------|------------------|-------------------|----------------|--------|
| < 1.0 | ❌ | ❌ | ❌ | Not supported |
| 1.0 - current | ✅ | ✅ (observe only) | ❌ | Observability only |
| Future (PR #68216) | ✅ | ✅ | ✅ | Full isolation |

The plugin currently provides **observability** (command logging, metrics) on all supported Hermes versions. Full PID namespace wrapping requires either:
- The `--sandbox` flag from [PR #68216](https://github.com/NousResearch/hermes-agent/pull/68216) to be merged upstream, or
- A `pre_terminal_command` hook in Hermes core

### Fallback: Backend-Layer Wrapping

On the `totalwindupflightsystems/hermes-agent` fork (branch `fix/cron-repeat-int-format`), the terminal backend wraps commands with `unshare --pid --fork --mount-proc --kill-child=SIGKILL` when `HERMES_TERMINAL_JAIL_ENABLED=true`. This bypasses the plugin layer entirely.

## util-linux (unshare) Compatibility

| util-linux Version | --pid | --fork | --mount-proc | --kill-child |
|-------------------|-------|--------|-------------|-------------|
| 2.34+ | ✅ | ✅ | ✅ | ❌ |
| 2.38+ | ✅ | ✅ | ✅ | ✅ |
| 2.40+ | ✅ | ✅ | ✅ | ✅ |

`--kill-child=SIGKILL` requires util-linux ≥ 2.38. Earlier versions will still create the PID namespace but cannot guarantee child process cleanup on jail exit.

## Distribution Compatibility

| Distribution | Plugin | CLI | systemd Drop-in | Notes |
|-------------|--------|-----|----------------|-------|
| Ubuntu 24.04 LTS | ✅ | ✅ | ✅ | May need `kernel.unprivileged_userns_clone=1` |
| Ubuntu 26.04 LTS | ⚠️ | ✅ | ✅ | Plugin isolation blocked (see host limitations) |
| Debian 12 | ✅ | ✅ | ✅ | Works with userns enabled |
| Debian 13 | ✅ | ✅ | ✅ | Expected to work |
| Arch Linux | ✅ | ✅ | ✅ | Full support |
| Fedora 40+ | ✅ | ✅ | ✅ | User namespaces enabled |
| RHEL 9+ | ⚠️ | ✅ | ✅ | Check SELinux policies |
| Alpine 3.19+ | ✅ | ✅ | ✅ | Uses BusyBox unshare (subset of flags) |
| macOS | ❌ | ❌ | ❌ | No Linux namespaces |
| WSL2 | ⚠️ | ⚠️ | ❌ | Kernel namespaces may be restricted |

## Python Compatibility

| Python Version | Plugin | Tests |
|---------------|--------|-------|
| 3.9 | ✅ | ✅ (CI) |
| 3.10 | ✅ | ✅ (CI) |
| 3.11 | ✅ | ✅ (CI, primary dev) |
| 3.12 | ✅ | Planned |
| 3.13 | ✅ | Planned |
| 3.14 | ✅ | Planned |

## Test Compatibility Notes

- 108 unit/functional tests run on any system with Python ≥ 3.9
- 25 integration tests require `unshare --user --pid --fork --mount-proc` support and will skip otherwise
- Fork bomb containment test (`test_t32_fork_bomb_containment`) requires `ulimit -u` support
- Performance benchmark test requires ≥ 100 iterations for statistical significance

## Reporting Compatibility Issues

If terminal-jail doesn't work on your system:
1. Check the compatibility matrix above
2. Try the standalone CLI as a fallback: `standalone/terminal-jail your-command`
3. Verify kernel config: `sysctl kernel.unprivileged_userns_clone`
4. File a bug report with the template in `.github/ISSUE_TEMPLATE/bug_report.md`
