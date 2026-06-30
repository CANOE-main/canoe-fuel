"""Build and persist Commodity and Technology rows (+ registry labels)."""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pandas as pd

from canoe_schema.v4_0.models import (
    Commodity,
    CommodityLabel,
    Technology,
    TechnologyLabel,
)
from canoe_schema.v4_0.enums import CommodityTypeCode, TechnologyTypeCode

if TYPE_CHECKING:
    from common import CANOEFuelConfig


_SECTORS = {
    "E": "Electric power sector",
    "R": "Residential sector",
    "C": "Commercial sector",
    "I": "Industrial sector",
    "T": "Transportation sector",
    "A": "Agriculture sector",
    "F": "Fuel production sector",
}

_EMISSION_COMMODITIES = {
    "co2": (CommodityTypeCode.E, "Carbon dioxide emissions"),
    "ch4": (CommodityTypeCode.E, "Methane emissions"),
    "n2o": (CommodityTypeCode.E, "Nitrous oxide emissions"),
    "co2e": (CommodityTypeCode.E, "Carbon dioxide equivalent emissions"),
}


def _fuel_description(code: str, fuels: dict[str, str]) -> str:
    parts = code.split("_")
    sector = _SECTORS.get(parts[0], "Unknown sector")
    key = "_".join(parts[1:]) if len(parts) > 1 else parts[0]
    if key.upper() == "ELC_DEM":
        fuel = "electricity (direct use)"
    elif key.upper() == "ELC":
        fuel = "electricity"
    else:
        fuel = fuels.get(key, key)
    return f"{fuel.capitalize()} for the {sector.lower()}"


def _tech_description(code: str, fuels: dict[str, str]) -> str:
    parts = code.split("_")
    if parts[0] == "F" and len(parts) > 1 and parts[1] == "IMP":
        fuel_key = "_".join(parts[2:]).lower()
        return f"{fuels.get(fuel_key, fuel_key).capitalize()} import into fuel sector"
    if parts[0] == "F" and len(parts) > 2:
        to_sector = _SECTORS.get(parts[1], parts[1])
        fuel_key = "_".join(parts[2:]).lower()
        return f"{fuels.get(fuel_key, fuel_key).capitalize()} distribution from fuel sector to {to_sector.lower()}"
    if parts[0] == "E" and len(parts) > 2:
        to_sector = _SECTORS.get(parts[1], parts[1])
        fuel_key = "_".join(parts[2:]).lower()
        return f"{fuels.get(fuel_key, fuel_key).capitalize()} distribution to {to_sector.lower()}"
    return f"Fuel flow for {code}"


def _commodity_flag(code: str) -> CommodityTypeCode:
    if code == "F_ethos":
        return CommodityTypeCode.S
    if "elc" in code.lower():
        return CommodityTypeCode.P
    return CommodityTypeCode.A


def build_tech_list(fuel_list: list[str], fuels: dict[str, str]) -> list[str]:
    """Derive the technology code list from the commodity list."""
    skip = {"e_elc_dem", "e_elc", "f_ethos"}
    tech_list: list[str] = []
    for code in fuel_list:
        if code.lower() in skip:
            continue
        parts = code.lower().split("_")
        prefix = parts[0].upper()
        fuel_part = "_".join(parts[1:]).upper() if len(parts) > 1 else parts[0].upper()
        if fuel_part.startswith("ELC") and prefix != "E":
            tech_code = f"E_{prefix}_{fuel_part}"
        elif prefix == "F":
            tech_code = f"F_IMP_{fuel_part}"
        else:
            tech_code = f"F_{prefix}_{fuel_part}"
        tech_list.append(tech_code)
    return tech_list


def build_comm_and_tech(
    conn: sqlite3.Connection,
    *,
    fuel_df: pd.DataFrame,
    fuel_list: list[str],
    cfg: "CANOEFuelConfig",
) -> list[str]:
    """Write Commodity, CommodityLabel, Technology, TechnologyLabel rows; return tech list.

    Uses INSERT OR IGNORE throughout so re-runs are idempotent.
    """
    can_data_id = cfg.data_id("CAN")
    fuels: dict[str, str] = fuel_df.set_index("Fuel_type")["Fuel_name"].to_dict()

    # --- Commodity rows ---
    used_fuel_keys: set[str] = set()
    comm_rows: list[Commodity] = []

    for code in fuel_list:
        comm_rows.append(Commodity(
            name=code,
            flag=_commodity_flag(code),
            description=_fuel_description(code, fuels),
            data_id=can_data_id,
        ))
        parts = code.split("_")
        key = "_".join(parts[1:]) if len(parts) > 1 else parts[0]
        if key.upper() not in {"ELC", "ELC_DEM"} and key in fuels:
            used_fuel_keys.add(key)

    # F_<fuel> physical commodities that serve as the fuel-sector internal carriers
    for fuel_key in sorted(used_fuel_keys):
        comm_rows.append(Commodity(
            name=f"F_{fuel_key}",
            flag=CommodityTypeCode.P,
            description=f"{fuels[fuel_key].capitalize()} for Fuel sector",
            data_id=can_data_id,
        ))

    # Emission commodities (INSERT OR IGNORE — canoe-base should eventually own these)
    for name, (flag, desc) in _EMISSION_COMMODITIES.items():
        comm_rows.append(Commodity(name=name, flag=flag, description=desc, data_id=can_data_id))

    cur = conn.cursor()
    cur.executemany(*Commodity.bulk_insert_or_ignore_sql(comm_rows))

    # Registry labels for all commodities
    label_rows = [CommodityLabel(commodity=r.name) for r in comm_rows]
    cur.executemany(*CommodityLabel.bulk_insert_or_ignore_sql(label_rows))

    # --- Technology rows ---
    tech_list = build_tech_list(fuel_list, fuels)
    tech_rows: list[Technology] = []
    for code in tech_list:
        parts = code.split("_")
        if parts[0] == "E":
            sector = "electricity"
            is_import = False
        elif parts[1] == "IMP":
            sector = "fuel"
            is_import = True
        else:
            sector_key = parts[1]
            sector = _SECTORS.get(sector_key, sector_key).split()[0].lower()
            is_import = False

        tech_rows.append(Technology(
            tech=code,
            flag=TechnologyTypeCode.P,
            sector=sector,
            unlim_cap=1,
            annual=1,
            description=_tech_description(code, fuels),
            data_id=can_data_id,
        ))

    cur.executemany(*Technology.bulk_insert_or_ignore_sql(tech_rows))

    # Registry labels for all technologies
    tech_label_rows = [TechnologyLabel(tech=r.tech) for r in tech_rows]
    cur.executemany(*TechnologyLabel.bulk_insert_or_ignore_sql(tech_label_rows))

    conn.commit()
    return tech_list
