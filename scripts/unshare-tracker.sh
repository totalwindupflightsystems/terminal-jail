#!/usr/bin/env bash
# unshare-tracker.sh — Track unshare binary capabilities for terminal-jail
# Tests unshare flag combinations and monitors for regressions.
# Part of T10.2: Phase 10 Maintenance — unshare tracking.
#
# Usage: ./unshare-tracker.sh [--json]
#   --json    Output as JSON (default: human-readable)
#
# Designed to run as a cron job. Exits 0 when all expected capabilities
# are present, 1 on capability regression, 2 on runtime error.

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_FILE="${SCRIPT_DIR}/.unshare-tracker-state"
JSON_MODE=false
[[ "$1" == "--json" ]] && JSON_MODE=true

# --- Discover unshare binary ---
UNSHARE=$(which unshare 2>/dev/null || true)
if [[ -z "$UNSHARE" ]]; then
    if $JSON_MODE; then
        echo '{"error": "unshare binary not found", "exit_code": 2}'
    else
        echo "FATAL: unshare binary not found in PATH"
    fi
    exit 2
fi
UNSHARE_VERSION=$("$UNSHARE" --version 2>/dev/null | head -1 || echo "unknown")

# --- Define capability tests ---
# Each test: "name|flags|expected_exit"
# expected_exit: 0=succeeds, non-zero=expected to fail (not a regression)
# Expected exits: 0=succeeds, non-zero=expected to fail on current kernel.
# State tracking detects regressions (pass→fail) and improvements (fail→pass).
declare -a TESTS=(
    "pid_only|--pid --fork|1"
    "user_only|--user|0"
    "user_pid_fork|--user --pid --fork|0"
    "user_pid_fork_kill|--user --pid --fork --kill-child=SIGKILL|0"
    "mount_proc|--mount-proc --fork|1"
    "user_mount_proc|--user --mount-proc --fork|1"
    "map_auto|--user --map-auto --pid --fork|1"
    "map_root_user|--user --map-root-user --pid --fork|1"
    "net_namespace|--net --fork|1"
    "uts_namespace|--uts --fork|1"
    "ipc_namespace|--ipc --fork|1"
)

# --- Run tests ---
declare -A test_results
declare -A test_exit_codes
declare -A test_durations

overall_rc=0
test_count=0

run_test() {
    local name="$1"
    local flags="$2"
    local expected_exit="$3"

    local start_time
    start_time=$(date +%s%N)

    # Run unshare with the flags, capture exit code and stderr
    local actual_exit=0
    local stderr_output=""
    stderr_output=$("$UNSHARE" $flags true 2>&1) || actual_exit=$?

    local end_time
    end_time=$(date +%s%N)
    local duration_ms=$(( (end_time - start_time) / 1000000 ))

    test_exit_codes["$name"]=$actual_exit
    test_durations["$name"]=$duration_ms

    if [[ $actual_exit -eq $expected_exit ]]; then
        test_results["$name"]="pass"
        test_count=$((test_count + 1))
    elif [[ $expected_exit -eq 0 && $actual_exit -ne 0 ]]; then
        test_results["$name"]="fail"
        test_count=$((test_count + 1))
        overall_rc=1
    else
        # Expected failure that fails differently — still as expected
        test_results["$name"]="pass"
        test_count=$((test_count + 1))
    fi
}

for test_def in "${TESTS[@]}"; do
    IFS='|' read -r name flags expected_exit <<< "$test_def"
    run_test "$name" "$flags" "$expected_exit"
done

# --- Track state changes ---
prev_json="{}"
if [[ -f "$STATE_FILE" ]]; then
    prev_json=$(cat "$STATE_FILE" 2>/dev/null || echo "{}")
fi

# --- Build results JSON ---
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
KERNEL=$(uname -r)

# Build capabilities object
capabilities=""
for test_def in "${TESTS[@]}"; do
    IFS='|' read -r name flags expected_exit <<< "$test_def"
    result="${test_results[$name]}"
    exit_code="${test_exit_codes[$name]}"
    duration_ms="${test_durations[$name]}"
    [[ -n "$capabilities" ]] && capabilities+=","
    capabilities+=$(printf '\n    "%s": {"flags": "%s", "result": "%s", "exit_code": %d, "duration_ms": %d}' \
        "$name" "$flags" "$result" "$exit_code" "$duration_ms")
done

