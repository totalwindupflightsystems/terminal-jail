# E2E Task Matrix — terminal-jail (tick #36)

| ID | Task | Pri | Cpx | Deps | Tags | Files |
|----|------|-----|-----|------|------|-------|
| E2E-001-GAP-01 | Align `specs/integration.md:176` auto-sandbox list with the actual 8 built-in sandbox rules (pytest, npm-test, go-test, make, pip, cargo, gcc, script). Remove curl/wget/apt/yum/docker/podman from the sandboxed list (or mark explicitly as blocklist-only via `curl|sh`). Update the T-I37 acceptance wording in integration.md if needed. | P2 | S | none | docs, spec-alignment, interruptor | specs/integration.md |
| E2E-001-GAP-02 | Add a regression test asserting plain `curl -o file URL` / `wget URL` / `apt-get update` / `docker ps` are ALLOWED (not sandboxed) — locks in current engine behavior so the doc-vs-engine contract can't drift again. | P3 | S | E2E-001-GAP-01 | tests, interruptor, contract | plugin/test_interruptor_integration.py |

## Notes

- E2E-001 itself remains a recurring fixture (never marked complete).
- GAP-01 is the doc fix (recommended option a). GAP-02 is optional hardening once the
  doc is truthful — it converts the divergence into a pinned contract test.
- No P0/P1 findings. No browser findings (no browser surface).
