# Security Policy

## Supported Versions

Only the latest release receives security updates.

| Version | Supported |
|---------|-----------|
| 1.1.x   | ✅ |
| 1.0.x   | ❌ |
| < 1.0   | ❌ |

## Reporting a Vulnerability

Report security vulnerabilities privately to the maintainers. Do NOT file public issues.

**Contact:** Open a private security advisory on GitHub.

## Response Timeline

- **Acknowledgment:** Within 72 hours
- **Triage & Assessment:** Within 5 business days
- **Fix Release:** Within 30 days for confirmed vulnerabilities

## Scope

Terminal-jail is a Hermes Agent plugin that wraps terminal commands in Linux PID namespaces for process isolation. Security issues may include:

- PID namespace escapes
- Signal propagation bypasses
- Interruptor rule bypass (Bash command firewall evasion)
- Seccomp filter bypasses
- User namespace privilege escalation
- Configuration injection

## Disclosure

We follow coordinated disclosure. After a fix is released, we will publish a security advisory with:

- Affected versions
- Impact assessment
- Mitigation steps
- Credits to the reporter
