# Daily Market Tracker

Daily Market Tracker records opening gaps for six indicators, creates a daily
Market Fingerprint, and presents the history in Streamlit. It is an observation
tool, not a market-prediction system. It is a WillGaoLab open-source project.

Read the project [usage disclaimer](DISCLAIMER.md) before using, publishing,
or redistributing generated data or figures.

## Features

- Collects Yahoo Finance daily close/open data for six market indicators.
- Maintains `data/history.csv` as the single source of truth.
- Generates daily Market Fingerprint PNGs and displays the latest data in
  Streamlit.

## Data and outputs

`data/history.csv` is the single source of truth. It has one row per U.S.
trading day and retains each instrument's previous Yahoo Finance daily close,
current daily open, absolute gap, and gap percentage.

The tracked Yahoo Finance symbols are `^GSPC`, `NQ=F`, `^VIX`, `^TNX`,
`DX-Y.NYB`, and `CL=F`. Fingerprint PNGs in `figures/` are generated only from
the history file.

The initial `2026-07-15` row was manually collected from the prototype's
Yahoo Finance snapshot and is retained as a documented seed. All later rows
are collected automatically from Yahoo Finance daily bars.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Repository Structure

```text
Daily_Market_Tracker/
├── app.py                       # Streamlit dashboard
├── data/history.csv             # Single source of truth
├── figures/                     # Generated Market Fingerprints
├── scripts/                     # Fetching, validation, and rendering pipeline
├── .github/workflows/           # Daily GitHub Actions workflow
├── README.md
├── DISCLAIMER.md
└── requirements.txt
```

Fetch a current-day preview without modifying history:

```bash
python scripts/fetch_data.py
```

Run the complete idempotent pipeline:

```bash
python scripts/daily_pipeline.py
```

Backfill one missing U.S. trading day without altering existing records:

```bash
python scripts/daily_pipeline.py --date YYYY-MM-DD
```

Generate a fingerprint for an existing history date:

```bash
python scripts/generate_fingerprint.py --date 2026-07-15
```

Launch the dashboard:

```bash
streamlit run app.py
```

## Automation and deployment

`.github/workflows/daily_market.yml` runs on weekdays at 22:15 UTC, which is
after the U.S. cash close in both Eastern Standard and Daylight Time. Python
uses `America/New_York`, skips weekends, and treats a missing same-day S&P 500
bar on an expected trading day as a failure. Regular NYSE holidays are listed
in the code without an external calendar dependency; rare unplanned closures
also fail visibly. If the date is already in `data/history.csv`, it makes no
changes. Manual GitHub Actions runs accept an optional date for backfills.

For Streamlit Cloud, deploy this repository with `app.py` as the entry point;
the service installs `requirements.txt` automatically. The hosted dashboard
uses Google Analytics 4 and Microsoft Clarity to process usage and technical
analytics data under their respective terms and privacy policies.

## GitHub publishing checklist

Before the first push, initialize this directory as a Git repository (or clone
the intended repository into this location), add the GitHub remote, and review
the staged files. Do not commit `.venv/`, `.matplotlib/`, `__pycache__/`, the
local `demo/` prototype, or local Streamlit secrets; they are covered by
`.gitignore`.

After pushing the default branch, confirm that GitHub Actions is enabled and
that the repository or organization permits the workflow's `contents: write`
permission. The scheduled workflow commits only `data/history.csv` and
`figures/` when a new valid record is created. Use **Run workflow** with an
optional ISO date to backfill a missing trading day.

## License

This repository is released under the [MIT License](LICENSE). The license
applies only to the project's source code and documentation; it does not grant
rights to Yahoo Finance or exchange-provided data.

## Notes

Yahoo Finance daily bars are used consistently for all instruments.

The local `demo/` folder preserves the original prototype and manual example;
it is intentionally excluded from GitHub.

## Attribution

Daily Market Tracker is created and maintained by William (Peidong) Gao under
[WillGaoLab](https://github.com/WillGaoLab), an independent research and
learning brand for open-source tools and scientific workflows.

- Project website: <https://williampeidonggao.com>
- WillGaoLab: <https://github.com/WillGaoLab>
- Personal GitHub: <https://github.com/PeidongGao>
