"""Write the phone-friendly site's data (site/data/*.json) from the Power BI CSVs in powerbi/data/.

    python scripts/build_powerbi_data.py   # first, if the CSVs are stale
    python scripts/build_site_data.py

Each file is {"columns": [...], "rows": [[...], ...]} with numbers rounded, to keep downloads small on a phone.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "powerbi" / "data"
OUT = ROOT / "site" / "data"

TABLES = {
    "seasons": ("player_seasons.csv", {
        "player_label": None, "player": None, "position": None, "season": 0, "team": None, "age_years": 0,
        "games": 0, "ppg": 2, "touches_pg": 2, "targets_pg": 2, "td_pg": 3, "td_rate": 3, "snap_pct": 3,
        "carries": 0, "ppr_points": 1, "pos_rank": 0, "top150": 0, "has_next": 0, "next_ppg": 2, "next_games": 0,
        "next_pos_rank": 0, "ppg_change": 2, "proj_next_ppg": 2, "current_ppg": 2, "current_games": 0}),
    "week": ("weekly_projections.csv", {
        "season": 0, "week": 0, "position": None, "pos_rank": 0, "player": None, "team": None, "opponent": None,
        "projection": 1, "avg_season": 1, "avg_last3": 1, "snap_last3": 2, "implied_total": 1, "no_line": None,
        "injury": None}),
    "backtest": ("backtest_2026.csv", {"week": 0, "player_games": 0, "model_start_sit": 4,
                                       "season_avg_start_sit": 4, "model_mae": 2, "season_avg_mae": 2}),
    "games": ("matchup_games.csv", {"game_id": None, "season": 0, "week": 0, "label": None}),
    "receivers": ("receivers.csv", {"receiver_id": None, "receiver_label": None}),
    "targets": ("wr_targets.csv", {"game_id": None, "offense": None, "defense": None, "receiver_id": None,
                                   "side": None, "complete": 0, "yards": 0, "td": 0, "success": 0, "est_cb": None,
                                   "est_cb_slot": None}),
    "wr_games": ("wr_games.csv", {"game_id": None, "team": None, "opponent": None, "receiver_id": None,
                                  "avg_separation": 2, "targets": 0}),
    "cb_games": ("cb_games.csv", {"game_id": None, "defense": None, "offense": None, "cb": None, "listed_as": None,
                                  "side": None, "targets": 0, "completions": 0, "yards": 0, "tds": 0, "rating": 1}),
}


def clean(v, digits):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if digits is None:
        return v.item() if isinstance(v, np.generic) else v
    return int(round(v)) if digits == 0 else round(float(v), digits)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (csv, cols) in TABLES.items():
        df = pd.read_csv(SRC / csv, usecols=list(cols), keep_default_na=True)[list(cols)]
        df = df.astype(object).where(df.notna(), None)
        rows = [[clean(v, cols[c]) for c, v in zip(cols, row)] for row in df.itertuples(index=False)]
        path = OUT / f"{name}.json"
        path.write_text(json.dumps({"columns": list(cols), "rows": rows}, separators=(",", ":")))
        print(f"{path.name}: {len(rows):,} rows, {path.stat().st_size / 1e6:.2f} MB")
    meta = {"week_label": None}
    wk = pd.read_csv(SRC / "weekly_projections.csv", usecols=["season", "week"]).iloc[0]
    meta["week_label"] = f"{int(wk.season)} week {int(wk.week)}"
    (OUT / "meta.json").write_text(json.dumps(meta))


if __name__ == "__main__":
    main()
