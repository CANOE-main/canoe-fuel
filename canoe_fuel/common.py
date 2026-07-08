"""Pydantic configuration model for the canoe-fuel pipeline."""

from __future__ import annotations
import tomllib
from pathlib import Path
from typing import Literal, Union
from pydantic import BaseModel, ConfigDict, RootModel, model_validator

# The two filter "variants"
class BlanketFuelFilter(RootModel[str]):
    def get_commodity(self) -> str:
        return self.root

class RegionPeriodFuelFilter(RootModel[tuple[str, str, float]]):
    def get_commodity(self) -> str:
        commodity, region, period = self.root
        return f"{commodity}:{region}:{period}"

FuelFilter = Union[BlanketFuelFilter, RegionPeriodFuelFilter]

class InflationFactors(BaseModel):
    """Currency conversion and GDP deflation constants used in price calculations.

    deflation_2022 / deflation_2025: GDP deflators to convert nominal prices to
    real 2020 CAD.  Source years differ because NREL ATB uses 2022 dollars while
    EIA AEO uses 2024/2025 dollars.
    currency_adjustment: USD → CAD conversion factor.
    mmbtu_convertor: 1 MMBtu = 1.055 GJ, used to convert $/MMBtu → $/GJ before
    applying the PJ-scale unit target.
    eth_price / rdsl_price / spk_price: fixed 2020 M$/PJ prices for ethanol,
    renewable diesel, and synthetic jet fuel (from Wolinetz & Harrison 2023 /
    NREL ATB — no time projection applied).
    """
    deflation_2022: float = 0.861446913
    deflation_2025: float = 0.877689699
    currency_adjustment: float = 1.22
    mmbtu_convertor: float = 1.055
    eth_price: float = 25.801332399
    rdsl_price: float = 34.286607549
    spk_price: float = 53.947379869


class CANOEFuelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "4.0"
    db_dir: str
    eia_year: int
    version: str
    future_periods: list[int]
    u_price: float
    b_price: float
    province_list: list[str]
    validation_behavior: Literal["error", "warning"] = "error"
    inflation: InflationFactors = InflationFactors()

    # EIA series selectors — expose so they're reviewable, not buried in code
    eia_unit_filter: str = "2024 $/MMBtu"
    eia_exclude_pattern: str = "average"

    # Fuel list filtering (input/fuel_list.csv, 'Commodity' column)
    exclude_fuels: list[FuelFilter] | None = None

    @model_validator(mode="after")
    def _check_version_format(self) -> "CANOEFuelConfig":
        if not self.version.isdigit():
            raise ValueError(f"version must be numeric digits only, got '{self.version}'")
        return self

    @classmethod
    def validate_from_toml(cls, path: str | Path = "input/params.toml") -> "CANOEFuelConfig":
        """Load and validate config from a TOML file."""
        with Path(path).open("rb") as fh:
            raw = tomllib.load(fh)

        # Inflate inflation sub-model from top-level keys if sub-dict absent
        if "inflation" not in raw:
            inflation_keys = {
                "deflation_2022", "deflation_2025", "currency_adjustment",
                "mmbtu_convertor", "eth_price", "rdsl_price", "spk_price",
            }
            inflation_raw = {k: raw.pop(k) for k in inflation_keys if k in raw}
            if inflation_raw:
                raw["inflation"] = inflation_raw

        return cls.model_validate(raw)

    def data_id(self, province: str) -> str:
        """Return the canonical data_id for a given province (or 'CAN' for national)."""
        if province == "CAN":
            return f"FUELHR{self.version}"
        return f"FUELHR{province}{self.version}"
