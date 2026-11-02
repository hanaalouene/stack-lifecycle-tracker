# tech-version-watch

Monthly pipeline that tracks releases and end-of-life (EOL) dates of the technologies you work with
(MuleSoft, Java, Spring Boot, Python, dbt, Airflow, Talend...) and emails you a report with a
criticality level for every end-of-life date.

100% free: Python standard library only (no `pip install`), SQLite, the public
[endoflife.date](https://endoflife.date/docs/api/v1/) API, SMTP for the email, and GitHub Actions or
Windows Task Scheduler for the schedule.

## Features

### Data Ingestion
- The task is scheduled to run once a month, on the 1st at 06:00 UTC, using GitHub Actions (cron) or Windows Task Scheduler.
- One API request per product is made to `endoflife.date` to gather release data in JSON format.
- The raw JSON is kept untouched in `data/bronze/<date>/<product>.json`.
- The JSON is cleaned and normalised into one row per release line (for example Java 21, Mule 4.9-lts) and saved into the SQLite database `data/versions.db`.
- Products the API does not cover (Talend) are read from `config/manual_releases.toml` and labelled "(unverified)" until you confirm them.
- A failing source never stops the run: it is listed in the report under "Sources that failed".

This process ensures that every month's data is kept, so any month can be compared with any earlier month.

### Data Analysis
- Each run is compared with the previous one using SQL queries in `store.py` (the gold queries):
  - new release lines
  - new latest versions (previous -> new)
  - newly end-of-life
  - changed end-of-life dates
  - upcoming end of life (next 180 days)
  - recently reached end of life (last 60 days)
  - currently supported versions
- Each end-of-life date gets a **criticality level**, based on the time left:

| Level | Rule |
|---|---|
| Critical | EOL in 30 days or less, or already EOL |
| High | 31 to 90 days |
| Medium | 91 to 180 days |
| Low | more than 180 days |
| No date | EOL date not announced |

- The first run only saves a baseline. Differences appear from the second run on.

### Report and Email
- A report is written to `reports/report-<date>.html` and `reports/report-<date>.md`.
- The HTML report shows the KPI tiles (Already EOL, Critical, High, Medium) and one table per section, with a coloured criticality badge on every end-of-life date.
- When the HTML file is opened in a browser, a **filter bar** lets you show only Critical, High, Medium... rows. Mail clients block scripts, so the email shows all rows.
- The report is sent by email (HTML + Markdown) when the SMTP variables are set. If they are not, the report is only saved on disk.


<img width="1190" height="799" alt="image" src="https://github.com/user-attachments/assets/d2e7d075-38df-4e53-8a4e-1a814f9ef08f" />


## Architecture

The project follows a **medallion architecture** (bronze, silver, gold):

```
config/products.toml ──► fetch.py ──► BRONZE  data/bronze/<date>/<product>.json
config/manual_releases.toml ─┘                (raw API responses, unmodified, replayable)
                                         │ normalise
                                         ▼
                                      SILVER  data/versions.db  table snapshots
                                              (cleaned, typed, one append-only row per product, release line and run)
                                         │ SQL diff vs previous run
                                         ▼
                                      GOLD    gold queries in store.py
                                              (business views used by the report)
                                         │
                                         ▼
                        report.py ──► reports/report-<date>.md + .html ──► notify.py (SMTP)
```

| Layer | Technology | Content |
|---|---|---|
| Bronze | JSON files in `data/bronze/<date>/` | Raw, unmodified API responses. |
| Silver | SQLite table `snapshots` | One row per product, release line and run. Nothing is updated or deleted, so history is kept. |
| Gold | SQL queries in `store.py` | New versions, newly EOL, changed EOL dates, upcoming EOL, supported versions. |

| Step | What happens |
|---|---|
| Extract | One HTTPS call per product to `endoflife.date/api/v1/products/<slug>`. |
| Transform | One row per release line: latest version, release date, end of standard support, end of life. |
| Load | A new `run_id` snapshot is appended to SQLite, never overwritten. |
| Serve | SQL compares this run with the previous one. |
| Notify | HTML + Markdown report, sent by email when configured. |

More detail (data model, data dictionary, business rules) is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Configuration

### Technologies
Edit `config/products.toml`. Slugs are listed at <https://endoflife.date/api/v1/products/>
(for example `mulesoft-runtime`, `oracle-jdk`, `eclipse-temurin`, `spring-boot`, `python`).

Talend is not in that API, so it is read from `config/manual_releases.toml`, which you maintain by hand from the
[official Qlik lifecycle page](https://help.qlik.com/talend/en-US/customer-support-statements/Cloud/product-end-of-life-planning).
The Talend values shipped here are **unverified** until you set `verified = true`.

### Email
Set these environment variables. Nothing is stored in the code.

| Variable | Example |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASSWORD` | a Gmail **app password**, not your normal password |
| `MAIL_TO` | where the report is sent |
| `MAIL_FROM` | optional, defaults to `SMTP_USER` |

On GitHub, add the first five as repository secrets (Settings > Secrets and variables > Actions).

## Folder Structure

```
📁|- config     : products.toml (technologies to track), manual_releases.toml (hand-maintained data, e.g. Talend)
📁|- data       : bronze/ (raw JSON per day) and versions.db (SQLite history, committed on purpose)
📁|- docs       : ARCHITECTURE.md (data model, functional and technical architecture)
📁|- reports    : generated report-<date>.html and .md
📁|- scripts    : run_monthly.ps1 (local run for Windows Task Scheduler)
📁|- src
   📁|- versionwatch
      🐍.cli.py     : orchestrates fetch -> store -> report -> email
      🐍.fetch.py   : calls the API, normalises the data, reads the manual file
      🐍.store.py   : SQLite schema, loading, and the gold SQL queries
      🐍.report.py  : builds the Markdown and HTML reports (criticality levels, filter)
      🐍.notify.py  : sends the email over SMTP
📁|- tests      : test_store.py (8 offline tests)
📁|- .github/workflows : monthly-report.yml (monthly schedule on GitHub Actions)
🐍.run.py : launcher, used by the schedule and by you
```

## Setup

1. Install Python 3.11 or newer (the project uses `tomllib`). There is nothing else to install: no `requirements.txt` is needed.
2. Run the tests:

```powershell
python -m unittest discover -s tests
```

3. Run the pipeline:

```powershell
python run.py run --no-email      # fetch + report, no email
python run.py run                 # also sends the email if configured
python run.py run --days 365      # upcoming end-of-life window (default 180)
```

4. Schedule it, either with GitHub Actions (push to a private repo and add the secrets) or with Windows Task Scheduler:

```powershell
New-Item -ItemType Directory -Force logs
schtasks /Create /SC MONTHLY /D 1 /ST 08:00 /TN "TechVersionWatch" /TR "powershell -NoProfile -File <project path>\scripts\run_monthly.ps1"
```

- `run.py` is the launcher that starts the whole pipeline.
- `cli.py` is the module that ingests, stores, reports and sends the email.

