#!/usr/bin/env bash
# Run the r9_analytics CLI.
# Usage: ./run_cli.sh [--LOG DEBUG|INFO|WARNING|ERROR]
set -euo pipefail
cd "$(dirname "$0")"
exec python -m cli.main "$@"
