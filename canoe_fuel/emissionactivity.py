"""Create EmissionActivity rows from upstream and direct combustion CSVs."""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pandas as pd

from canoe_schema.v4_0.models import EmissionActivity

if TYPE_CHECKING:
    from canoe_fuel.common import CANOEFuelConfig


def build_emission_activity(
    conn: sqlite3.Connection,
    *,
    mapping: dict[str, dict[str, str]],
    cfg: "CANOEFuelConfig",
    upstream_csv: str = "input/upstream_emissions_fuels.csv",
    direct_csv: str = "input/direct_comb_emission.csv",
) -> None:
    """Write EmissionActivity rows for all regions and periods."""
    cur = conn.cursor()

    upstream = pd.read_csv(upstream_csv)
    direct = pd.read_csv(direct_csv)
    emis_df = pd.concat([upstream, direct]).reset_index(drop=True)

    rows: list[EmissionActivity] = []
    seen: set[tuple] = set()

    for pro in cfg.province_list:
        if pro == "CAN":
            continue
        data_id = cfg.data_id(pro)

        for _, r in emis_df.iterrows():
            em = r["emission"]
            out = r["commodity"]
            val = r["value"]
            units = r["units"]
            notes = r["notes"] if not pd.isna(r["notes"]) else None
            data_source = r["source"] if not pd.isna(r["source"]) else None

            for tech, tv in mapping.items():
                if tv.get("output") != out:
                    continue
                inp = tv.get("input", "")
                for per in cfg.future_periods:
                    key = (pro, em, inp, tech, per, out, data_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(
                        EmissionActivity(
                            region=pro,
                            emis_comm=em,
                            input_comm=inp,
                            tech=tech,
                            vintage=per,
                            output_comm=out,
                            activity=float(val),
                            units=units,
                            notes=notes,
                            data_source=data_source,
                            dq_cred=1,
                            dq_geog=2,
                            dq_struc=2,
                            dq_tech=2,
                            dq_time=2,
                            data_id=data_id,
                        )
                    )

    if rows:
        cur.executemany(*EmissionActivity.bulk_insert_or_ignore_sql(rows, include_nulls=True))
    conn.commit()
