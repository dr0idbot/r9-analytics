#!/usr/bin/env bash
# Run the r9_analytics Streamlit dashboard.
# Usage: ./run_dashboard.sh
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"
exec streamlit run dashboard/app.py
