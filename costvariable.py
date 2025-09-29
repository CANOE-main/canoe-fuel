# -*- coding: utf-8 -*-
"""
costvariable.py

Builds the CostVariable table for CANOE.
"""
from typing import Dict, List
import pandas as pd


# ------------------------------
# Internal helpers
# ------------------------------
def _safe_base_from_cost(cost_df: pd.DataFrame, period_val: int, tech_name: str, *, warn_label: str) -> float:
    """Safely pull a base price from cost_df for (period, Tech Name).
    Prints a lightweight warning if the lookup fails.
    """
    sel = cost_df.loc[
        (cost_df['period'] == int(period_val)) & (cost_df['Tech Name'] == str(tech_name)),
        'value'
    ]
    if sel.empty:
        print(f"[CostVariable] WARNING: No base price for '{tech_name}' in period {period_val} "
              f"(needed by {warn_label}). Returning 0.")
        return 0.0
    # squeeze can be deprecated; use iloc[0] for single match
    return float(sel.iloc[0])


def _calc_value(
    tech: str,
    tech_name: str,
    period_val: int,
    *,
    cost_df: pd.DataFrame,
    cfg: dict,
    mmbtuconvertor: float,
    currencyadjustment: float,
    defl22: float,
    defl25: float,
    eth_price: float,
    rdsl_price: float,
    spk_price: float,
) -> float:
    """
    Compute a price in model units (2020 M$/PJ) for a given tech & period.
    This function centralizes all proxying and special-case logic.
    """

    tname_lower = tech_name.lower()

    # --- Config-based fuels ---
    # Biomass / Wood from config['b_price']
    if ('bio' in tname_lower) or ('wood' in tname_lower):
        # Using 2022 deflator path (as in prior pipeline)
        return ((cfg['b_price'] * mmbtuconvertor) * currencyadjustment) * defl22

    # Uranium from config['u_price']
    if ('u_nat' in tname_lower) or ('u_enr' in tname_lower):
        return ((cfg['u_price'] * mmbtuconvertor) * currencyadjustment) * defl22

    # --- Fixed external prices (already in model units) ---
    if 'eth' in tname_lower:
        return float(eth_price)
    if 'rdsl' in tname_lower:
        return float(rdsl_price)
    if 'spk' in tname_lower:
        return float(spk_price)

    # --- Derived fuels (CNG/LNG/NGL/LPG etc.) ---
    # Legacy behavior kept intact; only minor guard-rails added.
    if any(x in tname_lower for x in ['lng', 'cng', 'ngl']):
        # For LNG/CNG we proxy to transport NG; for NGL fall back to I_prop
        proxy = 'T_ng' if any(x in tname_lower for x in ['lng', 'cng']) else 'I_prop'
        base = _safe_base_from_cost(cost_df, period_val, proxy, warn_label=f"{tech_name} (lng/cng/ngl proxy)")
        return ((base * mmbtuconvertor) * currencyadjustment) * defl25 * 0.89

    if 'lpg' in tname_lower:
        # Residential LPG uses R_prop, otherwise T_prop
        proxy = 'R_prop' if tname_lower == 'f_r_lpg' else 'T_prop'
        base = _safe_base_from_cost(cost_df, period_val, proxy, warn_label=f"{tech_name} (lpg proxy)")
        return ((base * mmbtuconvertor) * currencyadjustment) * defl25

    # --- Electricity-side proxies (coal/gasoline/res oil/h2/coke) ---
    if 'e_coal' in tname_lower:
        base = _safe_base_from_cost(cost_df, period_val, 'I_coal', warn_label=f"{tech_name} (E_coal→I_coal)")
        return ((base * mmbtuconvertor) * currencyadjustment) * defl25

    if 'e_gsl' in tname_lower:
        base = _safe_base_from_cost(cost_df, period_val, 'T_gsl', warn_label=f"{tech_name} (E_gsl→T_gsl)")
        return ((base * mmbtuconvertor) * currencyadjustment) * defl25

    if 'r_oil' in tname_lower:
        base = _safe_base_from_cost(cost_df, period_val, 'C_oil', warn_label=f"{tech_name} (R_oil→C_oil)")
        return ((base * mmbtuconvertor) * currencyadjustment) * defl25

    if ('c_h2' in tname_lower) or ('r_h2' in tname_lower):
        base = _safe_base_from_cost(cost_df, period_val, 'I_h2', warn_label=f"{tech_name} (H2→I_h2)")
        return ((base * mmbtuconvertor) * currencyadjustment) * defl25

    if ('i_pcoke' in tname_lower) or ('i_coke' in tname_lower):
        base = _safe_base_from_cost(cost_df, period_val, 'I_coal', warn_label=f"{tech_name} (coke→I_coal)")
        return ((base * mmbtuconvertor) * currencyadjustment) * defl25

    # --- Agriculture proxies (NG/DSL/PROP + new GSL) ---
    if 'a_gsl' in tname_lower:
        # New: Agriculture gasoline -> transport gasoline
        base = _safe_base_from_cost(cost_df, period_val, 'T_gsl', warn_label=f"{tech_name} (A_gsl→T_gsl)")
        return ((base * mmbtuconvertor) * currencyadjustment) * defl25

    if 'a_ng' in tname_lower:
        base = _safe_base_from_cost(cost_df, period_val, 'I_ng', warn_label=f"{tech_name} (A_ng→I_ng)")
        return ((base * mmbtuconvertor) * currencyadjustment) * defl25

    if 'a_dsl' in tname_lower:
        base = _safe_base_from_cost(cost_df, period_val, 'T_dsl', warn_label=f"{tech_name} (A_dsl→T_dsl)")
        return ((base * mmbtuconvertor) * currencyadjustment) * defl25

    if 'a_prop' in tname_lower:
        base = _safe_base_from_cost(cost_df, period_val, 'T_prop', warn_label=f"{tech_name} (A_prop→T_prop)")
        return ((base * mmbtuconvertor) * currencyadjustment) * defl25

    # --- NEW: Marine diesel oil (MDO) ---
    if 'mdo' in tname_lower:
        # MDO is priced as 0.9 × transport diesel
        base = _safe_base_from_cost(cost_df, period_val, 'T_dsl', warn_label=f"{tech_name} (MDO→0.9*T_dsl)")
        return ((base * mmbtuconvertor) * currencyadjustment) * defl25 * 0.9

    # --- Default: direct lookup from cost_df ---
    base = _safe_base_from_cost(cost_df, period_val, tech_name, warn_label=f"{tech_name} (direct)")
    return ((base * mmbtuconvertor) * currencyadjustment) * defl25


