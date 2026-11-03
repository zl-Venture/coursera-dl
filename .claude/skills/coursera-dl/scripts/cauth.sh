#!/usr/bin/env bash
# Store / read / clear the Coursera CAUTH cookie without putting it in shell
# history, the repo or any world-readable file.
#
#   bash cauth.sh set          # prompts (input hidden); or pipe the value on stdin
#   bash cauth.sh get          # prints the stored value (used by run.sh)
#   bash cauth.sh status       # says whether a value is stored, never prints it
#   bash cauth.sh clear
#
# Storage, first available wins:
#   1. env COURSERA_CAUTH (read only, for CI / one-off use)
#   2. macOS Keychain, service "coursera-dl-cauth"
#   3. ~/.config/coursera-dl/cauth, mode 600
set -euo pipefail

service="coursera-dl-cauth"
file="${XDG_CONFIG_HOME:-$HOME/.config}/coursera-dl/cauth"

have_keychain() { [ "$(uname)" = Darwin ] && command -v security >/dev/null; }

get() {
  if [ -n "${COURSERA_CAUTH:-}" ]; then printf '%s' "$COURSERA_CAUTH"; return; fi
  if have_keychain && v="$(security find-generic-password -s "$service" -a "$USER" -w 2>/dev/null)"; then
    printf '%s' "$v"; return
  fi
  if [ -r "$file" ]; then tr -d '\n' < "$file"; return; fi
  return 1
}

set_value() {
  local v
  if [ -t 0 ]; then
    read -r -s -p "Paste the CAUTH cookie value (input hidden): " v; echo >&2
  else
    v="$(cat)"
  fi
  v="$(printf '%s' "$v" | tr -d '[:space:]')"
  if [ "${#v}" -lt 100 ]; then
    echo "That does not look like a CAUTH value (too short). Copy the whole Value cell." >&2
    exit 1
  fi
  if have_keychain; then
    security add-generic-password -U -s "$service" -a "$USER" -w "$v" >/dev/null
    echo "Stored in the macOS Keychain (service $service)." >&2
  else
    mkdir -p "$(dirname "$file")"
    (umask 077; printf '%s' "$v" > "$file")
    echo "Stored in $file (mode 600)." >&2
  fi
}

clear_value() {
  have_keychain && security delete-generic-password -s "$service" -a "$USER" >/dev/null 2>&1 || true
  rm -f "$file"
  echo "Cleared." >&2
}

case "${1:-}" in
  get)    get ;;
  set)    set_value ;;
  status) if get >/dev/null 2>&1; then echo "CAUTH: stored"; else echo "CAUTH: not stored"; exit 1; fi ;;
  clear)  clear_value ;;
  *)      sed -n '2,15p' "$0" >&2; exit 2 ;;
esac
