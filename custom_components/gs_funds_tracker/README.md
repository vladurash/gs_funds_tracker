# GS Funds Tracker (HACS custom integration)

Home Assistant custom integration that polls the Goldman Sachs funds endpoint and exposes sensors for each investment entry:
- Net Asset Value (NAV)
- Profit / benefit (absolute)
- Return (percentage)

Resource URL `https://am.gs.com/services/funds` .

## Install (local or HACS custom repo)
- For local dev: copy `custom_components/gs_funds_tracker` (this folder) into your Home Assistant `config/custom_components/` directory.
- For HACS: add this repo as a custom repository (category “Integration”), then install **GS Funds Tracker**.

Restart Home Assistant after installation.

## Configure (UI only)
- Go to *Settings → Devices & Services → Add Integration* and search **GS Funds Tracker** (or start from the HACS card).
- Step 1: Set `resource_url` (optional) and `scan_interval` in seconds (optional, min 60).
- Step 2: Add entries (multiple). Fields per entry:
  - `name` (friendly label used in sensors)
  - `pvNumber`
  - `shareClassId`
  - `investment_date` (optional)
  - `value_of_investment` (optional; used to infer units if `units_acquired` missing)
  - `price_per_unit` (required)
  - `units_acquired` (optional)
  - `currency` (optional)
- After adding at least one entry, choose Finish. The integration stores settings in Options.
- To edit later: Settings → Devices & Services → GS Funds Tracker → Configure. You can add, edit, or delete entries; forms are prefilled when editing.

## Sensors created per entry
- `sensor.<entry_slug>_nav`: `{fundName} - {shareClassId}` with attributes `as_at_date`, `currency`, `up_down_value`, `up_down_pct`, etc.
- `sensor.<entry_slug>_profit`: `{fundName} Profit Net`, computed from `(current_nav - price_per_unit) * units`.
- `sensor.<entry_slug>_return_pct`: `{fundName} Randament`, computed from `(current_nav / price_per_unit - 1) * 100`.

`entry_slug` is the lowercased name/shareClassId slug (non-alphanumerics replaced with `_`).

## How it works
- Uses Home Assistant’s `aiohttp` client to POST the GS GraphQL payload and parse NAV (`netAssetValue`) from `quickStats`.
- Derives units if `units_acquired` is missing but both `price_per_unit` and `value_of_investment` are provided.
- Updates every `scan_interval` seconds (default 3600).
- Sensor display names honor the user-provided `name`; underlying unique IDs use the slugified `name`/`shareClassId` combination.