# ------------------------------
# Public API
# ------------------------------
def build_costvariable(
    comb_dict: Dict[str, pd.DataFrame],
    *,
    cost_df: pd.DataFrame,
    tech_list: List[str],
    mapping: Dict[str, Dict[str, str]],
    province_list: List[str],
    periods: List[int],
    dict_id: Dict[str, str],
    factors: dict,
    fuel_df: pd.DataFrame,
    cfg: dict,
) -> Dict[str, pd.DataFrame]:
    """
    Append cost rows to comb_dict['CostVariable'] for each province, tech, vintage, and period.

    The output schema appended is expected to match the existing CostVariable table:
        [region, period, tech, vintage, value, unit, notes, source,
         dq_cred, dq_geo, dq_str, dq_tech, dq_time, data_id]
    """
    # Normalize types for cost_df
    cdf = cost_df.copy()
    cdf['period'] = cdf['period'].astype(int)
    cdf['Tech Name'] = cdf['Tech Name'].astype(str)
    cdf['value'] = cdf['value'].astype(float)

    # Ensure required metadata columns exist on fuel_df
    fuel_df = fuel_df.loc[:, ~fuel_df.columns.duplicated()].copy()
    for col in ('Commodity', 'notes', 'source'):
        if col not in fuel_df.columns:
            fuel_df[col] = ""

    rows = []
    for pro in province_list:
        if pro == 'CAN':
            continue

        for vint in periods:
            for per in periods:
                if per < vint:
                    continue

                for tech in tech_list:
                    # Skip imports/ELC/OTH if those are not meant to be priced here
                    if any(x in tech for x in ['F_IMP', 'ELC', 'OTH']):
                        continue

                    # Map to the "Tech Name" used in cost_df
                    tech_name = mapping[tech]['output'].strip()

                    # Compute value with all conversions/deflators applied
                    val = _calc_value(
                        tech,
                        tech_name,
                        int(per),
                        cost_df=cdf,
                        cfg=cfg,
                        mmbtuconvertor=factors['mmbtuconvertor'],
                        currencyadjustment=factors['currencyadjustment'],
                        defl22=factors['deflation_2022'],
                        defl25=factors['deflation_2025'],
                        eth_price=factors['eth_price'],
                        rdsl_price=factors['rdsl_price'],
                        spk_price=factors['spk_price'],
                    )

                    unit = "2020 M$/PJ"

                    # Attach notes/source from fuel_df where available
                    match = fuel_df.loc[fuel_df['Commodity'] == tech_name]
                    if not match.empty:
                        # guard for non-standard shapes
                        notes = match['notes'].iloc[0] if 'notes' in match else ''
                        ref = match['source'].iloc[0] if 'source' in match else ''
                    else:
                        notes, ref = '', ''

                    # Data Quality default scores (tunable)
                    dq_cred, dq_geo, dq_str, dq_tech, dq_time = 2, 3, 2, 1, 1

                    rows.append([
                        pro, int(per), tech, int(vint), float(val), unit,
                        notes, ref, dq_cred, dq_geo, dq_str, dq_tech, dq_time,
                        dict_id[pro],
                    ])

    if rows:
        new_df = pd.DataFrame(
            rows,
            columns=comb_dict['CostVariable'].columns
        )
        comb_dict['CostVariable'] = pd.concat(
            [comb_dict['CostVariable'], new_df],
            ignore_index=True
        )

    return comb_dict
