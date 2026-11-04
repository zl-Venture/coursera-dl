#!/usr/bin/env bash
# Run talkpal-dl with the stored Bearer token injected via the environment, so
# the token never appears on a visible command line, in `ps`, or in logs.
#
#   bash run.sh --list
#   bash run.sh --path ~/TalkPal
#   bash run.sh --course <courseConfigId>
#   bash run.sh --covers       # write courses.json + cover art only (read-only, no chat writes)
#
# Needs only python3 (standard library). If TALKPAL_TOKEN is already exported,
# that value is used and nothing is read from the Keychain.
set -euo pipefail
here="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

# Long-lived session cookie (preferred): lets the tool auto-refresh the access
# token when it expires mid-run, so a full download never stops for a stale JWT.
if [ -z "${TALKPAL_SESSION:-}" ]; then
  if sess="$(bash "$here/session.sh" get 2>/dev/null)"; then
    export TALKPAL_SESSION="$sess"
  fi
fi

# Short-lived access token (optional if a session cookie is stored).
if [ -z "${TALKPAL_TOKEN:-}" ]; then
  if tok="$(bash "$here/token.sh" get 2>/dev/null)"; then
    export TALKPAL_TOKEN="$tok"
  fi
fi

if [ -z "${TALKPAL_TOKEN:-}" ] && [ -z "${TALKPAL_SESSION:-}" ]; then
  echo "No TalkPal credential stored. Store a session cookie (recommended, enables" >&2
  echo "auto-refresh):  bash $here/session.sh set" >&2
  echo "or a one-hour access token:  bash $here/token.sh set" >&2
  exit 1
fi

exec python3 -I "$here/talkpal_dl.py" "$@"
