# Daily Market Tracker

Daily Market Tracker 2.0 records opening gaps and current-price changes for
nine indicators, creates a daily Market Fingerprint, and presents the history
in Streamlit. It is an observation tool, not a market-prediction system. It is
a WillGaoLab open-source project.

Read the project [usage disclaimer](DISCLAIMER.md) before using, publishing,
or redistributing generated data or figures.

## Features

- Tracks nine indicators in three groups: Equities, Risk & Sentiment, and
  Macro.
- Collects Yahoo Finance daily close/open data for eight indicators and the
  00:00 UTC open plus current Bitcoin market price for `BTC-USD`.
- Maintains `data/history.csv` as the single source of truth.
- Generates daily Market Fingerprint PNGs and displays the latest data in
  Streamlit.

## Version 2.0

Version 2.0 expands the original six-indicator tracker with the Dow Jones
Industrial Average (`^DJI`), Gold Futures (`GC=F`), and Bitcoin (`BTC-USD`).

- Equities: S&P 500, Nasdaq-100 Futures, Dow Jones Industrial Average
- Risk & Sentiment: VIX, Bitcoin, Gold Futures
- Macro: U.S. 10-Year Treasury Yield, U.S. Dollar Index, WTI Crude Oil

Bitcoin trades continuously, so its observation uses the latest 00:00 UTC
daily open available when the script runs instead of a prior close. The
tracker stores `bitcoin_open`, `bitcoin_current`, `bitcoin_change`, and
`bitcoin_change_pct`, where the current price is Yahoo Finance's current market
price at collection time.

## Data and outputs

`data/history.csv` is the single source of truth. It has one row per U.S.
trading day and retains each non-Bitcoin instrument's previous Yahoo Finance
daily close, current daily open, absolute gap, and gap percentage. Bitcoin
instead retains the latest 00:00 UTC daily open available at collection time,
the current Yahoo Finance market price, absolute change, and change percentage.

The tracked Yahoo Finance symbols are `^GSPC`, `^DJI`, `NQ=F`, `^VIX`, `^TNX`,
`DX-Y.NYB`, `CL=F`, `GC=F`, and `BTC-USD`. Fingerprint PNGs in `figures/` are
generated only from the history file.

The migrated history preserves its original `2026-07-15` manual seed and
`2026-07-16` automated record. Later rows are collected automatically from
Yahoo Finance; Bitcoin's current-price values are observed at collection time.

Version 2.0 includes a one-time in-place schema migration. It preserves the
original records and leaves unrecoverable historical Bitcoin live-price fields
as `NA`; all newly appended automated records contain the complete schema.

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
python scripts/generate_fingerprint.py --date 2026-07-17
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

Yahoo Finance daily bars are used for all indicators. For Bitcoin, only the
latest daily bar's open is used; its comparison price is the provider's current
market price. A manual backfill therefore records the BTC daily open and
current price available when the backfill runs, not historical prices for the
requested date.

The local `demo/` folder preserves the original prototype and manual example;
it is intentionally excluded from GitHub.

## Attribution

Daily Market Tracker is created and maintained by William (Peidong) Gao under
[WillGaoLab](https://github.com/WillGaoLab), an independent research and
learning brand for open-source tools and scientific workflows.

- Project website: <https://williampeidonggao.com>
- WillGaoLab: <https://github.com/WillGaoLab>
- Personal GitHub: <https://github.com/PeidongGao>
