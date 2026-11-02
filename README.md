# tech-version-watch

Monthly pipeline that tracks releases and end-of-life dates of the technologies you work with
(MuleSoft, Java, Spring Boot, Python, dbt, Airflow, Talend...) and emails you a report:
new versions, versions that reached end of life, upcoming end-of-life dates, changed dates.

100% free: Python standard library only (no pip install), SQLite, the public
[endoflife.date](https://endoflife.date/docs/api/v1/) API, SMTP for the email, GitHub Actions or
Windows Task Scheduler for the schedule.

## Architecture

```
config/products.toml ──► fetch.py ──► data/bronze/<date>/<product>.json   (raw API payloads)
config/manual_releases.toml ─┘             │
                                           ▼ normalise
                                  data/versions.db  (SQLite, silver: one append-only snapshot per run)
                                           │ SQL diff vs previous run (gold queries in store.py)
                                           ▼
                              report.py ──► reports/report-<date>.md + .html ──► notify.py (SMTP)
```

| Step | What happens |
|---|---|
| Extract | One HTTPS call per product to `endoflife.date/api/v1/products/<slug>`; raw JSON kept in `data/bronze/`. |
| Transform | One row per release line: latest version, release date, end of standard support, end of life. |
| Load | A new `run_id` snapshot is appended to SQLite, never overwritten. |
| Serve | SQL compares this run with the previous one: new lines, new latest versions, newly EOL, changed EOL dates, upcoming EOL. |
| Notify | HTML + Markdown report, sent by email when SMTP variables are set. |

## Run it

```powershell
cd C:\Users\DELL\tech-version-watch
python -m unittest discover -s tests      # 8 tests, offline
python run.py run --no-email              # fetch + report, no email
python run.py run                         # also sends the email if configured
python run.py run --days 365              # upcoming end-of-life window (default 180)
```

The first run only saves a baseline. Differences appear from the second run on.

## Choose your technologies

Edit `config/products.toml`. Slugs are listed at <https://endoflife.date/api/v1/products/>
(for example `mulesoft-runtime`, `oracle-jdk`, `eclipse-temurin`, `spring-boot`, `python`).
Talend is not in that API, so it is read from `config/manual_releases.toml`, which you maintain by
hand from the [official Qlik lifecycle page](https://help.qlik.com/talend/en-US/customer-support-statements/Cloud/product-end-of-life-planning).
The Talend values shipped here are **unverified** and are labelled "(unverified)" in the report until you set `verified = true`.

## Email (free)

Set these environment variables; nothing is stored in the code:

| Variable | Example |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASSWORD` | a Gmail **app password** (Google account > Security > 2-step verification > App passwords), not your normal password |
| `MAIL_TO` | where the report is sent |

## Schedule it (choose one)

**GitHub Actions (recommended, runs even when your PC is off).** Push this folder to a private GitHub repo,
add the five variables above as repository secrets (Settings > Secrets and variables > Actions), and the
workflow `.github/workflows/monthly-report.yml` runs on the 1st of each month at 06:00 UTC. It also commits
`data/` so the next month can compare against it. You can trigger it manually from the Actions tab.

**Windows Task Scheduler (runs on your PC).**
```powershell
New-Item -ItemType Directory -Force C:\Users\DELL\tech-version-watch\logs
schtasks /Create /SC MONTHLY /D 1 /ST 08:00 /TN "TechVersionWatch" /TR "powershell -NoProfile -File C:\Users\DELL\tech-version-watch\scripts\run_monthly.ps1"
```

## Ideas to extend it (good for your portfolio)

- Add a GitHub Releases source for tools that publish there (a second `fetch_*` function and `source = "github"`).
- Data-quality checks (no empty latest version, dates in ISO format) before loading.
- Replace SQLite with DuckDB or load into a free-tier cloud warehouse; add a small Streamlit or Power BI dashboard on the snapshots.
- Slack or Teams webhook notification next to the email.
- Alert only when an end-of-life date falls within 90 days, in a separate weekly job.
