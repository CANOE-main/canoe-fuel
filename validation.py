"""Pre-write validation: check that canoe-base DB is consistent with config."""
from __future__ import annotations

import logging
import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common import CANOEFuelConfig

logger = logging.getLogger(__name__)


def check_missing_periods(conn: sqlite3.Connection, future_periods: list[int]) -> list[int]:
    cur = conn.execute(
        "SELECT period FROM time_period WHERE flag = 'f'",
    )
    present = {row[0] for row in cur.fetchall()}
    return [p for p in future_periods if p not in present]


def check_missing_regions(conn: sqlite3.Connection, province_list: list[str]) -> list[str]:
    cur = conn.execute("SELECT region FROM region")
    present = {row[0] for row in cur.fetchall()}
    # CAN is a national aggregate used for data_id namespacing only, not a DB region row
    return [p for p in province_list if p != "CAN" and p not in present]


def validate_db_against_config(cfg: "CANOEFuelConfig", conn: sqlite3.Connection) -> None:
    """Raise (or warn) if the canoe-base DB is missing periods or regions the module needs."""
    missing_periods = check_missing_periods(conn, cfg.future_periods)
    if missing_periods:
        msg = (
            f"canoe-fuel: periods {missing_periods} are in config but absent from "
            f"time_period (flag='f') in the database."
        )
        if cfg.validation_behavior == "error":
            raise ValueError(msg)
        logger.warning(msg)

    missing_regions = check_missing_regions(conn, cfg.province_list)
    if missing_regions:
        msg = (
            f"canoe-fuel: regions {missing_regions} are in province_list but absent "
            f"from the region table in the database."
        )
        if cfg.validation_behavior == "error":
            raise ValueError(msg)
        logger.warning(msg)
