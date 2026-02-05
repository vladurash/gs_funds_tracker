## GS Funds Tracker (HACS/Config Flow)

Home Assistant custom integration that polls the Goldman Sachs funds endpoint and exposes sensors per investment entry:
- Net Asset Value (NAV)
- Profit / benefit (absolute)
- Return (percentage)

Defaults: `resource_url` https://am.gs.com/services/funds and 1-hour refresh.

### Install
- HACS: add this repo as a custom repository (category “Integration”), install **GS Funds Tracker**.
- Local: copy `custom_components/gs_funds_tracker` into your Home Assistant `config/custom_components/`.
- Restart Home Assistant.

### Configure (UI only)
1) Settings → Devices & Services → Add Integration → **GS Funds Tracker** (or Configure if already added).
2) Step 1: set `resource_url` (optional) and `scan_interval` (seconds, ≥60).
3) Step 2: add entries (you can add multiple, edit, or delete later):
   - `name` (friendly label)
   - `pvNumber`
   - `shareClassId`
   - `investment_date` (optional)
   - `value_of_investment` (optional; used to infer units if `units_acquired` missing)
   - `price_per_unit` (required)
   - `units_acquired` (optional)
   - `currency` (optional)
4) Finish. To adjust later, open Configure → entries menu to add/edit/delete.

### Sensors per entry
- `sensor.<entry_slug>_nav`: `{fundName} - {shareClassId}` with attributes `as_at_date`, `currency`, `up_down_value`, `up_down_pct`, etc.
- `sensor.<entry_slug>_profit`: `{fundName} Profit Net`, computed from `(current_nav - acquisition_price) * total_units`.
- `sensor.<entry_slug>_return_pct`: `{fundName} Randament`, computed from `(current_nav / acquisition_price - 1) * 100`.

`entry_slug` is the slugified `name`/`shareClassId`.

### How it works
- Uses HA `aiohttp` client to POST the GS GraphQL query and reads `netAssetValue` from `quickStats`.
- Derives units when missing and `value_of_investment` + `price_per_unit` are given.
- If multiple entries share the same `shareClassId`/`pvNumber`, it computes a weighted average acquisition price:  
  `(P1*U1 + P2*U2 + ... + Pn*Un) / (U1 + U2 + ... + Un)` and uses the group total units. Profit/return use this averaged price and total units so positions for the same share class are aggregated.
- Updates every `scan_interval` seconds (default 3600).
- Sensor display names honor the user-provided `name`; unique IDs use the slugified `name`/`shareClassId`.
