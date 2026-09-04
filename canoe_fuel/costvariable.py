"""Build CostVariable rows for the fuel pipeline."""
from __future__ import annotations

import ast
import sqlite3
from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from canoe_schema.v4_0.models import CostVariable

if TYPE_CHECKING:
    from canoe_fuel.common import CANOEFuelConfig


def _to_scalar(x):
    """Collapse list-like or JSON-string cells to a plain scalar."""
    if pd.isna(x):
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
    return x


def _safe_base(cost_df: pd.DataFrame, period_val: int, tech_name: str, *, warn_label: str) -> float:
    sel = cost_df.loc[
        (cost_df["period"] == int(period_val)) & (cost_df["Tech Name"] == str(tech_name)),
        "value",
    ]
    if sel.empty:
        print(
            f"[CostVariable] WARNING: No base price for '{tech_name}' in period {period_val} "
            f"(needed by {warn_label}). Returning 0."
        )
        return 0.0
    return float(sel.iloc[0])


def _calc_cost(
    tech: str,
    tech_name: str,
    period_val: int,
    *,
    cost_df: pd.DataFrame,
    cfg: "CANOEFuelConfig",
) -> float:
    """Return price in model units (2020 M$/PJ) for a given tech and EIA period year."""
    inf = cfg.inflation
    tname = tech_name.lower()

    if ("bio" in tname) or ("wood" in tname):
        return ((cfg.b_price * inf.mmbtu_convertor) * inf.currency_adjustment) * inf.deflation_2022

    if ("u_nat" in tname) or ("u_enr" in tname):
        return ((cfg.u_price * inf.mmbtu_convertor) * inf.currency_adjustment) * inf.deflation_2022

    if "eth" in tname:
        return inf.eth_price
    if "rdsl" in tname:
        return inf.rdsl_price
    if "spk" in tname:
        return inf.spk_price

    if any(x in tname for x in ["lng", "cng", "ngl"]):
        proxy = "T_ng" if any(x in tname for x in ["lng", "cng"]) else "I_prop"
        base = _safe_base(cost_df, period_val, proxy, warn_label=f"{tech_name} (lng/cng/ngl proxy)")
        return ((base * inf.mmbtu_convertor) * inf.currency_adjustment) * inf.deflation_2025 * 0.89

    if "lpg" in tname:
        proxy = "R_prop" if tname == "f_r_lpg" else "T_prop"
        base = _safe_base(cost_df, period_val, proxy, warn_label=f"{tech_name} (lpg proxy)")
        return ((base * inf.mmbtu_convertor) * inf.currency_adjustment) * inf.deflation_2025

    if "e_coal" in tname:
        base = _safe_base(cost_df, period_val, "I_coal", warn_label=f"{tech_name} (E_coal→I_coal)")
        return ((base * inf.mmbtu_convertor) * inf.currency_adjustment) * inf.deflation_2025

    if "e_gsl" in tname:
        base = _safe_base(cost_df, period_val, "T_gsl", warn_label=f"{tech_name} (E_gsl→T_gsl)")
        return ((base * inf.mmbtu_convertor) * inf.currency_adjustment) * inf.deflation_2025

    if "r_oil" in tname:
        base = _safe_base(cost_df, period_val, "C_oil", warn_label=f"{tech_name} (R_oil→C_oil)")
        return ((base * inf.mmbtu_convertor) * inf.currency_adjustment) * inf.deflation_2025

    if ("c_h2" in tname) or ("r_h2" in tname):
        base = _safe_base(cost_df, period_val, "I_h2", warn_label=f"{tech_name} (H2→I_h2)")
        return ((base * inf.mmbtu_convertor) * inf.currency_adjustment) * inf.deflation_2025

    if ("i_pcoke" in tname) or ("i_coke" in tname):
        base = _safe_base(cost_df, period_val, "I_coal", warn_label=f"{tech_name} (coke→I_coal)")
        return ((base * inf.mmbtu_convertor) * inf.currency_adjustment) * inf.deflation_2025

    if "a_gsl" in tname:
        base = _safe_base(cost_df, period_val, "T_gsl", warn_label=f"{tech_name} (A_gsl→T_gsl)")
        return ((base * inf.mmbtu_convertor) * inf.currency_adjustment) * inf.deflation_2025

    if "a_ng" in tname:
        base = _safe_base(cost_df, period_val, "I_ng", warn_label=f"{tech_name} (A_ng→I_ng)")
        return ((base * inf.mmbtu_convertor) * inf.currency_adjustment) * inf.deflation_2025

    if "a_dsl" in tname:
        base = _safe_base(cost_df, period_val, "T_dsl", warn_label=f"{tech_name} (A_dsl→T_dsl)")
        return ((base * inf.mmbtu_convertor) * inf.currency_adjustment) * inf.deflation_2025

    if "a_prop" in tname:
        base = _safe_base(cost_df, period_val, "T_prop", warn_label=f"{tech_name} (A_prop→T_prop)")
        return ((base * inf.mmbtu_convertor) * inf.currency_adjustment) * inf.deflation_2025

    if "mdo" in tname:
        base = _safe_base(cost_df, period_val, "T_dsl", warn_label=f"{tech_name} (MDO→0.9*T_dsl)")
        return ((base * inf.mmbtu_convertor) * inf.currency_adjustment) * inf.deflation_2025 * 0.9

    base = _safe_base(cost_df, period_val, tech_name, warn_label=f"{tech_name} (direct)")
    return ((base * inf.mmbtu_convertor) * inf.currency_adjustment) * inf.deflation_2025


