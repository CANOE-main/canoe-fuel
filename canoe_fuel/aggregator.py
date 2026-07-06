"""End-to-end orchestrator for the fuel pipeline."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from canoe_fuel.common import CANOEFuelConfig
from canoe_fuel.eia_api import load_cached, fetch_and_cache
from canoe_fuel.setup import load_fuel_list, build_cost_frame
from canoe_fuel.validation import validate_db_against_config
from canoe_fuel.techcom import build_comm_and_tech
from canoe_fuel.efficiency import build_mapping, add_efficiency
from canoe_fuel.costvariable import build_costvariable
from canoe_fuel.emissionactivity import build_emission_activity
from canoe_fuel.postprocessing import add_metadata

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def run() -> None:
    cfg = CANOEFuelConfig.validate_from_yaml()
    db_path = Path(cfg.db_dir)
    if not db_path.is_file():
        raise FileNotFoundError(db_path)

    # with sqlite3.connect(db_path) as conn:
    with sqlite3.connect(f"file:{db_path}?mode=rw", uri=True) as conn:
        validate_db_against_config(cfg, conn)

        # Acquire EIA data (from cache or API)
        cache_path = Path("cache/dataframes.pkl")
        try:
            df_raw = load_cached(cache_path)
            logger.info("Loaded EIA cache: %d rows", len(df_raw))
        except FileNotFoundError:
            api_key = ""  # set via environment or secrets management
            df_raw = fetch_and_cache(cfg.eia_year, api_key, cache_path)
            logger.info("Fetched & cached EIA: %d rows", len(df_raw))

        # Build runtime frames
        fuel_df = load_fuel_list()
        fuel_list = fuel_df["Commodity"].tolist()
        cost_df = build_cost_frame(df_raw, cfg)

        # Dimensions: Commodity and Technology
        tech_list = build_comm_and_tech(conn, fuel_df=fuel_df, fuel_list=fuel_list, cfg=cfg)
        logger.info("Wrote Commodity and Technology (%d techs)", len(tech_list))

        # Efficiency (unit) and LifetimeTech
        mapping = build_mapping(tech_list)
        add_efficiency(conn, tech_list=tech_list, mapping=mapping, cfg=cfg)
        logger.info("Wrote Efficiency and LifetimeTech")

        # CostVariable
        build_costvariable(conn, cost_df=cost_df, tech_list=tech_list, mapping=mapping, fuel_df=fuel_df, cfg=cfg)
        logger.info("Wrote CostVariable")

        # EmissionActivity
        build_emission_activity(conn, mapping=mapping, cfg=cfg)
        logger.info("Wrote EmissionActivity")

        # Metadata: DataSet, DataSource, SectorLabel
        add_metadata(conn, cfg=cfg)
        logger.info("Wrote DataSet, DataSource, SectorLabel")

    logger.info("Done. SQLite: %s", cfg.db_dir)


if __name__ == "__main__":
    run()
