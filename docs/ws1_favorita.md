# WS1 — Favorita generalization test (optional)

Re-runs the Rossmann forecasting method on a second retailer **without re-tuning**, to check that
the result is not specific to Rossmann.

```bash
python -m ai.cashflow_forecast.favorita
python -m ai.cashflow_forecast.train --dataset favorita --model seasonal_naive
python -m ai.cashflow_forecast.train --dataset favorita --model lightgbm
python -m ai.cashflow_forecast.train --dataset favorita --model lstm --window 56 --hidden 128 --layers 1
python -m ai.cashflow_forecast.train --dataset favorita --model gru --window 28 --hidden 128 --layers 2
python -m ai.cashflow_forecast.train --dataset favorita --model ensemble
python -m ai.cashflow_forecast.evaluate --dataset favorita
```

## Data

[Favorita Store Sales](https://www.kaggle.com/competitions/store-sales-time-series-forecasting):
54 supermarkets in Ecuador, 2013-01-01 to 2017-08-15. Sales are summed over the 33 product families
to one series per store. Mapping to the Rossmann schema is documented in
`ai/cashflow_forecast/favorita.py` (no `Open` column → `sales > 0`; no school holidays or competition
distance; promotions are item counts scaled per store).

| Set | Dates | Days | Evaluated store-days |
| --- | --- | --- | --- |
| Train | 2013-01-01 to 2017-05-23 | 1,604 | 79,070 |
| Validation | 2017-05-24 to 2017-07-04 | 42 | 2,268 |
| Test | 2017-07-05 to 2017-08-15 | 42 | 2,268 |

Same protocol as Rossmann: three rolling 14-day origins per period, metrics on open days only,
seed 42. LSTM and GRU use the configurations chosen on Rossmann. The ensemble rule (adopt if
validation WAPE beats the best single model) holds here too: 7.72% vs GRU 7.80%.

## Results

| Model | Val WAPE | Test WAPE | Test MAE | Test RMSE |
| --- | --- | --- | --- | --- |
| Seasonal naive | 15.16% | 14.98% | 2,324 | 3,448 |
| LightGBM | 8.54% | **8.59%** | **1,332** | **2,002** |
| LSTM | 8.06% | 9.13% | 1,416 | 2,100 |
| GRU | 7.80% | 9.48% | 1,471 | 2,223 |
| LSTM+GRU | **7.72%** | 9.11% | 1,413 | 2,125 |

Rossmann for comparison (Test WAPE): naive 22.39%, LightGBM 8.23%, LSTM 8.54%, GRU 8.28%, LSTM+GRU 8.18%.

## Findings

- The method transfers: every learned model meets WAPE ≤ 20% and beats seasonal naive by a wide
  margin on both datasets.
- On Favorita, LightGBM wins on Test by about 0.5 pt; the ensemble does not beat it, unlike Rossmann
  where it was ahead by 0.05 pt.
- The same pattern appears on both datasets: LSTM/GRU are better than LightGBM on Validation but
  not on Test. Validation is used for early stopping and (on Rossmann) model selection, so it is
  optimistic for the RNNs; LightGBM's Validation and Test scores stay close.
- Favorita is much smaller (54 stores, ~68k training windows vs ~834k on Rossmann), which leaves
  less data for the RNNs to learn from.

Conclusion for the report: the LSTM/GRU forecaster is competitive with a strong gradient-boosting
baseline and generalizes to a second retailer, but it does not consistently outperform it.