# --- Detect regressions AND improvements ---
regressions=""
improvements=""
prev_failures_str=$(echo "$prev_json" | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    caps=d.get('capabilities',{})
    print(','.join(k for k,v in caps.items() if v.get('result')=='fail'))
except: pass" 2>/dev/null || echo "")

new_failures_str=""
new_passes_str=""
for test_def in "${TESTS[@]}"; do
    IFS='|' read -r name flags expected_exit <<< "$test_def"
    if [[ "${test_results[$name]}" == "fail" ]]; then
        [[ -n "$new_failures_str" ]] && new_failures_str+=","
        new_failures_str+="$name"
    else
        [[ -n "$new_passes_str" ]] && new_passes_str+=","
        new_passes_str+="$name"
    fi
done

# Check for regressions: previously-passing test now fails
if [[ -n "$prev_failures_str" ]]; then
    IFS=',' read -ra prev_arr <<< "$prev_failures_str"
    declare -A prev_fail_map
    for f in "${prev_arr[@]}"; do prev_fail_map["$f"]=1; done
    if [[ -n "$new_failures_str" ]]; then
        IFS=',' read -ra new_arr <<< "$new_failures_str"
        for f in "${new_arr[@]}"; do
            if [[ -z "${prev_fail_map[$f]}" ]]; then
                [[ -n "$regressions" ]] && regressions+=","
                regressions+="$f"
            fi
        done
    fi
fi

# Check for improvements: previously-failing test now passes
if [[ -n "$prev_failures_str" && -n "$new_passes_str" ]]; then
    IFS=',' read -ra prev_arr <<< "$prev_failures_str"
    declare -A prev_fail_map2
    for f in "${prev_arr[@]}"; do prev_fail_map2["$f"]=1; done
    IFS=',' read -ra pass_arr <<< "$new_passes_str"
    for f in "${pass_arr[@]}"; do
        if [[ -n "${prev_fail_map2[$f]}" ]]; then
            [[ -n "$improvements" ]] && improvements+=","
            improvements+="$f"
        fi
    done
fi

# Write current state for next run
cap_json="{"
first=true
for test_def in "${TESTS[@]}"; do
    IFS='|' read -r name flags expected_exit <<< "$test_def"
    $first || cap_json+=","
    first=false
    cap_json+=$(printf '"%s":{"result":"%s","exit_code":%d}' \
        "$name" "${test_results[$name]}" "${test_exit_codes[$name]}")
done
cap_json+="}"

echo "{\"timestamp\":\"$TIMESTAMP\",\"kernel\":\"$KERNEL\",\"unshare_version\":\"$UNSHARE_VERSION\",\"unshare_path\":\"$UNSHARE\",\"capabilities\":$cap_json}" > "$STATE_FILE"

# --- Output ---
if $JSON_MODE; then
    cat <<EOF
{
  "timestamp": "$TIMESTAMP",
  "kernel_version": "$KERNEL",
  "unshare": {
    "version": "$UNSHARE_VERSION",
    "path": "$UNSHARE"
  },
  "capabilities": {$capabilities
  },
  "summary": {
    "total": ${#TESTS[@]},
    "passed": $(echo "${test_results[@]}" | grep -o 'pass' | wc -l),
    "failed": $(echo "${test_results[@]}" | grep -o 'fail' | wc -l),
    "regressions": [${regressions}],
    "improvements": [${improvements}]
  },
  "healthy": $([[ $overall_rc -eq 0 ]] && echo true || echo false),
  "exit_code": $overall_rc
}
EOF
else
    echo "=== Terminal-Jail Unshare Tracker ==="
    echo "Timestamp:       $TIMESTAMP"
    echo "Kernel:          $KERNEL"
    echo "unshare:         $UNSHARE_VERSION ($UNSHARE)"
    echo "---"
    printf "%-28s %-8s %-8s %s\n" "TEST" "RESULT" "EXIT" "FLAGS"
    printf "%-28s %-8s %-8s %s\n" "----" "------" "----" "-----"
    for test_def in "${TESTS[@]}"; do
        IFS='|' read -r name flags expected_exit <<< "$test_def"
        result="${test_results[$name]}"
        exit_code="${test_exit_codes[$name]}"
        marker=""
        [[ "$result" == "pass" ]] && marker="✓" || marker="✗"
        printf "%-28s %-8s %-8s %s\n" "$name" "$marker $result" "$exit_code" "$flags"
    done
    echo "---"
    if [[ -n "$regressions" ]]; then
        echo "⚠ REGRESSIONS DETECTED: $regressions"
    else
        echo "✓ No regressions detected"
    fi
    if [[ -n "$improvements" ]]; then
        echo "↑ IMPROVEMENTS DETECTED: $improvements"
    fi
    echo ""
    passed=$(echo "${test_results[@]}" | grep -o 'pass' | wc -l)
    failed=$(echo "${test_results[@]}" | grep -o 'fail' | wc -l)
    echo "Summary: $passed passed, $failed failed, ${#TESTS[@]} total"
    echo "Health:  $([[ $overall_rc -eq 0 ]] && echo '✓ HEALTHY' || echo '✗ WARNING')"
    echo ""
    echo "Suggested cron:  0 */12 * * * cd /home/kara/terminal-jail && scripts/unshare-tracker.sh --json | tee -a logs/unshare-tracker.log"
fi

exit $overall_rc