def build_costvariable(
    conn: sqlite3.Connection,
    *,
    cost_df: pd.DataFrame,
    tech_list: list[str],
    mapping: dict[str, dict[str, str]],
    fuel_df: pd.DataFrame,
    cfg: "CANOEFuelConfig",
) -> None:
    """Write CostVariable rows for all regions, techs, and periods."""
    cur = conn.cursor()

    cdf = cost_df.copy()
    cdf["period"] = cdf["period"].astype(int)
    cdf["Tech Name"] = cdf["Tech Name"].astype(str)
    cdf["value"] = cdf["value"].astype(float)

    # Period-end map: model_period → EIA year to use for pricing
    period_end_map: dict = cost_df.attrs.get("period_end_map", {})

    rows: list[CostVariable] = []
    for pro in cfg.province_list:
        if pro == "CAN":
            continue
        data_id = cfg.data_id(pro)

        for vint in cfg.future_periods:
            for tech in tech_list:
                if any(x in tech for x in ["F_IMP", "ELC", "OTH"]):
                    continue

                tech_name = mapping[tech]["output"].strip()
                price_year = period_end_map.get(int(vint), int(vint))
                cost = _calc_cost(tech, tech_name, price_year, cost_df=cdf, cfg=cfg)

                # Notes and source from fuel_df (matched by Commodity column)
                match = fuel_df.loc[fuel_df["Commodity"] == tech_name]
                if not match.empty:
                    notes = _to_scalar(match["notes"].iloc[0])
                    data_source = _to_scalar(match["source"].iloc[0])
                else:
                    notes = None
                    data_source = None

                rows.append(
                    CostVariable(
                        region=pro,
                        period=int(vint),
                        tech=tech,
                        vintage=int(vint),
                        cost=float(cost),
                        units="2020 M$/PJ",
                        notes=notes,
                        data_source=data_source,
                        dq_cred=2,
                        dq_geog=3,
                        dq_struc=2,
                        dq_tech=1,
                        dq_time=1,
                        data_id=data_id,
                    )
                )

    if rows:
        cur.executemany(*CostVariable.bulk_insert_or_ignore_sql(rows, include_nulls=True))
    conn.commit()
