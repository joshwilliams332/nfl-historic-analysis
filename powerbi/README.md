# NFL Fantasy: Power BI report

An interactive companion to the notebooks: pick buttons and drag sliders to see how a player's season tends to carry
into the next one. Built as a **Power BI Project** (`.pbip`): the data model, measures, and report pages are plain
text files, so they live in git next to the Python.

| Page | What you can do |
|---|---|
| **Past → Future** | Pick a position and a this-season stat (PPG, touches, targets, TDs, TD rate, snap share, age). A scatter plots every player-season against the same player's PPG the next year; cards show the correlation, how strong it is, and r². A line shows whether the link held up across eras. |
| **Find Similar Players** | Drag sliders for age, PPG, touches, TDs and games to describe a season. Cards show how all matching player-seasons since 1999 did the next year (% improved, average change, % top-12 at the position), with the matching seasons listed, plus the 2025 players who fit that profile and their 2026 projection. |
| **27 Seasons** | Position share of top-150 fantasy points, 300-carry running backs per season, and aging curves by position, filtered by position buttons and a season slider. |
| **Player Explorer** | Search any player since 1999: PPG by season against the top-24 average at their position, career numbers, and the 2026 projection. |
| **This Week** | The latest weekly projections by position, with the model's 2026 start/sit track record. |

## Open it

1. Install **Power BI Desktop** (free, Windows only: Microsoft Store).
2. Get this repo onto your computer (`git clone`, or **Code → Download ZIP** on GitHub) and open
   `powerbi/NFL Fantasy.pbip`.
3. If Desktop says it can't open the project format, turn on these and restart: **File → Options and settings →
   Options → Preview features** → *Power BI Project (.pbip) save option*, *Store semantic model using TMDL format*,
   *Store reports using enhanced metadata format (PBIR)*. (On recent versions they may already be on.)
4. Click **Refresh**. The data loads from this repo on GitHub. The first time, Desktop asks how to connect to
   `raw.githubusercontent.com`: choose **Anonymous → Connect**. If it asks about privacy levels, choose **Public**.

**Offline / your own copy of the data:** **Transform data → Edit parameters → DataSource**, and set it to the data folder
with a trailing backslash, e.g. `C:\Users\joshw\OneDrive\Desktop\nfl-historic-analysis\powerbi\data\`. Then Refresh.

## Check that it loaded right

With nothing selected, you should see:

* **Past → Future**, stat = PPG: **r = 0.76**, "Strong link". Choose **RB** and **Touches/G**: r ≈ 0.70.
  **TD rate** for RB: r ≈ -0.02, "Almost no link".
* **Find Similar Players**: **9,159** matching seasons, **47%** improved next year, average change **-0.1** PPG,
  **13%** top-12 next year.
* **27 Seasons**: wide receivers at about **48%** of top-150 points in 1999 and **33%** in 2025.

If the numbers differ, the data didn't refresh fully: check **Transform data** for errors in the queries.

## Update the data

```bash
python scripts/project_week.py         # this week's projections
python scripts/build_powerbi_data.py   # rebuild powerbi/data/*.csv
```

Commit and push the CSVs, then **Refresh** in Power BI.

## How it's built

* `NFL Fantasy.SemanticModel/`: tables (`player_seasons.csv` with each player's *next* season attached, lookup tables
  for seasons and positions, weekly projections, the 2026 backtest), relationships, and the DAX measures. The
  correlation card is computed in DAX over whatever the slicers leave in view; the stat buttons are a disconnected
  `Past Stat` table read by a `SWITCH` measure.
* `NFL Fantasy.Report/`: the five pages, one `visual.json` per visual. Every report file validates against Microsoft's
  published PBIR schemas.
* Colors follow the notebooks: WR blue, RB orange, QB aqua, TE violet.
* The report was written as files rather than built by clicking in Power BI Desktop, so its first open is its first
  real test. If a visual looks off, a screenshot is enough to fix it.
