## Prompt: Install Terminal-Jail on karaHermes

Run the following on karaHermes-mde-7840hs (Ubuntu 26.04, kernel 7.0.0-27).
You have sudo. Do NOT restart the gateway until all steps are verified.

---

### Step 1 — Install the shell wrapper

```bash
sudo cp /home/kara/terminal-jail/standalone/terminal-jail /usr/local/bin/terminal-jail-bash
sudo chmod 755 /usr/local/bin/terminal-jail-bash
```

### Step 2 — Install the SHELL shim (handles -lic invocation)

The Hermes terminal tool invokes the shell as: `bash -lic "set +m; {command}"`. We need a thin
wrapper that extracts the command, runs it through the interruptor, wraps with unshare, and execs.
The canonical wrapper lives in this repo at `standalone/terminal-jail-sh` — install it from there
(do NOT copy a script by hand; the repo copy is the maintained one):

```bash
sudo install -m 755 /home/kara/terminal-jail/standalone/terminal-jail-sh /usr/local/bin/terminal-jail-sh
```

The wrapper resolves its base directory relative to the repo checkout when present, and falls back
to `/usr/local/lib/terminal-jail` (override with `TERMINAL_JAIL_HOME` / `TERMINAL_JAIL_BRIDGE` /
`TERMINAL_JAIL_CLI`). On hosts without `setpriv` it degrades gracefully.

### Step 3 — Verify the shim works

```bash
# Test: simple command
/usr/local/bin/terminal-jail-sh -c "echo hello"
# Expected: "hello"

# Test: blocked command
/usr/local/bin/terminal-jail-sh -c "rm -rf /"
# Expected: error box, exit 126

# Test: sandboxed command
/usr/local/bin/terminal-jail-sh -c "echo pid inside jail: \$\$"
# Expected: PID = 1 (inside namespace)
```

### Step 4 — Deploy systemd hardening (Phase 5)

```bash
sudo mkdir -p /etc/systemd/system/hermes-gateway.service.d
sudo cp /home/kara/terminal-jail/systemd/90-terminal-jail-hardening.conf \
    /etc/systemd/system/hermes-gateway.service.d/
```

### Step 5 — Update gateway unit to use the jail SHELL

```bash
sudo mkdir -p /etc/systemd/system/hermes-gateway.service.d
sudo tee /etc/systemd/system/hermes-gateway.service.d/95-terminal-jail-shell.conf << 'UNIT'
[Service]
Environment="SHELL=/usr/local/bin/terminal-jail-sh"
UNIT
```

### Step 6 — Reload and restart

```bash
sudo systemctl daemon-reload
sudo systemctl restart hermes-gateway
sleep 5
systemctl status hermes-gateway --no-pager -l | head -20
```

### Step 7 — Verify isolation

```bash
# Check that SHELL is set
systemctl show hermes-gateway -p Environment | grep SHELL

# Check that systemd hardening is active
systemd-analyze security hermes-gateway --no-pager 2>/dev/null | tail -5
```

### Rollback (if anything breaks)

```bash
sudo rm /etc/systemd/system/hermes-gateway.service.d/95-terminal-jail-shell.conf
sudo systemctl daemon-reload
sudo systemctl restart hermes-gateway
```

---

**Post-install:** Tell me the output of Step 3 and Step 7 so I can verify.
