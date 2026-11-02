"""Reporting layer: turn the gold queries into a Markdown and an HTML report."""

from __future__ import annotations

import datetime as dt
import html

from . import store


def build_context(conn, run_id: int, today: dt.date, upcoming_days: int, failed: list[str]) -> dict:
    prev = store.previous_run_id(conn, run_id)
    ctx = {
        "today": today.isoformat(),
        "upcoming_days": upcoming_days,
        "baseline": prev is None,
        "failed": failed,
        "new_cycles": [],
        "new_latest": [],
        "eol_changes": [],
        "newly_eol": [],
    }
    if prev is not None:
        ctx["new_cycles"] = store.new_cycles(conn, run_id, prev)
        ctx["new_latest"] = store.new_latest_versions(conn, run_id, prev)
        ctx["eol_changes"] = store.eol_date_changes(conn, run_id, prev)
        ctx["newly_eol"] = store.newly_eol(conn, run_id, prev)
    ctx["upcoming"] = store.upcoming_eol(conn, run_id, today, upcoming_days)
    ctx["recent_eol"] = store.recently_eol(conn, run_id, today)
    ctx["supported"] = store.supported_now(conn, run_id)
    return ctx


def _v(row: dict) -> str:
    return "" if row.get("verified", 1) else " (unverified)"


def subject(ctx: dict) -> str:
    n_new = len(ctx["new_cycles"]) + len(ctx["new_latest"])
    return (
        f"Tech version watch {ctx['today'][:7]}: {n_new} new version(s), "
        f"{len(ctx['upcoming'])} end-of-life in {ctx['upcoming_days']} days"
    )


def _sections(ctx: dict) -> list[tuple[str, list[str], list[list[str]], str]]:
    """Each section: (title, headers, rows, empty message)."""
    s = []
    if ctx["baseline"]:
        s.append(("First run", ["Info"], [["Baseline snapshot saved. Changes will be shown from the next run."]], ""))
    else:
        s.append((
            "New release lines",
            ["Product", "Version line", "Latest version", "Released"],
            [[r["label"], r["cycle"], r["latest_version"] or "-", r["release_date"] or "-"] for r in ctx["new_cycles"]],
            "No new release line since the last report.",
        ))
        s.append((
            "New versions (patch / minor)",
            ["Product", "Version line", "Previous", "New", "Date"],
            [[r["label"], r["cycle"], r["old_version"] or "-", (r["new_version"] or "-") + _v(r), r["latest_date"] or "-"]
             for r in ctx["new_latest"]],
            "No new version since the last report.",
        ))
        s.append((
            "Newly end-of-life",
            ["Product", "Version line", "End of life", "Last version"],
            [[r["label"], r["cycle"], r["eol_from"] or "-", r["latest_version"] or "-"] for r in ctx["newly_eol"]],
            "Nothing reached end of life since the last report.",
        ))
        s.append((
            "Changed end-of-life dates",
            ["Product", "Version line", "Old date", "New date"],
            [[r["label"], r["cycle"], r["old_eol"] or "none", r["new_eol"] or "none"] for r in ctx["eol_changes"]],
            "No end-of-life date changed.",
        ))
    s.append((
        f"Upcoming end of life (next {ctx['upcoming_days']} days)",
        ["Product", "Version line", "Latest version", "End of standard support", "End of life"],
        [[r["label"], r["cycle"], r["latest_version"] or "-", r["eoas_from"] or "-", (r["eol_from"] or "-") + _v(r)]
         for r in ctx["upcoming"]],
        "No supported version reaches end of life in this window.",
    ))
    s.append((
        "Recently reached end of life (last 60 days)",
        ["Product", "Version line", "End of life", "Last version"],
        [[r["label"], r["cycle"], (r["eol_from"] or "-") + _v(r), r["latest_version"] or "-"] for r in ctx["recent_eol"]],
        "None.",
    ))
    s.append((
        "Currently supported versions",
        ["Product", "Version line", "Latest version", "LTS", "End of life"],
        [[r["label"], r["cycle"], (r["latest_version"] or "-") + _v(r), "yes" if r["is_lts"] else "", r["eol_from"] or "not announced"]
         for r in ctx["supported"]],
        "No supported version found.",
    ))
    return s


