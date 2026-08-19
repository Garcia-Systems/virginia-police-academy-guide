#!/usr/bin/env sh
set -eu
if [ "$#" -ne 1 ] || { [ "$1" != en ] && [ "$1" != es ]; }; then
  echo "Usage: $0 en|es" >&2
  exit 2
fi
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$SCRIPT_DIR/build_pdf.py" "$1"
