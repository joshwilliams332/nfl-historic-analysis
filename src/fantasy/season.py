"""Season-long projections: next season's PPR per game from this season, for draft prep."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .data import POSITIONS, load_birth_dates, load_player_weeks, load_snap_counts
from .features import TARGET

VOLUME = ["games", "targets_pg", "carries_pg", "touches_pg", "td_pg", "target_share", "snap_pct", "attempts_pg"]
# Age enters per position (centered at 27, plus a squared term) so each position gets its own curve.
AGE = [f"{p}_{k}" for p in POSITIONS for k in ("age", "age2", "is")]
SEASON_FEATURES = ["ppg", "ppg_prev", "has_prev"] + VOLUME + AGE


def season_table(seasons) -> pd.DataFrame:
    """One row per player-season: per-game production, volume, snap share, and age on Sept. 1."""
    seasons = list(seasons)
    p = load_player_weeks(seasons).merge(load_snap_counts([s for s in seasons if s >= 2012]),
                                         on=["player_id", "season", "week"], how="left")
    st = p.groupby(["player_id", "season"]).agg(
        name=("player_display_name", "last"), position=("position", "last"), team=("team", "last"),
        games=(TARGET, "size"), ppg=(TARGET, "mean"), targets_pg=("targets", "mean"),
        carries_pg=("carries", "mean"), receptions_pg=("receptions", "mean"), tds=("touch_tds", "sum"),
        target_share=("target_share", "mean"), snap_pct=("snap_pct", "mean"), attempts_pg=("attempts", "mean"),
    ).reset_index()
    st["touches_pg"] = st.carries_pg + st.receptions_pg
    st["td_pg"] = st.tds / st.games
    st = st.merge(load_birth_dates(), on="player_id", how="left")
    st["age"] = (pd.to_datetime(st.season.astype(str) + "-09-01") - st.birth_date).dt.days / 365.25
    return st.drop(columns="birth_date")


def season_pairs(st: pd.DataFrame, min_games: int = 6, min_ppg: float = 5.0) -> pd.DataFrame:
    """Each qualifying season with features, plus the same player's next season (``ppg_next``) when it exists."""
    prev = st[["player_id", "season", "ppg"]].assign(season=st.season + 1).rename(columns={"ppg": "ppg_prev"})
    nxt = st[["player_id", "season", "ppg", "games"]].assign(season=st.season - 1).rename(
        columns={"ppg": "ppg_next", "games": "games_next"})
    d = st.merge(prev, on=["player_id", "season"], how="left").merge(nxt, on=["player_id", "season"], how="left")
    d = d[(d.games >= min_games) & (d.ppg >= min_ppg)].copy()
    d["has_prev"] = d.ppg_prev.notna().astype(int)
    d["ppg_prev"] = d.ppg_prev.fillna(d.ppg)
    age = d.age.fillna(d.age.median()) - 27
    for pos in POSITIONS:
        is_pos = (d.position == pos).astype(float)
        d[f"{pos}_age"], d[f"{pos}_age2"], d[f"{pos}_is"] = is_pos * age, is_pos * age ** 2, is_pos
    return d


def fit_season_model(train: pd.DataFrame):
    model = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 20)))
    return model.fit(train[SEASON_FEATURES].fillna(0), train.ppg_next)


def predict(model, d: pd.DataFrame) -> np.ndarray:
    return model.predict(d[SEASON_FEATURES].fillna(0))
