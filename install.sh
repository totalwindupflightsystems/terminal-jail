#!/bin/sh
# terminal-jail installer — POSIX sh, usable as: curl -fsSL <url> | sh
# or from a repository checkout: ./install.sh
set -eu

# --- defaults ----------------------------------------------------------------
# Capture whether the caller explicitly chose a release base URL BEFORE the
# default is assigned — an explicit TERMINAL_JAIL_BASE_URL means release mode
# even when the script runs from a checkout (test fixtures exercise the
# release path from the repo; curl | sh runs always use release mode).
BASE_URL_EXPLICIT=0
[ -n "${TERMINAL_JAIL_BASE_URL:-}" ] && BASE_URL_EXPLICIT=1
TERMINAL_JAIL_VERSION="${TERMINAL_JAIL_VERSION:-1.1.0}"
TERMINAL_JAIL_INSTALL_DIR="${TERMINAL_JAIL_INSTALL_DIR:-$HOME/.local/bin}"
TERMINAL_JAIL_BASE_URL="${TERMINAL_JAIL_BASE_URL:-https://github.com/totalwindupflightsystems/terminal-jail/releases/download/v${TERMINAL_JAIL_VERSION}}"

# --- source vs release mode --------------------------------------------------
# When run from a repository checkout — invoked relatively (./install.sh or
# install.sh) with standalone/terminal-jail present next to this script — and
# no explicit TERMINAL_JAIL_BASE_URL override, install the local wrapper
# instead of downloading release assets. This keeps the documented install
# path working before (and without) published release assets. Absolute-path
# invocations (sh /path/to/install.sh) and an explicit base URL always select
# release mode — the release-mode tests depend on this.
SCRIPT_DIR=""
LOCAL_WRAPPER=""
case "${0:-}" in
    ./*install.sh|install.sh)
        if [ -n "$0" ] && [ -f "$0" ]; then
            SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd 2>/dev/null || true)"
        fi
        if [ "$BASE_URL_EXPLICIT" -eq 0 ] && [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/standalone/terminal-jail" ]; then
            LOCAL_WRAPPER="$SCRIPT_DIR/standalone/terminal-jail"
        fi
        ;;
esac

# --- preflight ---------------------------------------------------------------
if [ -z "${HOME:-}" ]; then
    echo "terminal-jail installer: HOME is not set; cannot determine install directory" >&2
    exit 1
fi

if [ "$(uname -s)" != "Linux" ]; then
    echo "terminal-jail installer: Terminal Jail requires Linux (detected: $(uname -s))" >&2
    exit 1
fi

ARCH="$(uname -m)"
echo "terminal-jail installer: detected architecture ${ARCH}"

# --- downloader / checksum verifier (release mode only) ----------------------
has_curl=0
has_wget=0
has_sha256sum=0
has_shasum=0
if [ -z "$LOCAL_WRAPPER" ]; then
    if command -v curl >/dev/null 2>&1; then
        has_curl=1
    elif command -v wget >/dev/null 2>&1; then
        has_wget=1
    else
        echo "terminal-jail installer: requires curl or wget (neither found)" >&2
        exit 1
    fi

    if command -v sha256sum >/dev/null 2>&1; then
        has_sha256sum=1
    elif command -v shasum >/dev/null 2>&1; then
        has_shasum=1
    else
        echo "terminal-jail installer: requires sha256sum or shasum (neither found)" >&2
        exit 1
    fi
fi

download() {
    url="$1"
    out="$2"
    if [ "$has_curl" -eq 1 ]; then
        curl -fsSL "$url" -o "$out"
    else
        wget -qO "$out" "$url"
    fi
}

# --- checksum verifier -------------------------------------------------------
# (functions defined for release mode; local-mode installs skip checksum
# verification because the wrapper comes from the trusted checkout)

check_sha256() {
    file="$1"
    expected="$2"
    if [ "$has_sha256sum" -eq 1 ]; then
        echo "${expected}  ${file}" | sha256sum -c >/dev/null 2>&1
    else
        actual="$(shasum -a 256 "$file" | awk '{print $1}')"
        [ "$actual" = "$expected" ]
    fi
}

# --- dependency warnings (non-fatal) -----------------------------------------
if ! command -v bash >/dev/null 2>&1; then
    echo "terminal-jail installer: WARNING — bash is required to run terminal-jail but was not found"
fi
if ! command -v unshare >/dev/null 2>&1; then
    echo "terminal-jail installer: WARNING — unshare (util-linux) is required to run terminal-jail but was not found"
fi

# --- install -----------------------------------------------------------------
mkdir -p "$TERMINAL_JAIL_INSTALL_DIR"

tmpdir="${TERMINAL_JAIL_INSTALL_DIR}"
tmp_payload="${tmpdir}/.terminal-jail.$$"
tmp_checksum="${tmpdir}/.terminal-jail.$$.sha256"

cleanup() {
    rm -f "$tmp_payload" "$tmp_checksum"
}
trap cleanup EXIT INT TERM

echo "terminal-jail installer: installing v${TERMINAL_JAIL_VERSION}..."

if [ -n "$LOCAL_WRAPPER" ]; then
    echo "terminal-jail installer: repository checkout detected — installing local wrapper (${LOCAL_WRAPPER})"
    cp "$LOCAL_WRAPPER" "$tmp_payload"
else
    echo "terminal-jail installer: downloading v${TERMINAL_JAIL_VERSION}..."
    download "${TERMINAL_JAIL_BASE_URL}/terminal-jail" "$tmp_payload"
    download "${TERMINAL_JAIL_BASE_URL}/terminal-jail.sha256" "$tmp_checksum"

    expected="$(awk '{print $1}' "$tmp_checksum")"
    if ! check_sha256 "$tmp_payload" "$expected"; then
        echo "terminal-jail installer: checksum verification FAILED — aborting" >&2
        exit 1
    fi
    echo "terminal-jail installer: checksum OK"
fi

# Integrity sanity check — first line must be the expected shebang.
first_line="$(head -n1 "$tmp_payload")"
if [ "$first_line" != "#!/usr/bin/env bash" ]; then
    echo "terminal-jail installer: downloaded file does not look like terminal-jail (bad shebang)" >&2
    exit 1
fi
if [ ! -s "$tmp_payload" ]; then
    echo "terminal-jail installer: downloaded file is empty" >&2
    exit 1
fi

chmod 0755 "$tmp_payload"
mv "$tmp_payload" "${TERMINAL_JAIL_INSTALL_DIR}/terminal-jail"

echo "terminal-jail installer: installed to ${TERMINAL_JAIL_INSTALL_DIR}/terminal-jail"

# --- PATH setup --------------------------------------------------------------
case ":${PATH}:" in
    *:"${TERMINAL_JAIL_INSTALL_DIR}":*)
        echo "terminal-jail installer: ${TERMINAL_JAIL_INSTALL_DIR} is already on PATH"
        ;;
    *)
        startup_file=""
        for candidate in "$HOME/.profile" "$HOME/.bash_profile" "$HOME/.bashrc" "$HOME/.zshrc"; do
            if [ -f "$candidate" ]; then
                startup_file="$candidate"
                break
            fi
        done
        if [ -z "$startup_file" ] && [ "$TERMINAL_JAIL_INSTALL_DIR" = "$HOME/.local/bin" ]; then
            startup_file="$HOME/.profile"
        fi

        if [ -n "$startup_file" ]; then
            # Check for existing marker or equivalent PATH entry.
            if grep -qF '# terminal-jail' "$startup_file" 2>/dev/null; then
                : # already present
            elif grep -qF "PATH=\"$HOME/.local/bin:\$PATH\"" "$startup_file" 2>/dev/null; then
                : # equivalent entry exists
            elif grep -qF "export PATH=\"$HOME/.local/bin:\$PATH\"" "$startup_file" 2>/dev/null; then
                : # equivalent entry exists
            else
                cat >> "$startup_file" <<'SHELLRC'

# terminal-jail
export PATH="$HOME/.local/bin:$PATH"
SHELLRC
                echo "terminal-jail installer: added PATH entry to ${startup_file}"
            fi
            echo "terminal-jail installer: to use immediately, run: export PATH=\"${TERMINAL_JAIL_INSTALL_DIR}:\$PATH\""
        else
            echo "terminal-jail installer: could not identify a shell startup file."
            echo "  Add the following line to your shell profile:"
            echo "  export PATH=\"${TERMINAL_JAIL_INSTALL_DIR}:\$PATH\""
        fi
        ;;
esac

echo "terminal-jail installer: done."
