# Fading extreme hourly candles 24 h later — Phase 0 validation on Hyperliquid

One-shot study testing whether fading an extreme 1 h candle exactly 24 h later (when it drops out of the exchange's "24h %" window) beats fading it 23 or 25 h later. Result: **DISCARD** on Hyperliquid perps.

## Hypothesis

Exchanges display the 24 h change as current price versus the price 24 h ago. When an extreme 1 h candle leaves that rolling window, the displayed "24h %" moves mechanically, with no new information, and retail flow is assumed to react to the displayed number. If so, fading the extreme candle during the hour in which it exits the window (lag k = 24) should earn more than fading it at neighbouring lags (k = 23, 25, …).

The idea and the original test come from Robot James, *rj's trading for dickheads* (Substack). This repository re-tests it on a different venue with a pre-specified decision rule and an explicit alternative: generic short-term reversal after extreme moves, with no peak specific to lag 24.

## Verdict: DISCARD (Hyperliquid)

The gross mean fade return at k = 24 is +6.8, +7.0, +8.0, +10.9, +11.1 and +13.5 bp for thresholds 3, 3.5, 4, 4.5, 5 and 6. The minimum round-trip cost in the most liquid quartile is 13 bp, and the net mean at k = 24 in that quartile is negative at every threshold (best case: threshold 4.5, −5.0 bp, 95 % CI [−19.3, +11.2]).

The lag-24 specific test D = fade_24 − mean(fade_22, fade_23, fade_25, fade_26) is positive at every threshold (+4.1 to +11.3 bp) but its 95 % CI includes zero at all six (e.g. threshold 3: +4.1 bp, CI [−3.5, +11.0], n = 24,002). The mechanism is not refuted, it is underpowered: at the observed effect size roughly 3× the current history would be needed to exclude zero. Even then, an effect of 4–11 bp does not cover fees, so more data would not change the trading decision.

## Data

- Source: exclusively `POST https://api.hyperliquid.xyz/info` (`meta` for the universe, `candleSnapshot` for candles). No keys, no orders, read-only.
- Universe: 234 perpetuals, 56 of them flagged `isDelisted`. 1 h candles, 1,147,017 in total, no gaps in any coin.
- The API returns at most the ~5,000 most recent candles per coin (median 5,001, maximum 5,003; three delisted coins have shorter series). For active coins this covers 2026-03-07 10:00 UTC to 2026-10-01 20:00 UTC (208 days), less for coins listed later.
- Delisted coins are different: their 5,000 candles end at the delisting date, so they cover earlier windows between 2023-10-07 and 2026-08-26 that do not overlap with the active coins' period. They are included in the main analysis and all headline tables are also reported without them. Including them raises the number of independent calendar days (953 vs 205 at threshold 3) at the cost of mixing market regimes and coins that ended up delisted.
- Timestamps are UTC milliseconds as delivered by the API. Raw candles are cached in `data/candles/<COIN>.parquet` (git-ignored); the download is resumable.

## Method

**Returns and z-scores.** r_t = ln(close_t / close_{t−1}) is the return of the candle opening at t. The main score excludes the candle being scored from its own baseline:

- z_excl(t) = (r_t − mean(r_{t−24..t−1})) / sd(r_{t−24..t−1}), sample sd (ddof = 1).
- z_incl(t): same formula with candle t included in the 24 (the original article's version), computed for comparison only. With n = 24 and the point included, Samuelson's inequality bounds |z_incl| ≤ (n−1)/√n = 23/√24 ≈ 4.69; the maximum observed is 4.68 versus 66.4 for z_excl. Thresholds 5 and 6 are therefore unreachable with z_incl.

| threshold | events (z_excl) | events (z_incl) |
|---|---|---|
| 3 | 24,002 | 9,704 |
| 3.5 | 14,580 | 3,403 |
| 4 | 9,317 | 844 |
| 4.5 | 6,174 | 78 |
| 5 | 4,221 | 0 |
| 6 | 2,198 | 0 |

**Events and fades.** An event is a candle with |z_excl| ≥ threshold, for thresholds 3.0, 3.5, 4.0, 4.5, 5.0 and 6.0 (nested sets). Fade direction is −sign(r_t). The fade return at lag k is a one-candle trade: enter at the open of the candle opening at t + k hours, exit at its close, fade_k = −sign(r_t) · ln(close_{t+k} / open_{t+k}), for all k = 18..30. Candles are placed on a complete hourly grid so t + k is always clock time, not row offset. `tests/test_lag24.py` checks that at k = 24 the entry candle is exactly the hour during which the event candle leaves the 24 h window.

**Filters** (applied in sequence; counts are candidates removed):

| threshold | candidates | − first 72 h of listing | − incomplete window (start/end of history) | − gap or zero volume in [t−24, t+30] | valid events | of which delisted coins |
|---|---|---|---|---|---|---|
| 3 | 26,574 | 213 | 128 | 2231 | 24,002 | 4881 |
| 3.5 | 16,285 | 119 | 75 | 1511 | 14,580 | 2992 |
| 4 | 10,525 | 81 | 46 | 1081 | 9,317 | 1949 |
| 4.5 | 7,070 | 63 | 30 | 803 | 6,174 | 1297 |
| 5 | 4,929 | 54 | 22 | 632 | 4,221 | 937 |
| 6 | 2,664 | 34 | 13 | 419 | 2,198 | 530 |

**Inference.** All confidence intervals are 95 % intervals from a cluster bootstrap over UTC calendar days (2,000 resamples). Events cluster on market-wide days, so a per-event bootstrap would understate uncertainty. The pre-specified test is D = fade_24 − mean(fade_22, fade_23, fade_25, fade_26).

**Placebo.** For each threshold, the same number of timestamps per coin is drawn at random from the valid candles, with random direction, and the same lag curve is computed. It is flat around zero (see `graficas/curva_rezagos_<threshold>.png`, orange curve).

**Costs.** Taker fee 0.045 % per side (0.09 % round trip) plus assumed slippage per side by liquidity quartile: 0.02 %, 0.05 %, 0.10 % and 0.20 % from most to least liquid. Quartiles are based on mean hourly USD volume over the 24 h before the event, with cut points fixed on the threshold-3.0 event set (5 k, 13 k, 61 k USD/h). Round-trip cost is therefore 13, 19, 29 and 49 bp for Q1–Q4.

**Non-overlapping simulation.** Threshold 4.0, fixed size, one position per coin at a time (a coin is busy from the signal at t until the exit at t + 25 h), net of costs: 8,028 trades, mean net −20.6 bp, hit rate 37.5 %, worst trade −15.99 %. Restricted to Q1: 1,985 trades, mean net −9.3 bp, hit rate 44.8 %.

## Results

D by threshold, delisted coins included (bp; 1 bp = 0.01 %):

| threshold | events | days | D (bp) | 95 % CI (bp) | excludes 0 |
|---|---|---|---|---|---|
| 3 | 24,002 | 953 | +4.1 | [-3.5, +11.0] | no |
| 3.5 | 14,580 | 869 | +4.0 | [-3.5, +11.9] | no |
| 4 | 9,317 | 757 | +4.8 | [-3.6, +14.1] | no |
| 4.5 | 6,174 | 652 | +7.7 | [-2.3, +20.8] | no |
| 5 | 4,221 | 566 | +8.3 | [-3.9, +23.4] | no |
| 6 | 2,198 | 443 | +11.3 | [-4.1, +29.8] | no |

Without delisted coins:

| threshold | events | D (bp) | 95 % CI (bp) |
|---|---|---|---|
| 3 | 19,121 | +3.6 | [-5.3, +11.8] |
| 3.5 | 11,588 | +3.0 | [-6.1, +12.4] |
| 4 | 7,368 | +3.1 | [-7.2, +14.5] |
| 4.5 | 4,877 | +5.3 | [-6.2, +20.9] |
| 5 | 3,284 | +6.4 | [-7.8, +25.5] |
| 6 | 1,668 | +10.4 | [-7.6, +33.8] |

Mean fade return by lag (bp, delisted included; bold = 95 % CI excludes zero):

| threshold | n | k=18 | k=19 | k=20 | k=21 | k=22 | k=23 | k=24 | k=25 | k=26 | k=27 | k=28 | k=29 | k=30 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3 | 24,002 | -1.6 | +1.1 | -5.3 | +3.4 | +2.5 | +3.8 | +6.8 | +2.3 | +2.4 | +1.4 | **-3.6** | -0.6 | +3.4 |
| 3.5 | 14,580 | -2.3 | +0.7 | -6.2 | +2.6 | +2.7 | +3.2 | **+7.0** | +3.8 | +2.1 | +1.9 | -2.9 | -1.0 | +3.7 |
| 4 | 9,317 | -3.3 | -0.2 | **-8.0** | +3.0 | +3.2 | +3.3 | +8.0 | +4.6 | +1.6 | +3.1 | -2.9 | -0.4 | +3.8 |
| 4.5 | 6,174 | -3.4 | +0.0 | **-10.0** | +3.1 | +2.1 | +3.6 | **+10.9** | +4.7 | +2.2 | +4.0 | -1.3 | +1.1 | +3.8 |
| 5 | 4,221 | -4.0 | -1.0 | **-11.2** | +0.9 | +1.7 | +4.4 | +11.1 | +3.9 | +1.4 | +4.4 | -1.1 | +3.1 | +3.1 |
| 6 | 2,198 | -1.5 | +1.9 | **-12.4** | +0.9 | +1.2 | +2.9 | +13.5 | +5.3 | -0.5 | +6.3 | -2.0 | +6.0 | -1.0 |

Two features of the curve deserve attention:

- k = 24 is the maximum of the curve at all six thresholds and the point estimate grows with the threshold, consistent with the hypothesis but never significant under the cluster bootstrap.
- There is a trough at k = 20 of comparable magnitude and opposite sign (−5.3 to −12.4 bp), significant at thresholds 4 to 6, which the 24 h-window mechanism does not predict. With 13 lags × 6 nested thresholds, isolated intervals that exclude zero are expected; the pre-specified test remains D, which does not.

Net return at k = 24 in the most liquid quartile (Q1), round-trip cost 13 bp:

| threshold | n (Q1) | gross k=24 (bp) | net k=24 (bp) | net 95 % CI |
|---|---|---|---|---|
| 3 | 6,001 | +11.3 | -1.7 | [-9.9, +6.2] |
| 3.5 | 3,619 | +9.1 | -3.9 | [-13.7, +6.3] |
| 4 | 2,270 | +6.3 | -6.7 | [-18.7, +6.1] |
| 4.5 | 1,494 | +8.0 | -5.0 | [-19.3, +11.2] |
| 5 | 961 | +2.7 | -10.3 | [-28.6, +10.1] |
| 6 | 485 | -0.8 | -13.8 | [-38.8, +10.6] |

Splits by direction (green candles faded short vs red faded long) and by all four liquidity quartiles are in `REPORTE.md` sections 4.3 and 4.4. The only sub-splits whose D interval excludes zero are green events at thresholds 3.0 and 3.5 and quartile Q2 at thresholds ≥ 4.0; these are a few of many comparisons and their net returns are still ≤ 0 or have intervals that include zero.

Figures: `graficas/curva_rezagos_<threshold>.png` (lag curve with CI band, vertical line at k = 24, placebo overlaid) and `graficas/simulacion_equity.png`. All table values are in `resultados/*.csv`.

## Limitations

- **Short history.** Active coins cover ~208 days (2026-03-07 to 2026-10-01), a single market regime. Seasonal or regime effects are not observable.
- **Mixed regimes with delisted coins.** Delisted coins contribute non-overlapping windows from 2023–2026 and are, by construction, coins that ended up delisted. Headline numbers are reported with and without them.
- **Few independent clusters.** The day-clustered bootstrap has ~205 clusters without delisted coins; intervals on D are wide, and those on direction and quartile splits are wider.
- **Nested thresholds.** The six threshold sets are subsets of each other, not independent tests. Agreement across thresholds is not six confirmations.
- **Multiple comparisons.** 6 thresholds × 13 lags × splits. Some intervals excluding zero by chance are expected; only D at k = 24 was pre-specified.
- **Assumed costs.** Slippage per quartile is an assumption, not an order-book measurement. Net results in the less liquid quartiles are very sensitive to it.
- **Execution at the candle open.** Entry at the open of t + k and exit at its close is assumed exact; a 1 h candle's open is not a guaranteed tradeable price.

## Reproduce

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py                # download (resumable) + events + analysis + report
.venv/bin/python tests/test_lag24.py   # lag-24 alignment test
```

`run.py` downloads candles only if `data/candles/` is empty (pass `--download` to force a resumable download), then regenerates `resultados/`, `graficas/` and `REPORTE.md`. The bootstrap and placebo seeds are fixed; two runs produce identical CSVs. Pinned versions: requests 2.34.2, polars 1.44.2, numpy 2.5.3, matplotlib 3.11.2, pyarrow 25.0.1.

## Full report

[REPORTE.md](REPORTE.md) (Spanish) contains the complete tables: filters, lag curves with intervals, placebo, direction and liquidity splits, costs, the non-overlapping simulation and the full limitations section.