def to_markdown(ctx: dict) -> str:
    lines = [f"# Tech version watch - {ctx['today']}", ""]
    for title, headers, rows, empty in _sections(ctx):
        lines += [f"## {title}", ""]
        if not rows:
            lines += [empty, ""]
            continue
        lines += ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
        lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
        lines.append("")
    if ctx["failed"]:
        lines += ["## Sources that failed", ""] + [f"- {f}" for f in ctx["failed"]] + [""]
    return "\n".join(lines)


# Criticality of an end-of-life date: (label, days threshold, badge background, badge text)
CRITICAL_DAYS, HIGH_DAYS, MEDIUM_DAYS = 30, 90, 180
_LEVELS = {
    "critical": ("Critical", "#fbc4c4", "#8f2323"),
    "high": ("High", "#fdd5b0", "#8a4210"),
    "medium": ("Medium", "#fdf0b0", "#7a5c0a"),
    "low": ("Low", "#c4dcfb", "#1f4a8a"),
    "none": ("No date", "#e3e8ef", "#4b5a6e"),
}
# Sections that get a criticality column, and the context list their rows come from.
_LEVEL_SECTIONS = {
    "Newly end-of-life": "newly_eol",
    "Upcoming end of life": "upcoming",
    "Recently reached end of life": "recent_eol",
    "Currently supported versions": "supported",
}

_BLUE, _INK, _BG = "#a9c8f5", "#1f2a3d", "#ffffff"
_HEAD_BG, _LINE = "#e4eefc", "#e6edf7"


def _level(eol_from: str | None, today: dt.date) -> tuple[str, str]:
    """Return (level key, relative text) for an end-of-life date."""
    if not eol_from:
        return "none", "not announced"
    days = (dt.date.fromisoformat(eol_from) - today).days
    if days < 0:
        return "critical", f"{-days} days ago"
    when = "today" if days == 0 else f"in {days} days"
    if days <= CRITICAL_DAYS:
        return "critical", when
    if days <= HIGH_DAYS:
        return "high", when
    if days <= MEDIUM_DAYS:
        return "medium", when
    return "low", when


def _badge(level: str, note: str) -> str:
    label, bg, fg = _LEVELS[level]
    return (
        f"<span style='display:inline-block;padding:2px 10px;border-radius:10px;background:{bg};color:{fg};"
        f"font-size:11px;font-weight:600;letter-spacing:.3px'>{label}</span>"
        f"<div style='color:#8493a8;font-size:11px;margin-top:2px'>{html.escape(note)}</div>"
    )


def _chip(key: str, label: str, bg: str, fg: str) -> str:
    return (
        f"<button type='button' data-f='{key}' style='margin:2px;padding:4px 14px;border:0;border-radius:14px;"
        f"background:{bg};color:{fg};font:600 12px Segoe UI,Arial,sans-serif;cursor:pointer'>{label}</button>"
    )


# Click a chip to toggle that level (several can be active); "All" clears the filter.
_FILTER_JS = """
(function(){
var bar=document.getElementById('flt');if(!bar)return;bar.style.display='block';
var on={},btns=bar.querySelectorAll('button');
function apply(){
var any=Object.keys(on).length;
document.querySelectorAll('tr[data-level]').forEach(function(r){
r.style.display=(!any||on[r.getAttribute('data-level')])?'':'none';});
document.querySelectorAll('.sec').forEach(function(s){
var rs=s.querySelectorAll('tr[data-level]');if(!rs.length)return;
var vis=0;rs.forEach(function(r){if(r.style.display!=='none')vis++;});
s.style.display=vis?'':'none';});
btns.forEach(function(b){var f=b.getAttribute('data-f');
b.style.outline=(f==='all'?!any:!!on[f])?'2px solid #1f2a3d':'none';});}
btns.forEach(function(b){b.onclick=function(){var f=b.getAttribute('data-f');
if(f==='all')on={};else if(on[f])delete on[f];else on[f]=1;apply();};});
apply();})();
"""


def _tile(value: int, label: str, bg: str, fg: str) -> str:
    return (
        f"<td align='center' width='25%' style='padding:14px 6px;background:{bg};border-radius:12px'>"
        f"<div style='font-size:26px;font-weight:700;color:{fg}'>{value}</div>"
        f"<div style='font-size:11px;color:{fg};opacity:.85'>{label}</div></td>"
    )


