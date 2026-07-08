# canoe-fuel — External Data Sources

| ID | Source | What it provides | Accessed by | Cache / file |
|---|---|---|---|---|
| F1 | EIA AEO 2025, Table 3 (API) | Sector-differentiated fuel prices (natural gas, diesel, HFO, propane, jet fuel, gasoline, coal, hydrogen) for Commercial, Industrial, Electric Power, Residential, and Transportation sectors | `eia_api.fetch_and_cache` | `cache/dataframes.pkl` |
| F2 | NREL ATB Electricity Sector 2022 | Fuel costs for biomass, wood, and uranium (natural and enriched); assumed constant across all model periods | Config parameters `b_price`, `u_price` | `input/params.toml` |
| F3 | Wolinetz & Harrison, *Biofuels in Canada 2023*, Navius Research | Canadian ethanol and renewable diesel prices; accounts for biofuel transportation costs in Ontario; average of 2012–2022, no time projection | Fixed prices in `inflation` sub-model | `input/params.toml` |
| F4 | Government of Canada, Emission Factors and Reference Values | Direct combustion emission factors (CO₂, CH₄, N₂O) by fuel type and sector, converted to kTonne/PJ or Tonne/PJ | `emissionactivity.load_emission_factors` | `input/direct_comb_emission.csv` |
| F5 | IPCC AR6 | GWP100 values for CH₄ and N₂O used to compute CO₂e emission factors | Baked into `input/direct_comb_emission.csv` | `input/direct_comb_emission.csv` |
| F6 | NS Dept. of Environment & Climate Change, QRV Standards | Direct combustion factors for wood, ethanol, biodiesel, and related biofuels | `emissionactivity.load_emission_factors` | `input/direct_comb_emission.csv` |
| F7 | Argonne National Laboratory, GREET Model | Upstream (well-to-gate) CO₂ emission factors for fossil fuels | `emissionactivity.load_emission_factors` | `input/upstream_emissions_fuels.csv` |
| — | `input/fuel_list.csv` | Master list of commodity codes, fuel type keys, price label mappings, and per-commodity data source annotations | `setup.load_fuel_list` | `input/fuel_list.csv` (static) |

## Notes

- EIA AEO prices are US national data in `2024 $/MMBtu`. The pipeline converts to 2020 CAD M$/PJ using a currency factor (1.22 USD/CAD) and GDP deflators defined in `input/params.toml` under `[inflation]`.
- No provincial price differentiation is applied: all ten Canadian provinces receive the same fuel price derived from the EIA national series.
- Several fuels lack a direct EIA price series and are assigned proxy prices (e.g. CNG/LNG → Transportation natural gas × 0.89; MDO → Transportation diesel × 0.9). Proxy logic is in `costvariable.py:_calc_price`.
- `fuel_list.csv` is a static authored file, not fetched from an external source, but it is the control list that drives which commodities and technologies the module generates. Changes to it directly change model scope.
