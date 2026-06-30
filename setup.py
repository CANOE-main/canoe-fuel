"""Runtime frame construction for the fuel pipeline.

Transforms raw EIA data and static CSVs into the typed DataFrames that the
rest of the pipeline consumes.  No SQL, no schema imports, no DB interaction.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from common import CANOEFuelConfig

logger = logging.getLogger(__name__)


def load_fuel_list(path: str | Path = "input/fuel_list.csv") -> pd.DataFrame:
    """Return the commodity/fuel mapping table from CSV.

    Columns: Commodity, Fuel_type, Fuel_name, fuel_price_label, notes, source
    """
    return pd.read_csv(path)


def build_cost_frame(df_raw: pd.DataFrame, cfg: "CANOEFuelConfig") -> pd.DataFrame:
    """Filter and reshape the raw EIA DataFrame into a cost lookup table.

    Parameters
    ----------
    df_raw:
        Raw EIA AEO table 3 DataFrame (from eia_api.load_cached / fetch_and_cache).
    cfg:
        Module config supplying period list and EIA filter parameters.

    Returns
    -------
    DataFrame with columns: period, sector_code, fuel_code, Tech Name, value, unit.
    'Tech Name' uses the {sector_code}_{fuel_code} convention that costvariable.py
    uses to look up prices (e.g. 'I_ng', 'T_dsl').
    """
    df = df_raw.copy()
    df = df[df["unit"] == cfg.eia_unit_filter]
    periods = list(map(str, cfg.future_periods))
    df = df[df["period"].isin(periods)]
    df = df[~df["seriesName"].str.contains(cfg.eia_exclude_pattern, case=False)]

    sector_mapping = {
        "Commercial": "C",
        "Industrial": "I",
        "Electric Power": "E",
        "Residential": "R",
        "Transportation": "T",
    }
    fuel_mapping = {
        "Natural Gas": "ng",
        "Distillate Fuel Oil": "dsl",
        "Diesel Fuel": "dsl",
        "Residual Fuel Oil": "hfo",
        "Propane": "prop",
        "Jet Fuel": "jtf",
        "Residual Fuel": "oil",
        "Hydrogen": "h2",
        "Metallurgical Coal": "coal",
        "Motor Gasoline": "gsl",
    }

    split_data = df["seriesName"].str.split(" : ", expand=True)
    df["sector_code"] = split_data[1].map(sector_mapping)
    df["fuel_code"] = split_data[2].map(fuel_mapping)

    # HFO becomes OIL for C/R/E sectors; E_hfo tech name also normalised
    df["fuel_code"] = df.apply(
        lambda row: "oil"
        if row["fuel_code"] == "hfo" and row["sector_code"] in ["C", "R", "E"]
        else row["fuel_code"],
        axis=1,
    )
    df["Tech Name"] = (df["sector_code"] + "_" + df["fuel_code"]).replace({"E_hfo": "E_oil"})

    df = df.dropna()
    cost_df = df[["period", "sector_code", "fuel_code", "Tech Name", "value", "unit"]].copy()
    cost_df["period"] = cost_df["period"].astype(int)
    return cost_df.sort_values("period", ascending=True).reset_index(drop=True)