def to_html(ctx: dict) -> str:
    e = html.escape
    today = dt.date.fromisoformat(ctx["today"])

    counts = {k: 0 for k in _LEVELS}
    for r in ctx["supported"]:
        counts[_level(r.get("eol_from"), today)[0]] += 1
    tiles = "<td width='8'></td>".join([
        _tile(len(ctx["recent_eol"]) + len(ctx["newly_eol"]), "Already EOL", *_LEVELS["none"][1:]),
        _tile(counts["critical"], f"Critical &le; {CRITICAL_DAYS} d", *_LEVELS["critical"][1:]),
        _tile(counts["high"], f"High &le; {HIGH_DAYS} d", *_LEVELS["high"][1:]),
        _tile(counts["medium"], f"Medium &le; {MEDIUM_DAYS} d", *_LEVELS["medium"][1:]),
    ])

    def table(title: str, head: list[str], body: list[str]) -> str:
        ths = "".join(
            f"<th align='left' style='background:{_HEAD_BG};color:{_INK};font-size:12px;font-weight:600'>{e(h)}</th>"
            for h in head
        )
        return (
            f"<div class='sec'><div style='margin-top:28px;color:{_INK};font-size:15px;font-weight:600;text-align:center'>{e(title)}</div>"
            "<table width='100%' cellpadding='9' cellspacing='0' style='border-collapse:collapse;font-size:13px;"
            f"margin-top:10px'><tr>{ths}</tr>{''.join(body)}</table></div>"
        )

    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Tech version watch - {e(ctx['today'])}</title></head>"
        f"<body style='margin:0;padding:28px 12px;background:{_BG};font-family:Segoe UI,Arial,sans-serif;color:{_INK}'>"
        "<table role='presentation' align='center' width='100%' cellpadding='0' cellspacing='0' "
        "style='max-width:820px;margin:0 auto'><tr><td>",
        f"<div style='text-align:center;font-size:26px;font-weight:700'>Tech version watch</div>"
        f"<div style='text-align:center;color:#8493a8;font-size:13px;margin:4px 0 18px'>{e(ctx['today'])}</div>",
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>{tiles}</tr></table>",
        # Filter bar: hidden until the script runs, so mail clients (which strip scripts) never show dead buttons.
        "<div id='flt' style='display:none;text-align:center;margin-top:20px'>"
        "<span style='font-size:12px;color:#8493a8;margin-right:6px'>Filter:</span>"
        + _chip("all", "All", "#e4eefc", _INK)
        + "".join(_chip(k, v[0], v[1], v[2]) for k, v in _LEVELS.items())
        + "</div>",
    ]
    for title, headers, rows, _empty in _sections(ctx):
        if not rows:
            continue
        key = next((k for p, k in _LEVEL_SECTIONS.items() if title.startswith(p)), None)
        levels = [_level(r.get("eol_from"), today) for r in ctx[key]] if key else []
        body = []
        for i, r in enumerate(rows):
            edge = _LEVELS[levels[i][0]][1] if key else _BLUE
            cells = [
                f"<td style='border-bottom:1px solid {_LINE};{'border-left:4px solid ' + edge + ';' if j == 0 else ''}'>"
                f"{e(str(c))}</td>"
                for j, c in enumerate(r)
            ]
            if key:
                cells.append(f"<td style='border-bottom:1px solid {_LINE}'>{_badge(*levels[i])}</td>")
            attr = f" data-level='{levels[i][0]}'" if key else ""
            body.append(f"<tr{attr}>" + "".join(cells) + "</tr>")
        parts.append(table(title, list(headers) + (["Criticality"] if key else []), body))
    if ctx["failed"]:
        body = [f"<tr><td style='border-bottom:1px solid {_LINE};border-left:4px solid {_LEVELS['critical'][1]}'>{e(f)}</td></tr>"
                for f in ctx["failed"]]
        parts.append(table("Sources that failed", ["Source"], body))
    parts.append(f"</td></tr></table><script>{_FILTER_JS}</script></body></html>")
    return "".join(parts)
