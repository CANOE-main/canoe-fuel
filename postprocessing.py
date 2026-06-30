"""Write DataSet, DataSource, DataSourceLabel, and SectorLabel rows."""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from canoe_schema.v4_0.models import DataSet, DataSource, DataSourceLabel, SectorLabel

if TYPE_CHECKING:
    from common import CANOEFuelConfig

# Source registry.  Each entry becomes a DataSource + DataSourceLabel row.
# Decision: canoe-fuel uses INSERT OR IGNORE on SectorLabel so other modules
# can also seed sector labels without collision.
_SOURCES: list[tuple[str, str, str]] = [
    (
        "F1",
        "EIA AEO 2025",
        "Using table 3 via the API to get access to the costs of the different fuels for different sectors",
    ),
    (
        "F2",
        "NREL ATB electricity sector 2022",
        "Taking the fuel costs from the appropriate places in the excel workbook",
    ),
    (
        "F3",
        "Biofuels in Canada 2023",
        (
            "Michael Wolinetz & Sam Harrison. (2023). Biofuels in Canada 2023: "
            "Tracking biofuel consumption, feedstocks and avoided greenhouse gas emissions. "
            "Navius Research."
        ),
    ),
    (
        "F4",
        "Government of Canada, Emission factors and reference values",
        "The appropriate emission factors for sector and fuel are converted to tonnes or ktonnes per PJ",
    ),
    (
        "F5",
        "IPCC AR6",
        "Used for the GWP100 values for methane, carbon dioxide and nitrous oxide for calculating CO2eq",
    ),
    (
        "F6",
        "NS Dept. of Environment & Climate Change",
        "QRV standards (wood/ethanol/biodiesel factors)",
    ),
    (
        "F7",
        "Argonne National Laboratory, GREET model",
        "Upstream fuel emissions factors",
    ),
]

_SECTORS: dict[str, str] = {
    "electricity": "Electric power sector",
    "residential": "Residential sector",
    "commercial": "Commercial sector",
    "industrial": "Industrial sector",
    "transportation": "Transportation sector",
    "agriculture": "Agriculture sector",
    "fuel": "Fuel production sector",
}


def add_metadata(
    conn: sqlite3.Connection,
    *,
    cfg: "CANOEFuelConfig",
) -> None:
    """Write DataSet, DataSource, DataSourceLabel, and SectorLabel rows."""
    can_data_id = cfg.data_id("CAN")
    cur = conn.cursor()

    # DataSet — one row per province (including CAN aggregate)
    dataset_rows = [
        DataSet(
            data_id=cfg.data_id(pro),
            label=f"{pro} - fuel",
            version=f"v{cfg.version}",
            description="Original sector design",
            status="active",
            author="David Turnbull - david.turnbull1@ucalgary.ca",
            date="2025-08-01",
        )
        for pro in cfg.province_list
    ]
    cur.executemany(*DataSet.bulk_insert_or_ignore_sql(dataset_rows))

    # DataSource + DataSourceLabel
    source_rows = [
        DataSource(source_id=sid, source=name, notes=notes, data_id=can_data_id)
        for sid, name, notes in _SOURCES
    ]
    cur.executemany(*DataSource.bulk_insert_or_ignore_sql(source_rows))

    source_label_rows = [DataSourceLabel(source_id=sid) for sid, _, _ in _SOURCES]
    cur.executemany(*DataSourceLabel.bulk_insert_or_ignore_sql(source_label_rows))

    # SectorLabel — INSERT OR IGNORE; canoe-base should eventually own this table.
    # See DECISIONS.md for rationale.
    sector_rows = [SectorLabel(sector=k, notes=v) for k, v in _SECTORS.items()]
    cur.executemany(*SectorLabel.bulk_insert_or_ignore_sql(sector_rows))

    conn.commit()
