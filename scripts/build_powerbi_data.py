"""Export the CSV files the Power BI report loads (powerbi/data/).

    python scripts/build_powerbi_data.py

Tables:
  player_seasons.csv      one row per player-season 1999-2026, with the same player's NEXT season attached
  seasons.csv, positions.csv   small lookup tables
  weekly_projections.csv  the latest week's projections (from scripts/project_week.py)
  backtest_2026.csv       weekly model vs. season average, 2026 weeks played so far
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from fantasy.data import CURRENT_SEASON  # noqa: E402
from fantasy.evaluate import pairwise_accuracy  # noqa: E402
from fantasy.features import TARGET, model_sample  # noqa: E402
from fantasy.season import fit_season_model, predict, season_pairs, season_table  # noqa: E402
from fantasy.weekly import fit, prepare, weekly_frame  # noqa: E402

OUT = ROOT / "powerbi" / "data"
POS_ORDER = {"WR": 1, "RB": 2, "QB": 3, "TE": 4}  # same order (and colors) as the notebook charts
POS_NAME = {"QB": "Quarterback", "RB": "Running back", "WR": "Wide receiver", "TE": "Tight end"}


def player_seasons() -> pd.DataFrame:
    st = season_table(range(1999, CURRENT_SEASON + 1))
    st["ppr_points"] = st.ppg * st.games
    st["carries"] = st.carries_pg * st.games
    st["touches"] = st.touches_pg * st.games
    st["td_rate"] = np.where(st.touches > 0, st.tds / st.touches, np.nan)
    st["pos_rank"] = st.groupby(["season", "position"]).ppr_points.rank(ascending=False, method="first").astype(int)
    st["top150"] = (st.groupby("season").ppr_points.rank(ascending=False, method="first") <= 150).astype(int)

    nxt = st[["player_id", "season", "ppg", "games", "pos_rank"]].assign(season=st.season - 1).rename(
        columns={"ppg": "next_ppg", "games": "next_games", "pos_rank": "next_pos_rank"})
    st = st.merge(nxt, on=["player_id", "season"], how="left")
    # "Next season" only counts when it's a finished season and the player got real playing time.
    st["has_next"] = ((st.season + 1 < CURRENT_SEASON) & (st.next_games >= 4)).astype(int)
    for col in ["next_ppg", "next_games", "next_pos_rank"]:
        st.loc[st.has_next == 0, col] = np.nan
    st["ppg_change"] = st.next_ppg - st.ppg
    st["improved"] = np.where(st.has_next == 1, (st.ppg_change > 0).astype(float), np.nan)
    st["next_top12"] = np.where(st.has_next == 1, (st.next_pos_rank <= 12).astype(float), np.nan)
    st["next_top24"] = np.where(st.has_next == 1, (st.next_pos_rank <= 24).astype(float), np.nan)

    # Season-model projection for 2026 (from 2025), plus 2026 so far, on the 2025 rows.
    pairs = season_pairs(st[st.season < CURRENT_SEASON].drop(columns=[c for c in st.columns if c.startswith("next_")]))
    labeled = pairs[(pairs.games_next >= 4) & (pairs.season + 1 < CURRENT_SEASON)]
    model = fit_season_model(labeled)
    last = pairs[pairs.season == CURRENT_SEASON - 1].copy()
    last["proj_next_ppg"] = predict(model, last)
    st = st.merge(last[["player_id", "season", "proj_next_ppg"]], on=["player_id", "season"], how="left")
    now = st[st.season == CURRENT_SEASON][["player_id", "ppg", "games"]].rename(
        columns={"ppg": "current_ppg", "games": "current_games"}).assign(season=CURRENT_SEASON - 1)
    st = st.merge(now, on=["player_id", "season"], how="left")

    st_names = st.sort_values("season").groupby("player_id").name.last()
    st["key"] = st.player_id + "_" + st.season.astype(str)
    # Names aren't unique (two WRs named Mike Williams), so the player picker shows position and years.
    span = st.groupby("player_id").season.agg(["min", "max"])
    first_pos = st.sort_values("season").groupby("player_id").position.last()
    st["player_label"] = st.player_id.map(
        lambda pid: f"{st_names[pid]} ({first_pos[pid]}, {span.loc[pid, 'min']}-{span.loc[pid, 'max']})")
    st["age_years"] = np.floor(st.age).astype("Int64")
    st["is_complete"] = (st.season < CURRENT_SEASON).astype(int)
    cols = ["key", "player_id", "name", "player_label", "position", "season", "team", "age", "age_years", "games", "ppr_points", "ppg",
            "targets_pg", "carries_pg", "receptions_pg", "touches_pg", "tds", "td_pg", "td_rate", "attempts_pg",
            "target_share", "snap_pct", "carries", "pos_rank", "top150", "is_complete", "has_next", "next_ppg",
            "next_games", "next_pos_rank", "ppg_change", "improved", "next_top12", "next_top24", "proj_next_ppg",
            "current_ppg", "current_games"]
    out = st[cols].rename(columns={"name": "player"})
    assert out.groupby("player_label").player_id.nunique().max() == 1, "player labels must be unique"
    return out.sort_values(["season", "position", "pos_rank"]).reset_index(drop=True)


def backtest_and_projections() -> tuple[pd.DataFrame, pd.DataFrame]:
    proj_files = sorted((ROOT / "reports" / "projections").glob(f"{CURRENT_SEASON}_week*.csv"))
    proj = pd.read_csv(proj_files[-1])
    week = int(proj_files[-1].stem.split("week")[1])
    proj.insert(0, "week", week)
    proj.insert(0, "season", CURRENT_SEASON)
    proj = proj.rename(columns={"player_display_name": "player", "opponent_team": "opponent"})

    df = weekly_frame(range(CURRENT_SEASON - 6, CURRENT_SEASON + 1))
    played = prepare(model_sample(df[df.season >= CURRENT_SEASON - 5]))
    model = fit(played[played.season < CURRENT_SEASON])
    cur = played[(played.season == CURRENT_SEASON) & (played.week < week)].copy()
    cur["model"] = model.predict(cur[list(model[0].feature_names_in_)])
    rows = []
    for w, d in cur.groupby("week"):
        rows.append({"season": CURRENT_SEASON, "week": w, "player_games": len(d),
                     "model_start_sit": pairwise_accuracy(d, "model", TARGET),
                     "season_avg_start_sit": pairwise_accuracy(d, "avg_season", TARGET),
                     "model_mae": (d.model - d[TARGET]).abs().mean(),
                     "season_avg_mae": (d.avg_season - d[TARGET]).abs().mean()})
    return proj, pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ps = player_seasons()
    ps.to_csv(OUT / "player_seasons.csv", index=False, float_format="%.4f")
    seasons = pd.DataFrame({"season": range(1999, CURRENT_SEASON + 1)})
    seasons["era"] = pd.cut(seasons.season, [1998, 2005, 2011, 2017, 2100],
                            labels=["1999-2005", "2006-2011", "2012-2017", "2018-now"]).astype(str)
    seasons["is_complete"] = (seasons.season < CURRENT_SEASON).astype(int)
    seasons.to_csv(OUT / "seasons.csv", index=False)
    pd.DataFrame({"position": list(POS_ORDER), "sort_order": list(POS_ORDER.values()),
                  "position_name": [POS_NAME[p] for p in POS_ORDER]}).to_csv(OUT / "positions.csv", index=False)
    proj, back = backtest_and_projections()
    proj.to_csv(OUT / "weekly_projections.csv", index=False, float_format="%.3f")
    back.to_csv(OUT / "backtest_2026.csv", index=False, float_format="%.4f")
    for f in sorted(OUT.glob("*.csv")):
        print(f"{f.name}: {sum(1 for _ in open(f)) - 1:,} rows, {f.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
