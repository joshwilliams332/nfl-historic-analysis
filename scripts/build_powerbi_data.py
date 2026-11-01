"""Export the CSV files the Power BI report loads (powerbi/data/).

    python scripts/build_powerbi_data.py

Tables:
  player_seasons.csv      one row per player-season 1999-2026, with the same player's NEXT season attached
  seasons.csv, positions.csv   small lookup tables
  weekly_projections.csv  the latest week's projections (from scripts/project_week.py)
  backtest_2026.csv       weekly model vs. season average, 2026 weeks played so far
  wr_targets.csv, wr_games.csv, cb_games.csv, matchup_games.csv, teams.csv, sides.csv
                          WR vs. CB page (2025+): every WR target with its side of the field and an
                          estimated covering corner, NGS separation, and PFR coverage stats per corner
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from fantasy.data import CURRENT_SEASON, _fetch, load_games  # noqa: E402
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


MATCHUP_SEASONS = [2025, 2026]  # depth charts name left/right corners only from 2025 on
# pass_location is from the offense's view; the defense's right corner lines up across from the offense's left.
SIDE_CB = {"left": "RCB", "middle": "NB", "right": "LCB"}
SIDE_NAME = {"left": "Left", "middle": "Middle", "right": "Right"}


def corner_sides() -> pd.DataFrame:
    """Each team's listed starting LCB / RCB / nickel for each game, from the latest depth chart before kickoff."""
    g = load_games(MATCHUP_SEASONS)
    g = g[g.points.notna()][["season", "week", "team"]]
    sched = pd.read_csv(_fetch("schedules/games.csv"), usecols=["game_id", "season", "week", "game_type", "gameday",
                                                               "home_team", "away_team"])
    sched = sched[sched.season.isin(MATCHUP_SEASONS) & (sched.game_type == "REG")]
    games = pd.concat([sched.assign(team=sched.home_team), sched.assign(team=sched.away_team)])
    games = games.merge(g, on=["season", "week", "team"])[["game_id", "season", "week", "gameday", "team"]]
    games["gameday"] = pd.to_datetime(games.gameday)
    dc = pd.concat([pd.read_csv(_fetch(f"depth_charts/depth_charts_{s}.csv"), low_memory=False)
                    for s in MATCHUP_SEASONS])
    dc["date"] = pd.to_datetime(dc.dt.str[:10])
    dc = dc[dc.pos_abb.isin(list(SIDE_CB.values())) & (dc.pos_rank == 1)]
    snaps = dc[["team", "date"]].drop_duplicates().sort_values("date").rename(columns={"date": "snap"})
    games = pd.merge_asof(games.sort_values("gameday"), snaps, left_on="gameday", right_on="snap", by="team")
    out = games.merge(dc[["team", "date", "pos_abb", "gsis_id"]], left_on=["team", "snap"], right_on=["team", "date"])
    return out[["game_id", "team", "pos_abb", "gsis_id"]].drop_duplicates(["game_id", "team", "pos_abb"])


