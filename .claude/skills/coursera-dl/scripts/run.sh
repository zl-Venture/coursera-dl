#!/usr/bin/env bash
# Run coursera-dl with the stored CAUTH cookie injected, so the cookie never
# appears on a visible command line or in logs.
#
#   bash run.sh --list-courses
#   bash run.sh --path ~/Coursera -sl en french-elementary
#
# If you pass -ca/--cauth or -c/--cookies_file yourself, nothing is injected.
set -euo pipefail
here="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
eval "$(bash "$here/setup.sh")"

auth=()
case " $* " in
  *" -ca "*|*" --cauth "*|*" -c "*|*" --cookies_file "*|*" -n "*|*" --netrc "*) ;;
  *)
    if cauth="$(bash "$here/cauth.sh" get)"; then
      auth=(-ca "$cauth")
    else
      echo "No CAUTH cookie stored. Run:  bash $here/cauth.sh set" >&2
      exit 1
    fi ;;
esac

exec "$PYTHON" "$REPO/coursera-dl" "${auth[@]}" "$@"
