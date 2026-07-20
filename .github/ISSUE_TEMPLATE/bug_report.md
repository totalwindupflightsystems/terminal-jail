---
name: Bug Report
about: Report a bug in terminal-jail
title: "[BUG] "
labels: bug, triage
assignees: ""
---

## Bug Description
A clear and concise description of what the bug is.

## Reproduction Steps
Steps to reproduce the behavior:
1. Run command '...'
2. Observe '...'

## Expected Behavior
A clear description of what you expected to happen.

## Actual Behavior
What actually happened. Include exact error messages, exit codes, and log output.

## Environment
- **OS:** [e.g., Ubuntu 26.04, Debian 12, Arch]
- **Kernel version:** [output of `uname -r`]
- **unshare version:** [output of `unshare --version`]
- **Hermes version:** [e.g., 1.2.3]
- **terminal-jail version:** [output of `terminal-jail --version` or git tag]
- **Plugin mode or standalone CLI?** [plugin / CLI]

## User Namespace Configuration
```bash
# Output of:
cat /proc/sys/kernel/unprivileged_userns_clone
sysctl kernel.unprivileged_userns_clone
```

## Plugin Configuration (if applicable)
```bash
# Output of:
echo $HERMES_TERMINAL_JAIL_ENABLED
echo $HERMES_TERMINAL_JAIL_LOG_LEVEL
echo $MAX_COMMAND_BYTES
```

## Logs
Relevant Hermes gateway logs or terminal-jail plugin logs.

## Additional Context
Any other information that might help. Have you tried the standalone CLI as a fallback?
