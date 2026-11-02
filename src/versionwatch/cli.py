""" the cli.py file is the main orchestrator 
Command line entry point: fetch -> store -> report -> email."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from . import fetch, notify, report, store

ROOT = Path(__file__).resolve().parents[2]


def run(args: argparse.Namespace) -> int:
    today = dt.date.today()
    now = dt.datetime.now(dt.timezone.utc)
    products = fetch.load_products(ROOT / "config" / "products.toml")
    bronze_dir = ROOT / "data" / "bronze" / today.isoformat()
    bronze_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    failed: list[str] = []
    for p in products:
        slug, label, source = p["slug"], p["label"], p["source"]
        try:
            if source == "endoflife":
                payload = fetch.fetch_endoflife(slug)
                (bronze_dir / f"{slug}.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
                got = fetch.normalize_endoflife(slug, label, payload)
            elif source == "manual":
                got = fetch.load_manual(ROOT / "config" / "manual_releases.toml", slug, today)
            else:
                raise ValueError(f"unknown source '{source}'")
            rows += got
            print(f"[ok]   {label}: {len(got)} release lines")
        except Exception as exc:  # one broken source must not stop the whole run
            failed.append(f"{label} ({slug}): {exc}")
            print(f"[fail] {label}: {exc}", file=sys.stderr)

    if not rows:
        print("No data fetched, nothing to report.", file=sys.stderr)
        return 1

    conn = store.connect(args.db or ROOT / "data" / "versions.db")
    run_id = store.start_run(conn, now)
    store.insert_rows(conn, run_id, rows)

    ctx = report.build_context(conn, run_id, today, args.days, failed)
    md, html_body, subject = report.to_markdown(ctx), report.to_html(ctx), report.subject(ctx)

    out = Path(args.out) if args.out else ROOT / "reports"
    out.mkdir(parents=True, exist_ok=True)
    stem = f"report-{today.isoformat()}"
    (out / f"{stem}.md").write_text(md, encoding="utf-8")
    (out / f"{stem}.html").write_text(html_body, encoding="utf-8")
    print(f"Report written: {out / (stem + '.md')}")

    if args.no_email:
        print("Email skipped (--no-email).")
    elif notify.send_email(subject, md, html_body):
        print(f"Email sent to {notify.os.environ['MAIL_TO']}.")
    else:
        print("Email not configured (set SMTP_HOST, SMTP_USER, SMTP_PASSWORD, MAIL_TO); report saved only.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="versionwatch")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="fetch versions, store a snapshot, write and send the report")
    r.add_argument("--days", type=int, default=180, help="window for upcoming end-of-life (default 180)")
    r.add_argument("--db", help="SQLite file (default data/versions.db)")
    r.add_argument("--out", help="report folder (default reports/)")
    r.add_argument("--no-email", action="store_true", help="do not send the email")
    r.set_defaults(func=run)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
