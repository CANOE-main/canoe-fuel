"""Build and persist CostVariable rows."""
from __future__ import annotations

import ast
import logging
import sqlite3
from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from canoe_schema.v4_0.models import CostVariable
from canoe_schema.v4_0.enums import (
    DataQualityCredibilityLevel,
    DataQualityGeographyLevel,
    DataQualityStructureLevel,
    DataQualityTechnologyLevel,
    DataQualityTimeLevel,
)

if TYPE_CHECKING:
    from common import CANOEFuelConfig, InflationFactors

logger = logging.getLogger(__name__)

# Data quality scores for fuel price data.
# Credibility=2 (Good): prices from EIA/NREL official sources.
# Geography=3 (Acceptable): US data applied uniformly to Canadian provinces.
# Structure=2 (Good): sector-differentiated prices match model structure.
# Technology=1 (Excellent): fuel prices are well-defined per commodity.
# Time=1 (Excellent): time-series projections directly from EIA AEO.
_DQ_COST = (
    DataQualityCredibilityLevel.GOOD,
    DataQualityGeographyLevel.ACCEPTABLE,
    DataQualityStructureLevel.GOOD,
    DataQualityTechnologyLevel.EXCELLENT,
    DataQualityTimeLevel.EXCELLENT,
)


def _to_scalar(x):
    if pd.isna(x) if not isinstance(x, (list, tuple)) else False:
        return None
    if isinstance(x, str) and x.strip().startswith("[") and x.strip().endswith("]"):
        try:
            parsed = ast.literal_eval(x.strip())
            if isinstance(parsed, Sequence) and not isinstance(parsed, (str, bytes)):
                return parsed[0] if len(parsed) else None
        except Exception:
            s = x.strip()[1:-1].strip()
            return s.strip("'").strip('"') or None
    if isinstance(x, Sequence) and not isinstance(x, (str, bytes)):
        return x[0] if len(x) else None
    return x if not (isinstance(x, float) and np.isnan(x)) else None


def _safe_price(cost_df: pd.DataFrame, period: int, tech_name: str) -> float:
    sel = cost_df.loc[
        (cost_df["period"] == period) & (cost_df["Tech Name"] == tech_name),
        "value",
    ]
    if sel.empty:
        logger.warning("No EIA price for '%s' in period %d — using 0.", tech_name, period)
        return 0.0
    return float(sel.iloc[0])


def _calc_price(
    tech_name: str,
    period: int,
    *,
    cost_df: pd.DataFrame,
    cfg: "CANOEFuelConfig",
    inf: "InflationFactors",
) -> float:
    """Return price in 2020 M$/PJ for a given tech output commodity and period."""
    n = tech_name.lower()
    c = inf.currency_adjustment
    m = inf.mmbtu_convertor
    d22 = inf.deflation_2022
    d25 = inf.deflation_2025

    # Config-priced fuels (constant, no EIA projection)
    if "bio" in n or "wood" in n:
        return cfg.b_price * m * c * d22
    if "u_nat" in n or "u_enr" in n:
        return cfg.u_price * m * c * d22

    # Fixed Canadian biofuel prices (Wolinetz & Harrison 2023, no projection)
    if "eth" in n:
        return inf.eth_price
    if "rdsl" in n:
        return inf.rdsl_price
    if "spk" in n:
        return inf.spk_price

    # Derived fuels — proxy to nearest EIA series
    if any(x in n for x in ["lng", "cng"]):
        base = _safe_price(cost_df, period, "T_ng")
        return base * m * c * d25 * 0.89
    if "ngl" in n:
        base = _safe_price(cost_df, period, "I_prop")
        return base * m * c * d25 * 0.89
    if "lpg" in n:
        proxy = "R_prop" if n == "f_r_lpg" else "T_prop"
        return _safe_price(cost_df, period, proxy) * m * c * d25
    if "mdo" in n:
        return _safe_price(cost_df, period, "T_dsl") * m * c * d25 * 0.9

    # Electricity-sector proxies
    if "e_coal" in n:
        return _safe_price(cost_df, period, "I_coal") * m * c * d25
    if "e_gsl" in n:
        return _safe_price(cost_df, period, "T_gsl") * m * c * d25
    if "r_oil" in n:
        return _safe_price(cost_df, period, "C_oil") * m * c * d25
    if "c_h2" in n or "r_h2" in n:
        return _safe_price(cost_df, period, "I_h2") * m * c * d25
    if "i_pcoke" in n or "i_coke" in n:
        return _safe_price(cost_df, period, "I_coal") * m * c * d25

    # Agriculture proxies
    if "a_gsl" in n:
        return _safe_price(cost_df, period, "T_gsl") * m * c * d25
    if "a_ng" in n:
        return _safe_price(cost_df, period, "I_ng") * m * c * d25
    if "a_dsl" in n:
        return _safe_price(cost_df, period, "T_dsl") * m * c * d25
    if "a_prop" in n:
        return _safe_price(cost_df, period, "T_prop") * m * c * d25

    # Direct EIA lookup
    return _safe_price(cost_df, period, tech_name) * m * c * d25


def build_costvariable(
    conn: sqlite3.Connection,
    *,
    cost_df: pd.DataFrame,
    tech_list: list[str],
    mapping: dict[str, dict[str, str]],
    fuel_df: pd.DataFrame,
    cfg: "CANOEFuelConfig",
) -> None:
    """Write CostVariable rows for every (province, period, tech) combination."""
    inf = cfg.inflation
    cdf = cost_df.copy()
    cdf["period"] = cdf["period"].astype(int)

    # Notes/source lookup keyed by output commodity name
    notes_lookup: dict[str, tuple[str | None, str | None]] = {}
    for _, row in fuel_df.iterrows():
        notes_lookup[str(row["Commodity"])] = (
            _to_scalar(row.get("notes")),
            _to_scalar(row.get("source")),
        )

    provinces = [p for p in cfg.province_list if p != "CAN"]
    rows: list[CostVariable] = []

    for pro in provinces:
        data_id = cfg.data_id(pro)
        for vintage in cfg.future_periods:
            for tech in tech_list:
                # F_IMP, electricity, and catch-all 'other' have no variable fuel cost
                if any(x in tech for x in ["F_IMP", "ELC", "OTH"]):
                    continue

                tech_name = mapping[tech]["output"].strip()
                price = _calc_price(tech_name, int(vintage), cost_df=cdf, cfg=cfg, inf=inf)
                notes, source = notes_lookup.get(tech_name, (None, None))

                rows.append(CostVariable(
                    region=pro,
                    period=int(vintage),
                    tech=tech,
                    vintage=int(vintage),
                    cost=float(price),
                    units="2020 M$/PJ",
                    notes=notes,
                    data_source=source,
                    dq_cred=_DQ_COST[0],
                    dq_geog=_DQ_COST[1],
                    dq_struc=_DQ_COST[2],
                    dq_tech=_DQ_COST[3],
                    dq_time=_DQ_COST[4],
                    data_id=data_id,
                ))

    if rows:
        cur = conn.cursor()
        cur.executemany(*CostVariable.bulk_insert_or_ignore_sql(rows))
        conn.commit()
