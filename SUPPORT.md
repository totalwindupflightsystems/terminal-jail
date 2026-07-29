# Support Policy

## Getting Help

Terminal-jail is a Hermes Agent plugin for terminal command isolation. Support is provided on a best-effort basis.

**Resources:**

- **Documentation:** [README.md](README.md) — installation, configuration, and usage
- **Specs:** [specs/](specs/) — design specs, integration specs, threat model
- **ADRs:** [docs/](docs/) — architecture decision records
- **Issues:** File bug reports and feature requests on GitHub

## Support Channels

- GitHub Issues: Bug reports, feature requests
- GitHub Discussions: Q&A, configuration help

## Supported Platforms

- Linux kernel 5.11+ (PID namespace support)
- Python 3.11+
- Hermes Agent (plugin system)
- systemd (optional, defense-in-depth hardening)

## Limitations

- Requires unprivileged user namespace support (`kernel.unprivileged_userns_clone=1`)
- `unshare --mount-proc` blocked on some kernel configurations
- Full defense-in-depth requires systemd + sudo (host-level dependency)
- AppArmor may restrict UID mapping (`kernel.apparmor_restrict_unprivileged_userns=1`)
