# Keep `isSpeedLimitEnabled` separate from `speedLimitation`

The global download limit is modeled as a boolean (`isSpeedLimitEnabled`) plus a
value (`speedLimitation`), even though the adjacent BitTorrent upload limit
(`maxUploadSpeed`) uses a single value where `0 = unlimited`. We deliberately
keep the separate enable flag: the user can toggle the limit off and back on
without losing their configured rate — the off state must not destroy the value.

## Considered Options

- **Collapse to a single `speedLimitation` with `0 = unlimited`** (matching
  `maxUploadSpeed`, removing one config item and the `_downloadLimit` branch).
  Rejected: turning the limit off would have to write `0`, discarding the
  remembered rate, so re-enabling couldn't restore it. The enable/disable state
  is intentionally independent of the rate value.
