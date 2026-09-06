"""Centralised configuration and path resolution.

All modules resolve paths through this module instead of computing their own
Path(__file__).parent.parent chains. This ensures paths work correctly
regardless of working directory or entry point (CLI vs Streamlit).
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DB_CONFIG_PATH = CONFIG_DIR / "dbconf.yaml"
ROSTER_PATH = CONFIG_DIR / "tickers.csv"
SQL_DIR = PROJECT_ROOT / "sql"

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_db_config(path: Path | None = None) -> dict:
    """Load database configuration from dbconf.yaml.

    Environment variable R9_DB_PASSWORD overrides the YAML password value.

    Args:
        path: Optional path to config file. Defaults to config/dbconf.yaml.

    Returns:
        Dict with keys: host, port, dbname, user, password, schema.
    """
    cfg_path = path or DB_CONFIG_PATH
    with open(cfg_path, "r") as fh:
        cfg = yaml.safe_load(fh)

    # Allow env-var override for password (12-factor)
    env_password = os.environ.get("R9_DB_PASSWORD")
    if env_password:
        cfg["password"] = env_password

    return cfg
