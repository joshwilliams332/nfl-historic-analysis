"""The weekly projection model: train it, backtest it, and project a week that hasn't been played."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import make_column_transformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .data import load_games, load_injuries, load_player_weeks, load_snap_counts
from .features import (FEATURES, INJURY_FEATURES, SNAP_FEATURES, TARGET, add_injury_features,
                       add_snap_features, build_features, model_sample, upcoming_rows)

BASE = [f for f in FEATURES if f != "prior_season_avg"] + ["prior_fill", "has_prior"]
FULL = BASE + SNAP_FEATURES + INJURY_FEATURES


def weekly_frame(seasons, upcoming: tuple[int, int] | None = None) -> pd.DataFrame:
    """Features for every player-game in ``seasons`` (snap counts and injury reports included).
    ``upcoming=(season, week)`` adds placeholder rows for a week not yet played."""
    seasons = list(seasons)
    players, games = load_player_weeks(seasons), load_games(seasons)
    if upcoming:
        players = pd.concat([players, upcoming_rows(players, games, *upcoming)], ignore_index=True)
        players = players.sort_values(["player_id", "season", "week"]).reset_index(drop=True)
    df = build_features(players, games)
    df = add_snap_features(df, load_snap_counts([s for s in seasons if s >= 2013]))
    return add_injury_features(df, load_injuries(seasons))


def prepare(sample: pd.DataFrame) -> pd.DataFrame:
    """Rookies and players new to the sample have no prior season: use this season's average and flag it."""
    return sample.assign(has_prior=sample.prior_season_avg.notna().astype(int),
                         prior_fill=sample.prior_season_avg.fillna(sample.avg_season))


def make_model(num=FULL):
    pre = make_column_transformer(
        (make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), num),
        (OneHotEncoder(handle_unknown="ignore"), ["position"]))
    return make_pipeline(pre, RidgeCV(alphas=np.logspace(-2, 3, 20)))


def fit(train: pd.DataFrame, num=FULL):
    return make_model(num).fit(train[num + ["position"]], train[TARGET])


def project_week(df: pd.DataFrame, model, season: int, week: int, num=FULL) -> pd.DataFrame:
    """Projections for one week from a frame built with ``upcoming=(season, week)``.

    Games without a Vegas line yet get that week's average implied total (flagged in ``no_line``)."""
    wk = df[(df.season == season) & (df.week == week)].copy()
    wk["no_line"] = wk.implied_total.isna()
    mean_total = wk.drop_duplicates("team").implied_total.mean()
    wk["implied_total"] = wk.implied_total.fillna(mean_total)
    wk["implied_factor"] = wk.implied_factor.fillna(1.0)
    wk["spread"] = wk.spread.fillna(0.0)
    wk["home"] = wk.home.fillna(0.5)
    wk = prepare(model_sample(wk))
    wk["projection"] = model.predict(wk[num + ["position"]])
    wk["pos_rank"] = wk.groupby("position").projection.rank(ascending=False, method="first").astype(int)
    status = np.select([wk.doubtful == 1, wk.questionable == 1], ["Doubtful", "Questionable"], "")
    wk["injury"] = status
    cols = ["position", "pos_rank", "player_display_name", "team", "opponent_team", "projection", "avg_season",
            "avg_last3", "snap_last3", "def_factor", "implied_total", "no_line", "injury"]
    return wk[cols].sort_values(["position", "pos_rank"]).reset_index(drop=True)
