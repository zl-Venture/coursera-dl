#!/usr/bin/env bash
# Store / read / clear the TalkPal Auth.js SESSION COOKIE (the long-lived login
# credential the web app holds). It is used to mint fresh short-lived access
# tokens via https://app.talkpal.ai/api/auth/refresh, so you set it once instead
# of re-copying an accessToken every hour.
#
#   bash session.sh set        # prompts (input hidden); or pipe the value on stdin
#   bash session.sh get        # prints the stored value (used by run.sh)
#   bash session.sh status     # says whether a value is stored, never prints it
#   bash session.sh clear
#
# What to copy: log in at app.talkpal.ai, DevTools -> Application -> Storage ->
# Cookies -> https://app.talkpal.ai -> value of  __Secure-authjs.session-token
# (it is HttpOnly, so it does not show up in document.cookie / sessionStorage;
# copy it from the Cookies panel). Paste just the value.
#
# Storage, first available wins:
#   1. env TALKPAL_SESSION (read only)
#   2. macOS Keychain, service "talkpal-dl-session"
#   3. ~/.config/talkpal-dl/session, mode 600
#
# This cookie is a full login credential: never echo it, never commit it, never
# quote it in errors. Refer to it as "the session cookie".
set -euo pipefail

service="talkpal-dl-session"
file="${XDG_CONFIG_HOME:-$HOME/.config}/talkpal-dl/session"

have_keychain() { [ "$(uname)" = Darwin ] && command -v security >/dev/null; }

get() {
  if [ -n "${TALKPAL_SESSION:-}" ]; then printf '%s' "$TALKPAL_SESSION"; return; fi
  if have_keychain && v="$(security find-generic-password -s "$service" -a "$USER" -w 2>/dev/null)"; then
    printf '%s' "$v"; return
  fi
  if [ -r "$file" ]; then tr -d '\n' < "$file"; return; fi
  return 1
}

set_value() {
  local v
  if [ -t 0 ]; then
    read -r -s -p "Paste the __Secure-authjs.session-token value (hidden): " v; echo >&2
  else
    v="$(cat)"
  fi
  # Strip surrounding whitespace and an optional "name=" prefix if the whole
  # cookie pair was pasted.
  v="$(printf '%s' "$v" | tr -d '[:space:]')"
  case "$v" in __Secure-authjs.session-token=*) v="${v#__Secure-authjs.session-token=}" ;; esac
  if [ "${#v}" -lt 20 ]; then
    echo "That does not look like a session cookie (too short). Copy the whole value." >&2
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
  status) if get >/dev/null 2>&1; then echo "SESSION: stored"; else echo "SESSION: not stored"; exit 1; fi ;;
  clear)  clear_value ;;
  *)      sed -n '2,19p' "$0" >&2; exit 2 ;;
esac
