#!/usr/bin/env bash
# Ludwig launcher — always runs cli.py through the project venv (which owns the
# heavy kernels: cadquery, ifcopenshell). A bare `python3 cli.py` picks the
# system interpreter, which lacks cadquery and silently refuses to compile.
#
#   ./run.sh "a steel bracket 80x40x5 with two M8 holes"
#   ./run.sh --selftest
#   ./run.sh --eval --repair
#   ./run.sh --edit out/bracket.py "make it 100mm long"
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
py="$here/.venv/bin/python"

if [[ ! -x "$py" ]]; then
  echo "error: no venv at $here/.venv" >&2
  echo "create it and install deps:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

exec "$py" "$here/cli.py" "$@"
