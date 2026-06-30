"""Build and persist Efficiency and LifetimeTech rows."""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from canoe_schema.v4_0.models import Efficiency, LifetimeTech

if TYPE_CHECKING:
    from common import CANOEFuelConfig

# All fuel-sector technologies are pure pass-throughs with unit efficiency.
_EFFICIENCY_VALUE = 1.0
_EFFICIENCY_NOTES = "Arbitrary value for transfer technology"

# Short lifetime ensures technologies are always available for reinvestment each period.
_LIFETIME_YEARS = 5.0
_LIFETIME_NOTES = "Arbitrary short lifetime so technology renews each period as needed"


def build_mapping(tech_list: list[str]) -> dict[str, dict[str, str]]:
    """Map each technology code to its input and output commodity codes.

    Derived entirely from the naming convention:
      F_IMP_<FUEL>  → F_ethos → F_<fuel>
      F_<SECTOR>_<FUEL> → F_<fuel> → <SECTOR>_<fuel>
      E_<SECTOR>_ELC → E_elc_dem → <SECTOR>_elc
    """
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
    cfg: "CANOEFuelConfig",
    mapping: dict[str, dict[str, str]],
) -> None:
    """Write Efficiency and LifetimeTech rows for every (province, period, tech)."""
    provinces = [p for p in cfg.province_list if p != "CAN"]

    eff_rows: list[Efficiency] = []
    for pro in provinces:
        data_id = cfg.data_id(pro)
        for vintage in cfg.future_periods:
            for tech in tech_list:
                io = mapping.get(tech, {})
                eff_rows.append(Efficiency(
                    region=pro,
                    input_comm=io.get("input", ""),
                    tech=tech,
                    vintage=vintage,
                    output_comm=io.get("output", ""),
                    efficiency=_EFFICIENCY_VALUE,
                    notes=_EFFICIENCY_NOTES,
                    data_id=data_id,
                ))

    life_rows: list[LifetimeTech] = []
    for pro in provinces:
        data_id = cfg.data_id(pro)
        for tech in tech_list:
            life_rows.append(LifetimeTech(
                region=pro,
                tech=tech,
                lifetime=_LIFETIME_YEARS,
                units="years",
                notes=_LIFETIME_NOTES,
                data_id=data_id,
            ))

    cur = conn.cursor()
    if eff_rows:
        cur.executemany(*Efficiency.bulk_insert_or_ignore_sql(eff_rows))
    if life_rows:
        cur.executemany(*LifetimeTech.bulk_insert_or_ignore_sql(life_rows))
    conn.commit()
