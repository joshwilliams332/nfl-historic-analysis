"""Scoring a set of weekly projections the way a fantasy manager would care about them."""
from __future__ import annotations

import numpy as np
import pandas as pd


def start_sit_pairs(df: pd.DataFrame, pred: str, actual: str) -> pd.DataFrame:
    """Every pair of same-position players in the same week, as a start/sit decision:
    ``gap`` is how far apart the projections were, ``correct`` whether the higher projection scored more.
    Pairs with tied projections or tied actual points are left out."""
    gaps, hits = [], []
    for _, grp in df.groupby(["season", "week", "position"]):
        p, a = grp[pred].to_numpy(), grp[actual].to_numpy()
        dp = p[:, None] - p[None, :]
        da = a[:, None] - a[None, :]
        mask = np.triu(np.ones_like(dp, dtype=bool), 1) & (da != 0) & (dp != 0)
        gaps.append(np.abs(dp[mask]))
        hits.append(np.sign(dp[mask]) == np.sign(da[mask]))
    return pd.DataFrame({"gap": np.concatenate(gaps), "correct": np.concatenate(hits)})


def pairwise_accuracy(df: pd.DataFrame, pred: str, actual: str) -> float:
    """Start/sit accuracy: share of same-position, same-week pairs where the player projected
    higher actually scored more. 50% is a coin flip."""
    return float(start_sit_pairs(df, pred, actual).correct.mean())


def score_table(df: pd.DataFrame, preds: list[str], actual: str) -> pd.DataFrame:
    """MAE, RMSE, correlation and start/sit accuracy for each projection column."""
    rows = []
    for p in preds:
        err = df[p] - df[actual]
        rows.append({
            "projection": p,
            "MAE": err.abs().mean(),
            "RMSE": np.sqrt((err ** 2).mean()),
            "r": df[p].corr(df[actual]),
            "start/sit acc.": pairwise_accuracy(df, p, actual),
        })
    return pd.DataFrame(rows).set_index("projection").round(3)
