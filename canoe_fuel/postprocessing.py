"""Write DataSet, DataSource, and SectorLabel rows for the fuel pipeline."""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from canoe_schema.v4_0.models import DataSet, DataSource, SectorLabel

if TYPE_CHECKING:
    from canoe_fuel.common import CANOEFuelConfig


def add_metadata(conn: sqlite3.Connection, *, cfg: "CANOEFuelConfig") -> None:
    """Write DataSet, DataSource, and SectorLabel rows."""
    cur = conn.cursor()

    # DataSet — one row per province (including CAN for the shared national dataset)
    ds_rows = [
        DataSet(
            data_id=cfg.data_id(pro),
            label=f"{pro} - fuel",
            version=f"v{cfg.version}",
            description="2025 annual update",
            status="active",
            author="David Turnbull - david.turnbull1@ucalgary.ca",
            date="2025-08-01",
            changelog="Original sector design",
        )
        for pro in cfg.province_list
    ]
    cur.executemany(*DataSet.bulk_insert_or_ignore_sql(ds_rows))

    # DataSource — source registry for the fuel module (INSERT OR IGNORE)
    can_data_id = cfg.data_id("CAN")
    src_rows = [
        DataSource(source_id="F1", source="EIA AEO 2025", notes="Using table 3 via the API to get access to the costs of the different fuels for different sectors", data_id=can_data_id),
        DataSource(source_id="F2", source="NREL ATB electricity sector 2022", notes="Taking the fuel costs from the appropriate places in the excel workbook", data_id=can_data_id),
        DataSource(source_id="F3", source="Biofuels in Canada 2023", notes="Michael Wolinetz & Sam Harrison. (2023). Biofuels in Canada 2023: Tracking biofuel consumption, feedstocks and avoided greenhouse gas emissions. Navius Research.", data_id=can_data_id),
        DataSource(source_id="F4", source="Government of Canada, Emission factors and reference values", notes="The appropriate emission factors for sector and fuel are converted to tonnes or ktonnes per PJ", data_id=can_data_id),
        DataSource(source_id="F5", source="IPCC AR6", notes="Used for the GWP100 values for methane, carbon dioxide and nitrous oxide for calculating CO2eq", data_id=can_data_id),
        DataSource(source_id="F6", source="NS Dept. of Environment & Climate Change", notes="QRV standards (wood/ethanol/biodiesel factors)", data_id=can_data_id),
        DataSource(source_id="F7", source="Environment and Climate Change Canada. (2024). Fuel life cycle assessment model user manual (June 2024). Government of Canada.", notes="Upstream fuel emissions factors", data_id=can_data_id),
        DataSource(source_id="F8", source="Argonne National Laboratory, GREET model", notes="Upstream fuel emissions factors", data_id=can_data_id),
    ]
    cur.executemany(*DataSource.bulk_insert_or_ignore_sql(src_rows))

    # SectorLabel — INSERT OR IGNORE; canoe-base is the long-term owner of this table
    sector_rows = [
        SectorLabel(sector="electricity", notes="Electric power sector"),
        SectorLabel(sector="residential", notes="Residential sector"),
        SectorLabel(sector="commercial", notes="Commercial sector"),
        SectorLabel(sector="industrial", notes="Industrial sector"),
        SectorLabel(sector="transportation", notes="Transportation sector"),
        SectorLabel(sector="agriculture", notes="Agriculture sector"),
        SectorLabel(sector="fuel", notes="Fuel production sector"),
    ]
    cur.executemany(*SectorLabel.bulk_insert_or_ignore_sql(sector_rows))

    conn.commit()