def matchups() -> dict[str, pd.DataFrame]:
    players = pd.read_csv(_fetch("players/players.csv"), usecols=["gsis_id", "pfr_id", "display_name", "position"],
                          low_memory=False)
    names = players.drop_duplicates("gsis_id").set_index("gsis_id").display_name
    sched = pd.read_csv(_fetch("schedules/games.csv"), usecols=["game_id", "season", "week", "game_type", "gameday",
                                                               "home_team", "away_team", "home_score"])
    sched = sched[sched.season.isin(MATCHUP_SEASONS) & (sched.game_type == "REG") & sched.home_score.notna()]
    games = sched.assign(label=sched.season.astype(str) + " Wk " + sched.week.astype(str).str.zfill(2) + ": "
                         + sched.away_team + " @ " + sched.home_team)[["game_id", "season", "week", "gameday", "label"]]

    cols = ["game_id", "season", "week", "season_type", "posteam", "defteam", "pass_location", "receiver_player_id",
            "air_yards", "complete_pass", "yards_gained", "pass_touchdown", "interception", "success", "epa",
            "two_point_attempt"]
    pbp = pd.concat([pd.read_csv(_fetch(f"pbp/play_by_play_{s}.csv.gz"), usecols=cols, low_memory=False)
                     for s in MATCHUP_SEASONS])
    wr_ids = set(players[players.position == "WR"].gsis_id)
    t = pbp[(pbp.season_type == "REG") & pbp.receiver_player_id.isin(wr_ids) & pbp.pass_location.notna()
            & (pbp.two_point_attempt != 1) & pbp.game_id.isin(games.game_id)].copy()
    sides = corner_sides()
    t["cb_slot"] = t.pass_location.map(SIDE_CB)
    t = t.merge(sides.rename(columns={"team": "defteam", "pos_abb": "cb_slot", "gsis_id": "est_cb_id"}),
                on=["game_id", "defteam", "cb_slot"], how="left")
    wr_targets = pd.DataFrame({
        "game_id": t.game_id, "offense": t.posteam, "defense": t.defteam,
        "receiver_id": t.receiver_player_id, "receiver": t.receiver_player_id.map(names),
        "side": t.pass_location.map(SIDE_NAME), "air_yards": t.air_yards, "complete": t.complete_pass.astype(int),
        "yards": np.where(t.complete_pass == 1, t.yards_gained, 0), "td": t.pass_touchdown.astype(int),
        "interception": t.interception.astype(int), "success": t.success, "epa": t.epa,
        "est_cb": t.est_cb_id.map(names).fillna("Not listed"), "est_cb_slot": t.cb_slot})

    ngs = pd.read_csv(_fetch("nextgen_stats/ngs_receiving.csv.gz"))
    ngs = ngs[ngs.season.isin(MATCHUP_SEASONS) & (ngs.week > 0) & (ngs.season_type == "REG")
              & (ngs.player_position == "WR")]
    long = pd.concat([sched.assign(team=sched.home_team, opponent=sched.away_team),
                      sched.assign(team=sched.away_team, opponent=sched.home_team)])[
        ["game_id", "season", "week", "team", "opponent"]]
    wr_games = ngs.merge(long, left_on=["season", "week", "team_abbr"], right_on=["season", "week", "team"])
    wr_games = wr_games[["game_id", "team", "opponent", "player_gsis_id", "player_display_name", "avg_separation",
                         "avg_cushion", "targets"]].rename(columns={"player_gsis_id": "receiver_id",
                                                                    "player_display_name": "receiver"})

    adv = pd.concat([pd.read_csv(_fetch(f"pfr_advstats/advstats_week_def_{s}.csv")) for s in MATCHUP_SEASONS])
    ids = players.dropna(subset=["pfr_id"]).drop_duplicates("pfr_id")
    adv = adv[(adv.game_type == "REG") & adv.game_id.isin(games.game_id)].merge(
        ids[["pfr_id", "gsis_id", "position"]], left_on="pfr_player_id", right_on="pfr_id")
    adv = adv[(adv.position == "CB") & (adv.def_targets > 0)]
    slot = sides.rename(columns={"team": "defense", "pos_abb": "slot"})
    cb = adv.rename(columns={"team": "defense", "opponent": "offense"}).merge(
        slot, on=["game_id", "defense", "gsis_id"], how="left")
    cb_games = pd.DataFrame({
        "game_id": cb.game_id, "defense": cb.defense, "offense": cb.offense, "cb_id": cb.gsis_id,
        "cb": cb.gsis_id.map(names).fillna(cb.pfr_player_name), "listed_as": cb.slot.fillna("Backup / not listed"),
        "side": cb.slot.map({v: SIDE_NAME[k] for k, v in SIDE_CB.items()}),
        "targets": cb.def_targets, "completions": cb.def_completions_allowed, "yards": cb.def_yards_allowed,
        "tds": cb.def_receiving_td_allowed, "ints": cb.def_ints, "rating": cb.def_passer_rating_allowed,
        "adot": cb.def_adot, "yac": cb.def_yards_after_catch})
    # PFR leaves yards / TDs / YAC blank when the corner allowed no catches; those are zeros.
    no_catch = cb_games.completions == 0
    cb_games.loc[no_catch, ["yards", "tds", "yac"]] = cb_games.loc[no_catch, ["yards", "tds", "yac"]].fillna(0)
    # One row per receiver, so target stats and NGS separation share an axis. Label = name + most frequent team.
    both = pd.concat([wr_targets[["receiver_id", "receiver", "offense"]],
                      wr_games.rename(columns={"team": "offense"})[["receiver_id", "receiver", "offense"]]])
    main_team = both.groupby("receiver_id").offense.agg(lambda x: x.value_counts().index[0])
    name = both.dropna(subset=["receiver"]).groupby("receiver_id").receiver.first()
    receivers = pd.DataFrame({"receiver_id": main_team.index})
    receivers["receiver"] = receivers.receiver_id.map(name)
    receivers["receiver_label"] = receivers.receiver + " (" + receivers.receiver_id.map(main_team) + ")"
    assert receivers.receiver_label.is_unique, "receiver labels must be unique"
    teams = pd.DataFrame({"team": sorted(set(sched.home_team) | set(sched.away_team))})
    side_tbl = pd.DataFrame({"side": ["Left", "Middle", "Right"], "sort_order": [1, 2, 3],
                             "facing": ["Offense's left: defense's RCB", "Middle: nickel back",
                                        "Offense's right: defense's LCB"]})
    return {"wr_targets": wr_targets, "wr_games": wr_games, "receivers": receivers, "cb_games": cb_games, "matchup_games": games,
            "teams": teams, "sides": side_tbl}


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
    for name, table in matchups().items():
        table.to_csv(OUT / f"{name}.csv", index=False, float_format="%.4f")
    for f in sorted(OUT.glob("*.csv")):
        print(f"{f.name}: {sum(1 for _ in open(f)) - 1:,} rows, {f.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
