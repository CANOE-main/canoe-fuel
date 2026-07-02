"""Pydantic configuration model for the canoe-fuel pipeline."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator


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

    @model_validator(mode="after")
    def _check_version_format(self) -> "CANOEFuelConfig":
        if not self.version.isdigit():
            raise ValueError(f"version must be numeric digits only, got '{self.version}'")
        return self

    @classmethod
    def validate_from_yaml(cls, path: str | Path = "input/params.yaml") -> "CANOEFuelConfig":
        """Load and validate config from a YAML file.

        The YAML key 'periods' is accepted as an alias for 'future_periods' to
        ease migration from the old params.yaml format.
        """
        with Path(path).open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        # Accept legacy 'periods' key
        if "periods" in raw and "future_periods" not in raw:
            raw["future_periods"] = raw.pop("periods")

        # schema_version in old yaml was a list; flatten to first element
        if isinstance(raw.get("schema_version"), list):
            raw["schema_version"] = str(raw["schema_version"][0]).replace("_", ".")

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
