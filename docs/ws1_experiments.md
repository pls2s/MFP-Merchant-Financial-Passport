# WS1 — Robustness experiments (Rossmann)

Supplementary analysis for the report. The main results stay at seed 42 (CLAUDE.md); nothing here
changed the chosen models. Charts are in `notebooks/forecast_results.ipynb` sections 7–9.

```bash
python -m ai.cashflow_forecast.experiments curves     # from models/logs/tune.log
python -m ai.cashflow_forecast.experiments ablation
python -m ai.cashflow_forecast.experiments seeds
```

## Learning curves

`models/experiments/learning_curves.csv` — every tuning run, per epoch. Train loss keeps falling
below validation WAPE while validation stops improving after a few epochs (LSTM best at epoch 5,
GRU at epoch 11): the models overfit, and early stopping on validation WAPE picks the turning point.

## Ablation — LSTM (w56/h128/l1, seed 42), one component removed at a time

| Variant | Val WAPE | Test WAPE | Δ Test |
| --- | --- | --- | --- |
| Full model | 7.19% | 8.54% | — |
| No per-window level normalisation | 10.65% | 11.54% | +3.00 pt |
| No store embedding | 8.44% | 9.40% | +0.86 pt |
| No previous/next-day known features | 7.69% | 8.39% | −0.15 pt |
| Unweighted loss | 7.39% | 8.44% | −0.10 pt |

- Per-window normalisation is the most important component. Without it the model anchors on each
  store's Train-period average and under-forecasts as 2015 sales grow.
- The store embedding helps on both Validation and Test.
- Neighbour-day features and the WAPE-weighted loss help on Validation, but their Test effect
  (±0.1–0.15 pt) is smaller than the LSTM's seed-to-seed spread (std 0.40 pt), so it is not
  distinguishable from noise. They were kept, because removing them on the basis of Test would use
  the Test set for model selection.

## Seeds — Test WAPE over 5 seeds (42 is the main result)

| Seed | LightGBM | LSTM | GRU | LSTM+GRU |
| --- | --- | --- | --- | --- |
| 42 | 8.23% | 8.54% | 8.28% | 8.18% |
| 1 | 8.29% | 8.39% | 8.82% | 8.34% |
| 2 | 8.33% | 9.01% | 8.69% | 8.67% |
| 3 | 8.27% | 8.96% | 8.31% | 8.33% |
| 4 | 8.38% | 9.40% | 8.69% | 8.09% |
| **Mean ± std** | **8.30% ± 0.06** | 8.86% ± 0.40 | 8.56% ± 0.25 | **8.32% ± 0.22** |

- LSTM+GRU beats LightGBM in 2 of 5 seeds; the means differ by 0.02 pt, well inside the spread.
- LightGBM is far more stable across seeds (std 0.06 pt vs 0.22–0.40 pt for the RNNs).
- Averaging LSTM and GRU reduces both the error and the variance of the single RNNs.

## Conclusion for the report

The LSTM+GRU forecaster meets the WAPE ≤ 20% target with a wide margin and is **on par with**
a strong LightGBM baseline (8.32% vs 8.30% mean Test WAPE), but does not consistently beat it and
is more sensitive to the random seed. The seed-42 result where the ensemble is ahead by 0.05 pt
should be reported together with this table.
