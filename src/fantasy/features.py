"""Leakage-safe features for predicting a player's fantasy points in a given week.

Every feature for (player, season, week) uses only games played *before* that week:
rolling stats are shifted by one game, and defense / league numbers only count earlier weeks.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TARGET = "fantasy_points_ppr"

FEATURES = [
    "games_prior", "last_game", "avg_last3", "avg_season", "prior_season_avg",
    "opps_per_game", "targets_per_game", "carries_per_game", "target_share_avg",
    "tds_per_game", "def_factor", "implied_total", "implied_factor", "spread", "home",
]


def _player_history(df: pd.DataFrame) -> pd.DataFrame:
    """Rolling per-player features within a season, each shifted so week t only sees weeks < t."""
    g = df.groupby(["player_id", "season"], sort=False)
    prev = lambda col: g[col].shift(1)  # noqa: E731
    out = pd.DataFrame(index=df.index)
    out["games_prior"] = g.cumcount()
    out["last_game"] = prev(TARGET)
    out["avg_season"] = g[TARGET].transform(lambda s: s.shift(1).expanding().mean())
    out["avg_last3"] = g[TARGET].transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
    for col, name in [("opportunities", "opps_per_game"), ("targets", "targets_per_game"),
                      ("carries", "carries_per_game"), ("target_share", "target_share_avg"),
                      ("touch_tds", "tds_per_game")]:
        out[name] = g[col].transform(lambda s: s.shift(1).expanding().mean())
    return out


def _prior_season(df: pd.DataFrame) -> pd.Series:
    """The player's full previous-season PPR average (needs 4+ games), joined onto each row."""
    per = df.groupby(["player_id", "season"])[TARGET].agg(["mean", "size"]).reset_index()
    per = per[per["size"] >= 4]
    per["season"] += 1
    merged = df[["player_id", "season"]].merge(
        per[["player_id", "season", "mean"]], on=["player_id", "season"], how="left")
    return merged["mean"].set_axis(df.index)


def defense_vs_position(df: pd.DataFrame) -> pd.DataFrame:
    """How many PPR points each defense had allowed per game to each position before each week,
    as a ratio to the league average to that position over the same weeks (1.0 = average)."""
    allowed = (df.groupby(["season", "week", "opponent_team", "position"])[TARGET].sum()
               .rename("allowed").reset_index()
               .sort_values(["season", "opponent_team", "position", "week"]))
    g = allowed.groupby(["season", "opponent_team", "position"])
    allowed["def_allowed_pg"] = g["allowed"].transform(lambda s: s.shift(1).expanding().mean())

    # League average allowed per defense-game to the position, using only weeks before this one.
    wk = allowed.groupby(["season", "position", "week"])["allowed"].agg(["sum", "count"]).reset_index()
    wk = wk.sort_values(["season", "position", "week"])
    gw = wk.groupby(["season", "position"])
    wk["league_pg"] = gw["sum"].transform(lambda s: s.shift(1).cumsum()) / gw["count"].transform(
        lambda s: s.shift(1).cumsum())
    allowed = allowed.merge(wk[["season", "position", "week", "league_pg"]], on=["season", "position", "week"])
    allowed["def_factor"] = allowed.def_allowed_pg / allowed.league_pg
    return allowed[["season", "week", "opponent_team", "position", "def_allowed_pg", "league_pg", "def_factor"]]


def build_features(players: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """One row per player-game with the target and all pre-game features."""
    df = players.copy()
    df = df.join(_player_history(df))
    df["prior_season_avg"] = _prior_season(df)
    df = df.merge(defense_vs_position(df), on=["season", "week", "opponent_team", "position"], how="left")

    lines = games[["season", "week", "team", "home", "spread", "implied_total"]].copy()
    lines["implied_factor"] = lines.implied_total / lines.groupby(["season", "week"]).implied_total.transform("mean")
    df = df.merge(lines, on=["season", "week", "team"], how="left")
    return df


def model_sample(df: pd.DataFrame, min_games: int = 3, min_avg: float = 5.0) -> pd.DataFrame:
    """Rows a fantasy manager would actually face: 3+ earlier games this season and a
    season-to-date average of 5+ PPR (filters out backups who are rarely in a lineup)."""
    s = df[(df.games_prior >= min_games) & (df.avg_season >= min_avg)].copy()
    return s.dropna(subset=["def_factor", "implied_total"])


def mingus_projection(df: pd.DataFrame) -> pd.Series:
    """The Mingus site's Start/Sit heuristic, reproduced: average of season and last-3 PPG,
    times a matchup factor (clamped 0.8-1.2) and a Vegas implied-total factor (clamped 0.9-1.1)."""
    base = (df.avg_season + df.avg_last3) / 2
    return base * np.clip(df.def_factor, 0.8, 1.2) * np.clip(df.implied_factor, 0.9, 1.1)
