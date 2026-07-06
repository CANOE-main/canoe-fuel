# canoe-fuel — Decision Log

Decisions made during the Stage 2 refactor (v4.0 schema migration, Pydantic SQL, canoe-base DB contract).
Template: question → decision → owner/rationale → follow-ups.

---

### Emission commodities (`co2`, `ch4`, `n2o`, `co2e`)

- **Question:** Emission commodities are shared across all sector modules. Who owns the `commodity` rows for `co2`, `ch4`, `n2o`, and `co2e`?
- **Decision:** canoe-fuel writes these rows using `INSERT OR IGNORE`. Any other module that also needs them (e.g. canoe-electricity, canoe-industry) can safely do the same — the `OR IGNORE` prevents duplication.
- **Owner/rationale:** Yamil / Stage 2 refactor, 2025. Preferred outcome is that canoe-base seeds these globally (they are truly cross-sector), but that requires a canoe-base change which is out of scope for this round.
- **Follow-ups:** Open a canoe-base ticket to seed `co2`, `ch4`, `n2o`, `co2e` as part of the shared DB structure. Once done, remove the emission commodity rows from canoe-fuel and any other module that duplicates them.

---

### `sector_label` table

- **Question:** `sector_label` has one row per CANOE sector. No single module "owns" all sectors, but the table must be populated before any module references `sector` values.
- **Decision:** canoe-fuel writes all seven sector label rows using `INSERT OR IGNORE`. Other modules can do the same without collision.
- **Owner/rationale:** Same as above — canoe-base should eventually own this table. For now, the first module to run in a given pipeline initialises it.
- **Follow-ups:** canoe-base should seed `sector_label` in the same pass that creates `region` and `time_period`. Once done, sector modules should not write to this table.

---

### Cross-sector fuel commodities (`F_ng`, `F_coal`, etc.)

- **Question:** canoe-fuel defines `F_`-prefixed internal commodities as its supply-side carriers. Other sectors define their own sector-prefixed copies (`E_ng`, `R_ng`, `I_ng`, `T_ng`, `A_ng`). Is this duplication intentional, or should sectors share canonical fuel commodity rows?
- **Decision:** Sector-prefixed copies are intentional for this round. Each sector module independently defines the fuels it consumes under its own namespace, avoiding cross-module primary-key collisions. canoe-fuel owns the `F_`-prefixed supply side; consuming sectors own their own prefixed copies.
- **Owner/rationale:** Yamil / Stage 2 refactor, 2025. The sector-prefix convention is consistent with how canoe-agriculture namespaces its fuels (`A_ng`, `A_dsl`, etc.). Whether a commodity-balance layer should eventually connect `F_ng → E_ng / R_ng / ...` through `commodity_balance` rows is an open modelling question.
- **Follow-ups:** Revisit when designing cross-sector commodity balances. At that point, some `F_`-prefixed commodities may become the canonical shared representation that sector-specific distribution technologies consume directly, eliminating the duplicate definitions.

---

### `data_id` namespacing convention

- **Question:** What is the correct `data_id` string format for canoe-fuel v4.0 rows?
- **Decision:** `FUELHR{PROVINCE}{VERSION}` for province-level rows (e.g. `FUELHRAB001`) and `FUELHR{VERSION}` for national/CAN-level rows (e.g. `FUELHR001`). This matches the pre-existing convention in the original code and is consistent with the pattern used by canoe-agriculture (`AGRIHR...`).
- **Owner/rationale:** Yamil / Stage 2 refactor, 2025.
- **Follow-ups:** Confirm with canoe-base whether a formal `data_id` naming registry or prefix reservation scheme is needed to prevent collisions between modules.

---

### `input/schema_3_1.sql` retention

- **Question:** Now that the module no longer creates the DB, is `input/schema_3_1.sql` still needed?
- **Decision:** The file is retained but not used. It can be deleted once the team confirms no other tooling or documentation references it.
- **Owner/rationale:** Yamil / Stage 2 refactor, 2025. Left in place to avoid an accidental loss of reference during the transition period.
- **Follow-ups:** Delete `input/schema_3_1.sql` in a cleanup PR once canoe-base is confirmed as the sole DB creator.
