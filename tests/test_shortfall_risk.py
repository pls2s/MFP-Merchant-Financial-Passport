import numpy as np

from ai.gap_detection.shortfall_risk import reliability, sample_paths, shortfall_probability


def test_probability_is_share_of_paths_below_zero():
    # 4 paths, 1 store, 3 days; opening 100, an expense of 150 on day 2.
    paths = np.array([[[0, 0, 0]], [[0, 40, 0]], [[0, 60, 0]], [[0, 100, 0]]], dtype=float)
    b0 = np.array([100.0])
    exp_next = np.array([[0.0, 150.0, 0.0]])
    p, bal = shortfall_probability(paths, b0, exp_next)
    assert bal.shape == (4, 1, 3)
    # day 2 balances: -50, -10, +10, +50 → 2 of 4 below zero
    np.testing.assert_allclose(p[0], [0.0, 0.5, 0.5])


def test_no_expenses_no_risk():
    paths = np.random.default_rng(0).uniform(0, 10, size=(50, 3, 14))
    p, _ = shortfall_probability(paths, np.full(3, 10.0), np.zeros((3, 14)))
    assert (p == 0).all()


def test_sample_paths_scales_by_whole_blocks():
    mc = np.ones((5, 2, 14))
    blocks = np.stack([np.full(14, 0.5), np.full(14, 2.0)])
    out = sample_paths(mc, blocks, np.random.default_rng(0))
    assert out.shape == mc.shape
    # each path-store row uses one block: all 14 days share the same factor here
    assert all(len(np.unique(out[i, j])) == 1 for i in range(5) for j in range(2))


def test_reliability_bins_count_everything():
    p = np.array([0.0, 0.1, 0.5, 0.9, 1.0])
    y = np.array([0, 0, 1, 1, 1])
    rows = reliability(p, y)
    assert sum(r["n"] for r in rows) == len(p)
    assert rows[-1]["observed_rate"] == 1.0
