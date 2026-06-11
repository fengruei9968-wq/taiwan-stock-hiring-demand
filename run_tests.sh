#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PYTHON="${HIRING_TEST_PYTHON:-$SCRIPT_DIR/venv/bin/python3}"
TMP_BASE="${HIRING_TEST_TMPDIR:-$SCRIPT_DIR/_test_runtime/tmp}"

if [ ! -x "$PYTHON" ]; then
    echo "Python venv not found or not executable: $PYTHON" >&2
    exit 1
fi

mkdir -p "$TMP_BASE"
export TMPDIR="$TMP_BASE"

cd "$SCRIPT_DIR"

if [ "$#" -eq 0 ]; then
    exec "$PYTHON" -m unittest discover -s tests
fi

exec "$PYTHON" -m unittest "$@"
