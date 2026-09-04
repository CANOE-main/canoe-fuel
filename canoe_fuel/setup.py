"""Runtime frame construction for the fuel pipeline.

Transforms raw EIA data and static CSVs into the typed DataFrames that the
rest of the pipeline consumes.  No SQL, no schema imports, no DB interaction.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from canoe_fuel.common import BlanketFuelFilter

if TYPE_CHECKING:
    from canoe_fuel.common import CANOEFuelConfig

logger = logging.getLogger(__name__)


def load_fuel_list(
    path: str | Path = "input/fuel_list.csv", *, cfg: "CANOEFuelConfig | None" = None
) -> pd.DataFrame:
    """Return the commodity/fuel mapping table from CSV.

    Columns: Commodity, Fuel_type, Fuel_name, fuel_price_label, notes, source

    If `cfg` is given and sets `include_fuels` or `exclude_fuels`, the table is
    filtered accordingly (see `filter_fuel_list`).
    """
    df = pd.read_csv(path)
    if cfg is not None:
        df = filter_fuel_list(df, cfg)
    return df


def filter_fuel_list(df: pd.DataFrame, cfg: "CANOEFuelConfig") -> pd.DataFrame:
    """Restrict the fuel list to drop `cfg.exclude_fuels`.

    Codes are matched against the 'Commodity' column; unknown codes are treated as a
    configuration error since they most likely indicate a typo.
    """
    known = set(df["Commodity"])
    exclude_commodities = [f.get_commodity() for f in cfg.exclude_fuels if isinstance(f, BlanketFuelFilter)] if cfg.exclude_fuels is not None else []
    if cfg.exclude_fuels is not None:
        unknown = set(exclude_commodities) - known
        if unknown:
            raise ValueError(f"exclude_fuels contains unknown Commodity codes: {sorted(unknown)}")
        return df[~df["Commodity"].isin(exclude_commodities)].reset_index(drop=True)
    return df


def build_cost_frame(df_raw: pd.DataFrame, cfg: "CANOEFuelConfig") -> pd.DataFrame:
    """Filter and reshape the raw EIA DataFrame into a cost lookup table.

    Period-end perspective: each model period (e.g. 2025) uses EIA price data
    from the *following* period (e.g. 2030), stored in cost_df.attrs['period_end_map'].
    This map is read by build_costvariable to perform the correct price lookup.

    Returns a DataFrame with columns: period, sector_code, fuel_code, Tech Name, value, unit.
    'period' contains the EIA years (end-of-period), not the model periods.
    'Tech Name' uses the {sector_code}_{fuel_code} convention (e.g. 'I_ng', 'T_dsl').
    """
    df = df_raw.copy()
    df = df[df["unit"] == cfg.eia_unit_filter]

    sorted_periods = sorted(cfg.future_periods)
    period_step = sorted_periods[1] - sorted_periods[0] if len(sorted_periods) > 1 else 5
    end_periods = list(map(str, [p + period_step for p in sorted_periods]))
    df = df[df["period"].isin(end_periods)]
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
    cost_df = cost_df.sort_values("period", ascending=True).reset_index(drop=True)

    # Store mapping so downstream consumers can translate model period → EIA year
    cost_df.attrs["period_end_map"] = {p: p + period_step for p in sorted_periods}

    return cost_df
