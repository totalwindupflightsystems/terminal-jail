# Supply Chain Security — terminal-jail

**Task:** T9.4  
**Date:** 2026-07-20

---

## Current State

### install.sh Security Review

The installer (`install.sh`, 159 lines) has been audited. Security properties:

| Property | Status | Detail |
|----------|--------|--------|
| No `curl \| sh` pattern | PASS | Downloads to temp file, verifies checksum, then moves |
| SHA256 verification | PASS | Checksum file downloaded separately, verified before execution |
| Shebang sanity check | PASS | Verifies first line is `#!/usr/bin/env bash` |
| Empty file check | PASS | Rejects zero-byte downloads |
| Temp file cleanup | PASS | `trap cleanup EXIT INT TERM` removes temp files |
| No system directories | PASS | Installs to `$HOME/.local/bin`, no `sudo` |
| Shell profile modification | LOW RISK | Adds PATH entry; gated by existence checks |
| Checksum source | MITIGATED | Checksum downloaded from same release — relies on GitHub Release integrity |

### GPG Signing

**Status: NOT IMPLEMENTED.** No GPG keypair exists on this host.

Required steps (manual, not automatable by foreman):
1. Generate GPG key: `gpg --full-generate-key`
2. Export public key: `gpg --armor --export KEYID > release-key.asc`
3. Sign releases: `gpg --armor --detach-sign terminal-jail > terminal-jail.asc`
4. Update install.sh to verify GPG signature in addition to SHA256
5. Publish public key on GitHub / keyservers

### GitHub Release Integrity

Current release (v1.0.0) is published on GitHub Releases. GitHub provides:
- TLS (HTTPS) for download transport
- Authenticated upload (GitHub OAuth/token required to publish)
- Tag immutability (git tags can't be changed without force-push)

This is adequate for an initial release but not defense-in-depth.

---

## Recommendations

1. **GPG-sign v1.0.1 release** — generate key, sign binary, update install.sh to verify
2. **SLSA provenance** — generate SLSA Level 2 provenance for the standalone CLI binary (the plugin itself is source-distributed)
3. **Release key rotation policy** — document key expiry and revocation process
4. **Reproducible build** — the standalone CLI is a 56-line bash script; reproducible by definition

---

## Verdict

install.sh is secure against the most common supply chain attacks (no pipe-to-sh, checksum verification, integrity checks). The remaining gap is GPG signing, which requires manual key generation.
