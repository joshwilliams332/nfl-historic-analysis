"""Project PPR points for an upcoming week and write reports/projections/<season>_week<NN>.csv and .md.

    python scripts/project_week.py                 # next unplayed week of the current season
    python scripts/project_week.py --week 9

Current-season data is re-downloaded when more than a few hours old, so rerunning after Friday's
injury reports picks them up.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from fantasy.data import CURRENT_SEASON, load_games  # noqa: E402
from fantasy.features import model_sample  # noqa: E402
from fantasy.weekly import fit, prepare, project_week, weekly_frame  # noqa: E402

TOP = {"QB": 12, "RB": 24, "WR": 24, "TE": 12}


def next_week(season: int) -> int:
    g = load_games([season])
    return int(g[g.points.isna()].week.min())


def to_markdown(proj: pd.DataFrame, season: int, week: int) -> str:
    lines = [f"# {season} week {week} PPR projections", ""]
    tagged = (proj.injury != "").sum()
    lines.append(f"{len(proj)} players. Injury tags included: {tagged}." +
                 ("" if tagged else " (No injury report yet: rerun after Friday's reports.)"))
    if proj.no_line.any():
        lines.append("Games marked † had no Vegas line yet; the week's average team total was used.")
    for pos, n in TOP.items():
        lines += ["", f"## {pos}", "", "| # | Player | Team | Opp | Proj | Season avg | Last 3 | Tag |",
                  "|---:|---|---|---|---:|---:|---:|---|"]
        for _, r in proj[(proj.position == pos) & (proj.pos_rank <= n)].iterrows():
            opp = r.opponent_team + (" †" if r.no_line else "")
            lines.append(f"| {r.pos_rank} | {r.player_display_name} | {r.team} | {opp} | {r.projection:.1f} | "
                         f"{r.avg_season:.1f} | {r.avg_last3:.1f} | {r.injury} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=CURRENT_SEASON)
    ap.add_argument("--week", type=int)
    args = ap.parse_args()
    season = args.season
    week = args.week or next_week(season)

    df = weekly_frame(range(season - 6, season + 1), upcoming=(season, week))
    played = df[(df.season >= season - 5) & ~((df.season == season) & (df.week >= week))]
    model = fit(prepare(model_sample(played)))
    proj = project_week(df, model, season, week)

    out = ROOT / "reports" / "projections"
    out.mkdir(parents=True, exist_ok=True)
    proj.to_csv(out / f"{season}_week{week:02d}.csv", index=False)
    (out / f"{season}_week{week:02d}.md").write_text(to_markdown(proj, season, week))
    print(f"{season} week {week}: projected {len(proj)} players -> {out}/{season}_week{week:02d}.md")
    print(proj[proj.pos_rank <= 5][["position", "pos_rank", "player_display_name", "team", "opponent_team",
                                    "projection"]].to_string(index=False))


if __name__ == "__main__":
    main()
