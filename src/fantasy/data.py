"""Download and cache nflverse weekly player stats and the game schedule (with Vegas lines)."""
from __future__ import annotations

from pathlib import Path
from urllib.request import urlretrieve

import numpy as np
import pandas as pd

BASE = "https://github.com/nflverse/nflverse-data/releases/download"
RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
SEASONS = range(2021, 2026)        # recent window used for the projection model
ALL_SEASONS = range(1999, 2026)    # everything nflverse has weekly player stats for
POSITIONS = ["QB", "RB", "WR", "TE"]
# nflverse has receptions but (almost) no targets for these seasons; treat targets as unknown, not zero.
NO_TARGETS = range(2003, 2009)
# Player stats label every season with today's franchise codes; the schedule uses the city at the time.
FRANCHISE = {"OAK": "LV", "SD": "LAC", "STL": "LA"}

PLAYER_COLS = [
    "player_id", "player_display_name", "position", "season", "week", "season_type", "team", "opponent_team",
    "attempts", "passing_yards", "passing_tds", "passing_interceptions",
    "carries", "rushing_yards", "rushing_tds",
    "targets", "receptions", "receiving_yards", "receiving_tds", "target_share", "air_yards_share",
    "sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost",
    "passing_2pt_conversions", "rushing_2pt_conversions", "receiving_2pt_conversions",
    "fantasy_points", "fantasy_points_ppr",
]


def _fetch(path: str) -> Path:
    """Download a file from the nflverse release once, then reuse the local copy."""
    dest = RAW / Path(path).name
    if not dest.exists():
        RAW.mkdir(parents=True, exist_ok=True)
        urlretrieve(f"{BASE}/{path}", dest)
    return dest


def load_player_weeks(seasons=SEASONS) -> pd.DataFrame:
    """Regular-season weekly stats for skill-position players (QB/RB/WR/TE)."""
    frames = [
        pd.read_csv(_fetch(f"stats_player/stats_player_week_{s}.csv"), usecols=PLAYER_COLS, low_memory=False)
        for s in seasons
    ]
    df = pd.concat(frames, ignore_index=True)
    df = df[(df.season_type == "REG") & df.position.isin(POSITIONS)].drop(columns="season_type")
    stat_cols = df.columns[df.columns.get_loc("attempts"):]
    df[stat_cols] = df[stat_cols].fillna(0)
    df.loc[df.season.isin(list(NO_TARGETS)), ["targets", "target_share", "air_yards_share"]] = np.nan
    df["half_ppr"] = df.fantasy_points + 0.5 * df.receptions
    df["touch_tds"] = df.rushing_tds + df.receiving_tds
    df["opportunities"] = df.carries + df.targets
    df["fumbles_lost"] = df.sack_fumbles_lost + df.rushing_fumbles_lost + df.receiving_fumbles_lost
    df["two_pt"] = df.passing_2pt_conversions + df.rushing_2pt_conversions + df.receiving_2pt_conversions
    return df.sort_values(["player_id", "season", "week"]).reset_index(drop=True)


def load_games(seasons=SEASONS) -> pd.DataFrame:
    """One row per team per regular-season game, with that team's Vegas implied point total.

    nflverse's ``spread_line`` is the home team's expected margin, so
    home implied = (total + spread) / 2 and away implied = (total - spread) / 2.
    """
    g = pd.read_csv(_fetch("schedules/games.csv"), low_memory=False)
    g = g[g.season.isin(list(seasons)) & (g.game_type == "REG")].copy()
    g[["home_team", "away_team"]] = g[["home_team", "away_team"]].replace(FRANCHISE)
    home = pd.DataFrame({
        "season": g.season, "week": g.week, "team": g.home_team, "opponent_team": g.away_team, "home": 1,
        "total_line": g.total_line, "spread": g.spread_line, "points": g.home_score,
    })
    away = pd.DataFrame({
        "season": g.season, "week": g.week, "team": g.away_team, "opponent_team": g.home_team, "home": 0,
        "total_line": g.total_line, "spread": -g.spread_line, "points": g.away_score,
    })
    out = pd.concat([home, away], ignore_index=True)
    out["implied_total"] = (out.total_line + out.spread) / 2
    return out.reset_index(drop=True)


def load_birth_dates() -> pd.DataFrame:
    """Player id -> birth date, from the nflverse players table."""
    p = pd.read_csv(_fetch("players/players.csv"), usecols=["gsis_id", "birth_date"], low_memory=False)
    p = p.dropna().rename(columns={"gsis_id": "player_id"})
    p["birth_date"] = pd.to_datetime(p.birth_date, errors="coerce")
    return p.dropna().drop_duplicates("player_id")
