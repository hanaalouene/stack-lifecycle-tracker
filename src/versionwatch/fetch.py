"""Ingestion layer (bronze): pull release data from the sources and normalise it."""

from __future__ import annotations

import datetime as dt
import json
import tomllib
import urllib.request
from pathlib import Path

EOL_API = "https://endoflife.date/api/v1/products/{slug}"
USER_AGENT = "tech-version-watch/1.0 (personal project)"


def load_products(path: Path) -> list[dict]:
    with open(path, "rb") as f:
        return tomllib.load(f)["product"]


def fetch_endoflife(slug: str, timeout: int = 30) -> dict:
    """Return the raw JSON payload of one product from endoflife.date."""
    req = urllib.request.Request(EOL_API.format(slug=slug), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def normalize_endoflife(slug: str, label: str, payload: dict) -> list[dict]:
    """Flatten one endoflife.date payload into one row per release cycle."""
    rows = []
    for rel in payload["result"]["releases"]:
        latest = rel.get("latest") or {}
        rows.append(
            {
                "product": slug,
                "label": label,
                "cycle": str(rel["name"]),
                "release_date": rel.get("releaseDate"),
                "latest_version": latest.get("name"),
                "latest_date": latest.get("date"),
                "is_lts": int(bool(rel.get("isLts"))),
                "eoas_from": rel.get("eoasFrom"),
                "eol_from": rel.get("eolFrom"),
                "is_eol": int(bool(rel.get("isEol"))),
                "is_maintained": int(bool(rel.get("isMaintained"))),
                "link": latest.get("link"),
                "source": "endoflife.date",
                "verified": 1,
            }
        )
    return rows


def load_manual(path: Path, slug: str, today: dt.date) -> list[dict]:
    """Read hand-maintained releases for one product (products the API does not cover)."""
    if not path.exists():
        return []
    with open(path, "rb") as f:
        entries = tomllib.load(f).get("release", [])
    rows = []
    for e in entries:
        if e["product"] != slug:
            continue
        eol = e.get("eol_from") or None
        is_eol = int(bool(eol) and eol <= today.isoformat())
        rows.append(
            {
                "product": slug,
                "label": e.get("label", slug),
                "cycle": str(e["cycle"]),
                "release_date": e.get("release_date") or None,
                "latest_version": e.get("latest_version") or None,
                "latest_date": None,
                "is_lts": 0,
                "eoas_from": None,
                "eol_from": eol,
                "is_eol": is_eol,
                "is_maintained": int(not is_eol),
                "link": e.get("link"),
                "source": "manual",
                "verified": int(bool(e.get("verified", False))),
            }
        )
    return rows
