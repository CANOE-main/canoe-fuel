"""Build Commodity and Technology tables from the fuel list."""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pandas as pd

from canoe_schema.v4_0.models import Commodity, Technology

if TYPE_CHECKING:
    from canoe_fuel.common import CANOEFuelConfig


def _sectors_map() -> dict[str, str]:
    return {
        "E": "Electric power sector",
        "R": "Residential sector",
        "C": "Commercial sector",
        "I": "Industrial sector",
        "T": "Transportation sector",
        "A": "Agriculture sector",
        "F": "Fuel production sector",
    }


def build_comm_and_tech(
    conn: sqlite3.Connection,
    *,
    fuel_df: pd.DataFrame,
    fuel_list: list[str],
    cfg: "CANOEFuelConfig",
) -> list[str]:
    """Write Commodity and Technology rows; return the tech code list."""
    cur = conn.cursor()
    sectors = _sectors_map()
    fuels = fuel_df.set_index("Fuel_type")["Fuel_name"].to_dict()
    can_data_id = cfg.data_id("CAN")

    def _comm_description(code: str) -> str:
        parts = code.split("_")
        prefix = parts[0]
        sector = sectors.get(prefix, "Unknown sector")
        key = "_".join(parts[1:]) if len(parts) > 1 else parts[0]
        if code in fuels:
            fuel = fuels[code]
        elif key.upper() == "ELC":
            fuel = "electricity"
        elif key.upper() == "ELC_DEM":
            fuel = "electricity (direct use)"
        else:
            fuel = fuels.get(key, key)
        return f"{fuel.capitalize()} for the {sector.lower()}"

    # --- Commodities from fuel_list ---
    comm_rows: list[Commodity] = []
    for code in fuel_list:
        if "elc" in code.lower():
            flag = "p"
        elif code == "F_ethos":
            flag = "s"
        else:
            flag = "a"
        comm_rows.append(Commodity(name=code, flag=flag, description=_comm_description(code), data_id=can_data_id))

    # --- Emission commodities (INSERT OR IGNORE — canoe-base is the long-term owner) ---
    emis_list = ["co2", "ch4", "n2o", "co2e"]
    emis_descriptions = {
        "co2": "Carbon dioxide emissions",
        "ch4": "Methane emissions",
        "n2o": "Nitrous oxide emissions",
        "co2e": "Carbon dioxide equivalent emissions",
    }
    for emis in emis_list:
        comm_rows.append(Commodity(name=emis, flag="e", description=emis_descriptions[emis], data_id=can_data_id))

    # --- Cross-sector F_<fuel> commodities ---
    used_fuels: set[str] = set()
    for code in fuel_list:
        parts = code.split("_")
        fuel_key = "_".join(parts[1:]) if len(parts) > 1 else parts[0]
        if fuel_key.upper() not in {"ELC", "ELC_DEM"} and fuel_key in fuels:
            used_fuels.add(fuel_key)
    for fuel_code in sorted(used_fuels):
        comm_rows.append(
            Commodity(
                name=f"F_{fuel_code}",
                flag="p",
                description=f"{fuels[fuel_code].capitalize()} for Fuel sector",
                data_id=can_data_id,
            )
        )

    cur.executemany(*Commodity.bulk_insert_or_ignore_sql(comm_rows))

    # --- Technologies (fuel flow links) ---
    all_comm_codes = [r.name for r in comm_rows]
    fuel_flow_list: list[str] = []
    for code in all_comm_codes:
        if code in emis_list:
            continue
        original = code.lower()
        if original in {"e_elc_dem", "e_elc", "f_ethos"}:
            continue
        parts = original.split("_")
        prefix = parts[0].upper()
        fuel_part = "_".join(parts[1:]).upper() if len(parts) > 1 else parts[0].upper()
        if fuel_part.startswith("ELC") and prefix != "E":
            tech_code = f"E_{prefix}_{fuel_part}"
        elif prefix == "F":
            tech_code = f"F_IMP_{fuel_part}"
        else:
            tech_code = f"F_{prefix}_{fuel_part}"
        fuel_flow_list.append(tech_code)

    def _tech_description(code: str) -> str:
        parts = code.split("_")
        if parts[0] == "F" and len(parts) > 1 and parts[1] == "IMP":
            fuel_key = "_".join(parts[2:]).lower()
            fuel_name = fuels.get(fuel_key, fuel_key)
            return f"{fuel_name.capitalize()} import into fuel sector"
        if parts[0] == "F" and len(parts) > 2:
            to_sector = parts[1]
            fuel_key = "_".join(parts[2:]).lower()
            to_sector_name = sectors.get(to_sector, to_sector)
            fuel_name = fuels.get(fuel_key, fuel_key)
            return f"{fuel_name.capitalize()} distribution from fuel sector to {to_sector_name.lower()}"
        if parts[0] == "E" and len(parts) > 2:
            to_sector = parts[1]
            fuel_key = "_".join(parts[2:]).lower()
            to_sector_name = sectors.get(to_sector, to_sector)
            fuel_name = fuels.get(fuel_key, fuel_key)
            return f"{fuel_name.capitalize()} distribution to {to_sector_name.lower()}"
        return f"Fuel flow for {code}"

    def _sector_for_tech(code: str) -> str:
        if code.startswith(("F_C_", "E_C_")):
            return "commercial"
        if code.startswith(("F_I_", "E_I_")):
            return "industrial"
        if code.startswith(("F_R_", "E_R_")):
            return "residential"
        if code.startswith(("F_A_", "E_A_")):
            return "agriculture"
        if code.startswith(("F_T_", "E_T_")):
            return "transportation"
        if code.startswith("F_E_"):
            return "electricity"
        return "fuel"

    tech_rows: list[Technology] = []
    for code in fuel_flow_list:
        is_elec_dist = code.startswith("E_")
        tech_rows.append(
            Technology(
                tech=code,
                flag="p",
                sector=_sector_for_tech(code),
                unlim_cap=1,
                annual=0 if is_elec_dist else 1,
                description=_tech_description(code),
                data_id=can_data_id,
            )
        )

    cur.executemany(*Technology.bulk_insert_or_ignore_sql(tech_rows))
    conn.commit()

    return fuel_flow_list
