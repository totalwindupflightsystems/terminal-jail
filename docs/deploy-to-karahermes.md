## Prompt: Install Terminal-Jail on karaHermes

Run the following on karaHermes-mde-7840hs (Ubuntu 26.04, kernel 7.0.0-27).
You have sudo. Do NOT restart the gateway until all steps are verified.

---

### Step 1 — Install the shell wrapper

```bash
sudo cp /home/kara/terminal-jail/standalone/terminal-jail /usr/local/bin/terminal-jail-bash
sudo chmod 755 /usr/local/bin/terminal-jail-bash
```

### Step 2 — Create the SHELL shim (handles -lic invocation)

The Hermes terminal tool invokes the shell as: `bash -lic "set +m; {command}"`. We need a thin
wrapper that extracts the command, runs it through the interruptor, wraps with unshare, and execs.

```bash
sudo tee /usr/local/bin/terminal-jail-sh << 'SHIM'
#!/bin/bash
# terminal-jail-sh — SHELL replacement for Hermes gateway
# Handles: bash -lic "set +m; COMMAND"
# Extracts COMMAND, evaluates via interruptor, wraps in PID namespace.

INTERRUPTOR_BRIDGE="/home/kara/terminal-jail/plugin/terminal_jail/interruptor_bridge.py"
MODE="${TERMINAL_JAIL_INTERRUPTOR_MODE:-enforce}"

# Extract the actual command from bash -lic "set +m; <command>"
extract_command() {
    local raw="$1"
    # Strip "set +m; " prefix if present
    raw="${raw#set +m; }"
    # Strip leading/trailing whitespace
    raw="${raw#"${raw%%[![:space:]]*}"}"
    raw="${raw%"${raw##*[![:space:]]}"}"
    echo "$raw"
}

# If invoked as a login shell (-l flag), extract command and jail it
if [[ "$*" == *"-c"* ]] || [[ "$*" == *"-lic"* ]]; then
    # Find the -c argument — it's the last argument
    cmd=""
    while [[ $# -gt 0 ]]; do
        if [[ "$1" == "-c" ]]; then
            cmd="$2"
            break
        fi
        shift
    done
    
    cmd=$(extract_command "${cmd:-$*}")
    
    # Run through interruptor if available
    if [[ -f "$INTERRUPTOR_BRIDGE" ]] && [[ "$MODE" != "disabled" ]]; then
        result=$(echo "{\"command\":$(echo "$cmd" | python3 -c "import json,sys; print(json.dumps(sys.stdin.read().rstrip('\n')))")}" | python3 "$INTERRUPTOR_BRIDGE" 2>/dev/null)
        action=$(echo "$result" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('action','allow'))" 2>/dev/null || echo "allow")
        
        if [[ "$action" == "block" ]]; then
            rule_id=$(echo "$result" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('rule_id','unknown'))" 2>/dev/null)
            reason=$(echo "$result" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('reason','Blocked by security policy'))" 2>/dev/null)
            {
                echo "╔══════════════════════════════════════════════════════════╗"
                echo "║  COMMAND BLOCKED — $rule_id"
                echo "╠══════════════════════════════════════════════════════════╣"
                echo "║  $reason"
                echo "╚══════════════════════════════════════════════════════════╝"
            } >&2
            exit 126
        elif [[ "$action" == "modify" ]]; then
            modified=$(echo "$result" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('modified',''))" 2>/dev/null)
            if [[ -n "$modified" ]]; then
                cmd="$modified"
            fi
        fi
    fi
    
    # Execute in PID namespace with seccomp
    export TERMINAL_JAIL_SECCOMP="${TERMINAL_JAIL_SECCOMP:-1}"
    exec /home/kara/terminal-jail/standalone/terminal-jail --user --seccomp "$cmd"
else
    # Interactive shell fallback (shouldn't happen for terminal tool)
    exec /bin/bash "$@"
fi
SHIM
sudo chmod 755 /usr/local/bin/terminal-jail-sh
```

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
