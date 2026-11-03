#!/usr/bin/env bash
# Locate (or clone) the patched coursera-dl checkout, make sure its virtualenv
# exists, and print the command prefix to use. Safe to run repeatedly.
#
#   eval "$(bash setup.sh)"  # sets REPO and PYTHON; then: "$PYTHON" "$REPO/coursera-dl" ...
#   COURSERA_DL_HOME=/path bash setup.sh   # use a specific checkout
set -euo pipefail

# The patched fork. Upstream coursera-dl/coursera-dl is unmaintained and
# lacks the Python 3.12+ and Coursera v2 API fixes.
: "${COURSERA_DL_REPO:=https://github.com/zl-Venture/coursera-dl.git}"

# -P: resolve symlinks, so a symlinked skill dir still finds the real repo
here="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
candidates=(
  "${COURSERA_DL_HOME:-}"
  "$here/../../../.."          # skill shipped inside the repo (.claude/skills/coursera-dl/scripts)
  "$HOME/PycharmProjects/coursera-dl"
  "$HOME/coursera-dl"
)

repo=""
for c in "${candidates[@]}"; do
  [ -n "$c" ] && [ -f "$c/coursera-dl" ] && [ -f "$c/coursera/coursera_dl.py" ] && [ -f "$c/requirements.txt" ] \
    && { repo="$(cd -P "$c" && pwd -P)"; break; }
done

if [ -z "$repo" ]; then
  repo="$HOME/coursera-dl"
  echo "coursera-dl checkout not found, cloning $COURSERA_DL_REPO into $repo" >&2
  git clone --quiet "$COURSERA_DL_REPO" "$repo"
fi

py=""
for v in venv .venv venv3; do
  [ -x "$repo/$v/bin/python" ] && { py="$repo/$v/bin/python"; break; }
done
if [ -z "$py" ]; then
  echo "creating virtualenv in $repo/venv" >&2
  python3 -m venv "$repo/venv"
  py="$repo/venv/bin/python"
fi

if ! "$py" -c "import requests, bs4, six, attr, configargparse, keyring" 2>/dev/null; then
  echo "installing requirements" >&2
  "$py" -m pip install --quiet -r "$repo/requirements.txt"
fi

echo "REPO=$repo"
echo "PYTHON=$py"
