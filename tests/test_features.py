"""Features must only use games played before the week they describe."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantasy.evaluate import pairwise_accuracy  # noqa: E402
from fantasy.features import TARGET, build_features, defense_vs_position  # noqa: E402


def _toy():
    """Two WRs on team A facing teams B then C then B, and one WR on team D facing the same defenses."""
    rows = []
    for week, opp, pts_a1, pts_a2, pts_d in [(1, "B", 10, 4, 7), (2, "C", 20, 6, 9), (3, "B", 30, 8, 11)]:
        for pid, team, pts in [("a1", "A", pts_a1), ("a2", "A", pts_a2), ("d1", "D", pts_d)]:
            rows.append({"player_id": pid, "player_display_name": pid, "position": "WR", "season": 2024,
                         "week": week, "team": team, "opponent_team": opp if team == "A" else {"B": "C", "C": "B"}[opp],
                         "targets": 5, "carries": 0, "opportunities": 5, "target_share": 0.2, "touch_tds": 0,
                         TARGET: pts})
    games = pd.DataFrame([{"season": 2024, "week": w, "team": t, "home": 1, "spread": 0.0, "implied_total": 22.0}
                          for w in (1, 2, 3) for t in ("A", "D")])
    return pd.DataFrame(rows), games


def test_player_rolling_features_exclude_current_week():
    players, games = _toy()
    f = build_features(players, games).set_index(["player_id", "week"])
    assert np.isnan(f.loc[("a1", 1), "avg_season"])
    assert f.loc[("a1", 2), "avg_season"] == 10
    assert f.loc[("a1", 3), "avg_season"] == 15
    assert f.loc[("a1", 3), "last_game"] == 20
    assert f.loc[("a1", 3), "games_prior"] == 2


def test_defense_factor_uses_only_earlier_weeks():
    players, _ = _toy()
    d = defense_vs_position(players).set_index(["week", "opponent_team"])
    # Going into week 3, defense B had allowed 14 to team A's WRs (week 1) and 9 to team D's (week 2);
    # week 3's 38 points must not count.
    assert d.loc[(3, "B"), "def_allowed_pg"] == (14 + 9) / 2
    # League average over weeks 1-2: (14 + 7 + 26 + 9) / 4 defense-games.
    assert d.loc[(3, "B"), "league_pg"] == (14 + 7 + 26 + 9) / 4
    assert np.isnan(d.loc[(1, "B"), "def_factor"])


def test_pairwise_accuracy():
    df = pd.DataFrame({"season": 2024, "week": 1, "position": "WR",
                       "pred": [3.0, 2.0, 1.0], "actual": [30.0, 10.0, 20.0]})
    # Pairs: (3 vs 2) right, (3 vs 1) right, (2 vs 1) wrong.
    assert pairwise_accuracy(df, "pred", "actual") == 2 / 3
