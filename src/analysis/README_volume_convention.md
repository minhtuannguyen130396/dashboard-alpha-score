## Volume Convention

Rule used in this project:

- Use `dealVolume` for any indicator, score, RVOL, breakout-volume check, OBV, MFI, VWAP, or chart volume that is meant to explain price movement.
- Keep `totalVolume` only as raw market data for reference.
- Reason: `totalVolume = dealVolume + putthroughVolume`, while `putthroughVolume` does not reflect the same direct order-book pressure on traded price.

Implementation note:

- `StockRecord.priceImpactVolume` is the canonical field for price-impact analysis.
- New analysis code should read `priceImpactVolume` instead of `totalVolume`.
