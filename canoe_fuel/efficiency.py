"""Generate Efficiency and LifetimeTech rows from technology naming rules."""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from canoe_schema.v4_0.models import Efficiency, LifetimeTech

if TYPE_CHECKING:
    from canoe_fuel.common import CANOEFuelConfig


def build_mapping(tech_list: list[str]) -> dict[str, dict[str, str]]:
    """Map each tech code to its input and output commodity using naming conventions."""
    mapping: dict[str, dict[str, str]] = {}
    for tech in tech_list:
        parts = tech.split("_")
        if tech.startswith("F_IMP_"):
            fuel = "_".join(parts[2:]).lower()
            mapping[tech] = {"input": "F_ethos", "output": f"F_{fuel}"}
        elif tech.startswith("E_"):
            sector = parts[1].upper()
            mapping[tech] = {"input": "E_elc_dem", "output": f"{sector}_elc"}
        elif tech.startswith("F_"):
            sector = parts[1].upper()
            fuel = "_".join(parts[2:]).lower()
            mapping[tech] = {"input": f"F_{fuel}", "output": f"{sector}_{fuel}"}
    return mapping


def add_efficiency(
    conn: sqlite3.Connection,
    *,
    tech_list: list[str],
    mapping: dict[str, dict[str, str]],
    cfg: "CANOEFuelConfig",
) -> None:
    """Write Efficiency (value=1.0) and LifetimeTech rows for all techs/regions/periods."""
    cur = conn.cursor()

    eff_rows: list[Efficiency] = []
    for pro in cfg.province_list:
        if pro == "CAN":
            continue
        data_id = cfg.data_id(pro)
        for vint in cfg.future_periods:
            for tech in tech_list:
                inp = mapping.get(tech, {}).get("input", "")
                out = mapping.get(tech, {}).get("output", "")
                eff_rows.append(
                    Efficiency(
                        region=pro,
                        input_comm=inp,
                        tech=tech,
                        vintage=vint,
                        output_comm=out,
                        efficiency=1.0,
                        notes="Arbitrary value for transfer technology",
                        data_id=data_id,
                    )
                )

    if eff_rows:
        cur.executemany(*Efficiency.bulk_insert_or_ignore_sql(eff_rows, include_nulls=True))

    life_rows: list[LifetimeTech] = []
    for pro in cfg.province_list:
        if pro == "CAN":
            continue
        data_id = cfg.data_id(pro)
        for tech in tech_list:
            life_rows.append(
                LifetimeTech(
                    region=pro,
                    tech=tech,
                    lifetime=5,
                    notes="An arbitrary lifetime so that it is renewed as often as it is needed",
                    data_id=data_id,
                )
            )

    if life_rows:
        cur.executemany(*LifetimeTech.bulk_insert_or_ignore_sql(life_rows, include_nulls=True))

    conn.commit()
