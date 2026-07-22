#!/usr/bin/env bash
# kernel-watchdog.sh — Monitor kernel compatibility for terminal-jail
# Checks /proc/sys/kernel/unprivileged_userns_clone and warns if disabled.
# Part of T10.1: Phase 10 Maintenance — kernel compatibility watchdog.
#
# Usage: ./kernel-watchdog.sh [--json]
#   --json    Output as JSON (default: human-readable)
#
# Designed to run as a cron job. Exits 0 when healthy, 1 on warning, 2 on error.

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_FILE="${SCRIPT_DIR}/.kernel-watchdog-state"
JSON_MODE=false
[[ "$1" == "--json" ]] && JSON_MODE=true

# --- Check unprivileged_userns_clone ---
USERNS_CLONE_PATH="/proc/sys/kernel/unprivileged_userns_clone"
if [[ ! -f "$USERNS_CLONE_PATH" ]]; then
    rc=2
    userns_status="missing"
    userns_value="N/A"
    userns_note="Kernel parameter $USERNS_CLONE_PATH not found — unprivileged user namespaces may not be available"
elif ! userns_value=$(cat "$USERNS_CLONE_PATH" 2>/dev/null); then
    rc=2
    userns_status="unreadable"
    userns_value="N/A"
    userns_note="Cannot read $USERNS_CLONE_PATH — permission denied"
elif [[ "$userns_value" == "1" ]]; then
    rc=0
    userns_status="enabled"
    userns_note="Unprivileged user namespaces are enabled"
elif [[ "$userns_value" == "0" ]]; then
    rc=1
    userns_status="disabled"
    userns_note="CRITICAL: Unprivileged user namespaces are DISABLED — terminal-jail PID namespace isolation WILL FAIL"
else
    rc=1
    userns_status="unknown"
    userns_value="$userns_value"
    userns_note="Unexpected value '$userns_value' in $USERNS_CLONE_PATH"
fi

# --- Check previous state ---
prev_value=""
if [[ -f "$STATE_FILE" ]]; then
    prev_value=$(cat "$STATE_FILE" 2>/dev/null)
fi
echo "$userns_value" > "$STATE_FILE"

state_changed=false
if [[ -n "$prev_value" && "$prev_value" != "$userns_value" ]]; then
    state_changed=true
    if [[ "$prev_value" == "1" && "$userns_value" == "0" ]]; then
        rc=1
        userns_note="REGRESSION: unprivileged_userns_clone changed from 1→0 — kernel update disabled user namespaces"
    elif [[ "$prev_value" == "0" && "$userns_value" == "1" ]]; then
        rc=0
        userns_note="RECOVERY: unprivileged_userns_clone restored from 0→1 — user namespaces re-enabled"
    fi
fi

# --- Check unshare binary ---
unshare_path=$(which unshare 2>/dev/null || true)
if [[ -z "$unshare_path" ]]; then
    unshare_available=false
    unshare_version="N/A"
else
    unshare_available=true
    unshare_version=$(unshare --version 2>/dev/null | head -1 || echo "unknown")
fi

# --- Check AppArmor ---
apparmor_restrict=$(cat /proc/sys/kernel/apparmor_restrict_unprivileged_userns 2>/dev/null || echo "unknown")
apparmor_status="unknown"
if [[ "$apparmor_restrict" == "1" ]]; then
    apparmor_status="restrictive"
elif [[ "$apparmor_restrict" == "0" ]]; then
    apparmor_status="permissive"
fi

# --- Output ---
if $JSON_MODE; then
    cat <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "kernel_version": "$(uname -r)",
  "unprivileged_userns_clone": {
    "value": "$userns_value",
    "status": "$userns_status",
    "changed": $state_changed,
    "previous": "${prev_value:-null}",
    "note": "$userns_note"
  },
  "apparmor_restrict_unprivileged_userns": "$apparmor_restrict",
  "apparmor_status": "$apparmor_status",
  "unshare": {
    "available": $unshare_available,
    "path": "${unshare_path:-null}",
    "version": "$unshare_version"
  },
  "healthy": $([[ $rc -eq 0 ]] && echo true || echo false),
  "exit_code": $rc
}
EOF
else
    echo "=== Terminal-Jail Kernel Watchdog ==="
    echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "Kernel:    $(uname -r)"
    echo "---"
    echo "unprivileged_userns_clone: $userns_value ($userns_status)"
    echo "  → $userns_note"
    if $state_changed; then
        echo "  → State changed from '$prev_value' to '$userns_value'"
    fi
    echo "---"
    echo "AppArmor restrict: $apparmor_restrict ($apparmor_status)"
    echo "---"
    echo "unshare: $([[ $unshare_available == true ]] && echo "$unshare_version ($unshare_path)" || echo "NOT FOUND")"
    echo "---"
    echo "Health: $([[ $rc -eq 0 ]] && echo '✓ HEALTHY' || echo '✗ WARNING')"
    echo ""
    echo "Suggested cron:  0 */12 * * * cd /home/kara/terminal-jail && scripts/kernel-watchdog.sh --json | tee -a logs/kernel-watchdog.log"
fi

exit $rc
