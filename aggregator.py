"""End-to-end orchestrator for the canoe-fuel pipeline."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from common import CANOEFuelConfig
from validation import validate_db_against_config
from eia_api import load_cached, fetch_and_cache
from setup import build_cost_frame, load_fuel_list
from techcom import build_comm_and_tech
from efficiency import build_mapping, add_efficiency
from costvariable import build_costvariable
from emissionactivity import build_emission_activity
from postprocessing import add_metadata

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_CACHE_PATH = Path("cache/dataframes.pkl")


def run() -> None:
    # 0. Config + pre-flight validation
    cfg = CANOEFuelConfig.validate_from_yaml()
    with sqlite3.connect(cfg.db_dir) as conn:
        validate_db_against_config(cfg, conn)

        # 1. Acquire raw EIA prices
        try:
            df_raw = load_cached(_CACHE_PATH)
            logger.info("Loaded EIA cache: %d rows", len(df_raw))
        except FileNotFoundError:
            api_key = ""  # set via environment variable or config if needed
            df_raw = fetch_and_cache(cfg.eia_year, api_key, _CACHE_PATH)
            logger.info("Fetched & cached EIA: %d rows", len(df_raw))

        # 2. Transform raw data into typed lookup frames
        cost_df = build_cost_frame(df_raw, cfg)
        fuel_df = load_fuel_list()
        fuel_list = fuel_df["Commodity"].tolist()

        # 3. Commodity + Technology dimensions
        tech_list = build_comm_and_tech(
            conn,
            fuel_df=fuel_df,
            fuel_list=fuel_list,
            cfg=cfg,
        )
        logger.info("Wrote %d technologies", len(tech_list))

        # 4. Efficiency + LifetimeTech
        mapping = build_mapping(tech_list)
        add_efficiency(conn, tech_list=tech_list, cfg=cfg, mapping=mapping)
        logger.info("Wrote Efficiency + LifetimeTech")

        # 5. Variable costs
        build_costvariable(
            conn,
            cost_df=cost_df,
            tech_list=tech_list,
            mapping=mapping,
            fuel_df=fuel_df.rename(columns={"Fuel_type": "Commodity", "Fuel_name": "notes"}).assign(source="[F1]"),
            cfg=cfg,
        )
        logger.info("Wrote CostVariable")

        # 6. Emission activity
        build_emission_activity(conn, tech_list=tech_list, mapping=mapping, cfg=cfg)
        logger.info("Wrote EmissionActivity")

        # 7. Metadata (DataSet, DataSource, SectorLabel)
        add_metadata(conn, cfg=cfg)
        logger.info("Wrote metadata tables")

    logger.info("Done. DB: %s", cfg.db_dir)


if __name__ == "__main__":
    run()
