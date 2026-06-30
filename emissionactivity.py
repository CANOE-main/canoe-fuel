"""Build and persist EmissionActivity rows from upstream and direct-combustion CSVs."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from canoe_schema.v4_0.models import EmissionActivity
from canoe_schema.v4_0.enums import (
    DataQualityCredibilityLevel,
    DataQualityGeographyLevel,
    DataQualityStructureLevel,
    DataQualityTechnologyLevel,
    DataQualityTimeLevel,
)

if TYPE_CHECKING:
    from common import CANOEFuelConfig

# Data quality scores for emission factor data.
# Credibility=1 (Excellent): factors from authoritative government/IPCC sources.
# Geography=2 (Good): Canadian/North American emission factors used where available.
# Structure=2 (Good): per-fuel, per-sector differentiation matches model structure.
# Technology=2 (Good): factors tied to specific fuel types, not technology processes.
# Time=2 (Good): static factors without time projection (reasonable for GHG accounting).
_DQ_EMIS = (
    DataQualityCredibilityLevel.EXCELLENT,
    DataQualityGeographyLevel.GOOD,
    DataQualityStructureLevel.GOOD,
    DataQualityTechnologyLevel.GOOD,
    DataQualityTimeLevel.GOOD,
)


def load_emission_factors(
    upstream_csv: str | Path = "input/upstream_emissions_fuels.csv",
    direct_csv: str | Path = "input/direct_comb_emission.csv",
) -> pd.DataFrame:
    """Load and combine upstream and direct-combustion emission factor CSVs.

    Returns DataFrame with columns: commodity, emission, value, units, notes, source.
    """
    upstream = pd.read_csv(upstream_csv)
    direct = pd.read_csv(direct_csv)
    return pd.concat([upstream, direct], ignore_index=True)


def build_emission_activity(
    conn: sqlite3.Connection,
    *,
    tech_list: list[str],
    mapping: dict[str, dict[str, str]],
    cfg: "CANOEFuelConfig",
    upstream_csv: str | Path = "input/upstream_emissions_fuels.csv",
    direct_csv: str | Path = "input/direct_comb_emission.csv",
) -> None:
    """Write EmissionActivity rows for each (province, emission species, tech, period)."""
    emis_df = load_emission_factors(upstream_csv, direct_csv)

    # Build index: output_comm → list of (emission, value, units, notes, source)
    output_to_factors: dict[str, list[tuple]] = {}
    for _, r in emis_df.iterrows():
        out = str(r["commodity"])
        output_to_factors.setdefault(out, []).append((
            str(r["emission"]),
            float(r["value"]),
            str(r["units"]) if pd.notna(r.get("units")) else None,
            str(r["notes"]) if pd.notna(r.get("notes")) else None,
            str(r["source"]) if pd.notna(r.get("source")) else None,
        ))

    provinces = [p for p in cfg.province_list if p != "CAN"]
    seen: set[tuple] = set()
    rows: list[EmissionActivity] = []

    for pro in provinces:
        data_id = cfg.data_id(pro)
        for tech in tech_list:
            io = mapping.get(tech, {})
            inp = io.get("input", "")
            out = io.get("output", "")
            factors = output_to_factors.get(out, [])
            for emis, val, units, notes, source in factors:
                for period in cfg.future_periods:
                    key = (pro, emis, inp, tech, period, out, data_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(EmissionActivity(
                        region=pro,
                        emis_comm=emis,
                        input_comm=inp,
                        tech=tech,
                        vintage=int(period),
                        output_comm=out,
                        activity=val,
                        units=units,
                        notes=notes,
                        data_source=source,
                        dq_cred=_DQ_EMIS[0],
                        dq_geog=_DQ_EMIS[1],
                        dq_struc=_DQ_EMIS[2],
                        dq_tech=_DQ_EMIS[3],
                        dq_time=_DQ_EMIS[4],
                        data_id=data_id,
                    ))

    if rows:
        cur = conn.cursor()
        cur.executemany(*EmissionActivity.bulk_insert_or_ignore_sql(rows))
        conn.commit()
