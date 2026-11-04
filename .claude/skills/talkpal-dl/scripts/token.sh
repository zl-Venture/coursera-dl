#!/usr/bin/env bash
# Store / read / clear the TalkPal Bearer access token without putting it in
# shell history, the repo or any world-readable file.
#
#   bash token.sh set          # prompts (input hidden); or pipe the value on stdin
#   bash token.sh get          # prints the stored value (used by run.sh)
#   bash token.sh status       # says whether a value is stored, never prints it
#   bash token.sh clear
#
# Storage, first available wins:
#   1. env TALKPAL_TOKEN (read only, for CI / one-off use)
#   2. macOS Keychain, service "talkpal-dl-token"
#   3. ~/.config/talkpal-dl/token, mode 600
#
# A leading "Bearer " (if you copied the whole header value) is stripped.
set -euo pipefail

service="talkpal-dl-token"
file="${XDG_CONFIG_HOME:-$HOME/.config}/talkpal-dl/token"

have_keychain() { [ "$(uname)" = Darwin ] && command -v security >/dev/null; }

get() {
  if [ -n "${TALKPAL_TOKEN:-}" ]; then printf '%s' "$TALKPAL_TOKEN"; return; fi
  if have_keychain && v="$(security find-generic-password -s "$service" -a "$USER" -w 2>/dev/null)"; then
    printf '%s' "$v"; return
  fi
  if [ -r "$file" ]; then tr -d '\n' < "$file"; return; fi
  return 1
}

set_value() {
  local v
  if [ -t 0 ]; then
    read -r -s -p "Paste the TalkPal access token (input hidden): " v; echo >&2
  else
    v="$(cat)"
  fi
  # Strip surrounding whitespace and an optional "Bearer " prefix.
  v="$(printf '%s' "$v" | tr -d '[:space:]')"
  case "$v" in Bearer*) v="${v#Bearer}" ;; esac
  if [ "${#v}" -lt 20 ]; then
    echo "That does not look like an access token (too short). Copy the whole value." >&2
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
  status) if get >/dev/null 2>&1; then echo "TOKEN: stored"; else echo "TOKEN: not stored"; exit 1; fi ;;
  clear)  clear_value ;;
  *)      sed -n '2,15p' "$0" >&2; exit 2 ;;
esac
